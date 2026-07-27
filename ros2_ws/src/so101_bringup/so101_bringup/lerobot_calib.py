"""lerobot の較正 JSON を feetech_ros2_driver の joint_config_file へ変換する。

    ros2 run so101_bringup so101_calib \\
        --json ~/.cache/huggingface/lerobot/calibration/robots/so_follower/my_awesome_follower_arm.json \\
        --delta shoulder_pan=0,shoulder_lift=0,elbow_flex=0,wrist_flex=0,wrist_roll=0,gripper=-790

────────────────────────────────────────────────────────────────
なぜ Δ (delta) を手で渡すのか
────────────────────────────────────────────────────────────────
lerobot と driver でレジスタも符号化も一致していることは確認済み:

    レジスタ  Homing_Offset = 31 (2byte)          … 両者同じ
    符号化    sign-magnitude 符号ビット 11         … 両者同じ
    range_*   reg 9-12、homing 適用後の tick 空間  … 両者同じ
    中心      lerobot = 2047 / driver = 2048       … 1 tick (0.088°) だけ違う

本当の問題は符号化ではなく **ゼロ姿勢の定義** である。
lerobot の homing_offset は「較正時に操作者が ENTER を押したときの姿勢」で
決まる。一方 URDF のゼロは幾何学的に定義されている。一致する *はず* だが、
アームで「はず」に頼ってはいけない。

そこで so101_probe でトルクを切り、各関節を URDF ゼロ姿勢へ手で合わせて

    Δ = Present - 2048

を実測し、それをここへ渡す。この方法は lerobot の意味論に一切依存せず、
**driver が実際に publish する値と同じ計器で測る**ので確実である。

    homing_offset_ros = homing_offset_現在 + Δ
    range_*_ros       = range_*_現在 - Δ        (Present 空間が Δ だけずれるため)

★ グリッパは Δ が大きくなる (-790 tick 程度)。so_arm101 の gripper_joint の
  ゼロは「閉」であって可動域の中間ではないため。丸め誤差ではなく規約の違い。

Δ を全部 0 にすれば「lerobot の値をそのまま使う」ことになる。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

#: lerobot のモータ名 → so_arm101_description の関節名。
#: **この対応表の唯一の出典**。他の場所に散らさないこと。
#: (リンク名も moving_jaw_so101_v1_link → jaw_link に改名されている)
LEROBOT_TO_ROS = {
    "shoulder_pan": "shoulder_pan_joint",
    "shoulder_lift": "shoulder_lift_joint",
    "elbow_flex": "elbow_flex_joint",
    "wrist_flex": "wrist_flex_joint",
    "wrist_roll": "wrist_roll_joint",
    "gripper": "gripper_joint",
}

#: Homing_Offset は sign-magnitude 符号ビット 11 → 大きさは 11 ビットまで。
#: これを超えると driver 側の encode_sign_magnitude が std::out_of_range を投げ、
#: 捕捉されないので **on_init でハードウェアコンポーネントごとクラッシュする**。
MAX_HOMING_OFFSET = 2047

MAX_TICK = 4095

#: 既定の調整値。so101_joints.yaml の Phase 1 と揃えてある。
DEFAULT_TUNING = {
    "p_coefficient": 16,
    "i_coefficient": 0,
    "d_coefficient": 32,
    "return_delay_time": 0,
    "acceleration": 20,
}
GRIPPER_EXTRA = {"protection_current": 200, "overload_torque": 40}


def parse_deltas(text: str) -> dict[str, int]:
    if not text:
        return {}
    out = {}
    for item in text.split(","):
        name, _, value = item.partition("=")
        name = name.strip()
        if name not in LEROBOT_TO_ROS:
            raise SystemExit(f"未知のモータ名: {name!r} (期待: {list(LEROBOT_TO_ROS)})")
        out[name] = int(value)
    return out


def convert(calib: dict, deltas: dict[str, int], emit_ranges: bool) -> tuple[dict, list[str]]:
    joints: dict[str, dict] = {}
    errors: list[str] = []

    for name, ros_name in LEROBOT_TO_ROS.items():
        if name not in calib:
            errors.append(f"{name}: 較正 JSON に存在しない")
            continue

        entry = calib[name]
        delta = deltas.get(name, 0)

        homing = int(entry["homing_offset"]) + delta
        if abs(homing) > MAX_HOMING_OFFSET:
            errors.append(
                f"{name}: homing_offset={homing} が ±{MAX_HOMING_OFFSET} を超える。"
                " driver が on_init でクラッシュするので却下する"
            )

        out: dict = {"id": int(entry["id"])}
        out.update(DEFAULT_TUNING)
        if name == "gripper":
            out.update(GRIPPER_EXTRA)
        out["homing_offset"] = homing

        if emit_ranges:
            # Present 空間が Δ だけずれるので、範囲は逆向きに動かす
            rmin = int(entry["range_min"]) - delta
            rmax = int(entry["range_max"]) - delta
            if rmin >= rmax:
                errors.append(f"{name}: range_min({rmin}) >= range_max({rmax})")
            clamped_min = max(0, min(MAX_TICK, rmin))
            clamped_max = max(0, min(MAX_TICK, rmax))
            if (clamped_min, clamped_max) != (rmin, rmax):
                print(
                    f"# 注意: {name} の range を 0..{MAX_TICK} にクランプした "
                    f"({rmin}..{rmax} -> {clamped_min}..{clamped_max})",
                    file=sys.stderr,
                )
            out["range_min"] = clamped_min
            out["range_max"] = clamped_max

        joints[name] = out

    return joints, errors


def dump_yaml(joints: dict, source: Path, deltas: dict[str, int]) -> str:
    lines = [
        "# so101_calib が生成したファイル (Phase 2: ゼロ点を実測して明示的に書いた状態)。",
        f"#   出典: {source}",
        f"#   実測 Δ: {deltas or '(なし)'}",
        "#",
        "# ★ 突合せは関節名ではなく servo id で行われる (driver の仕様)。",
        "# ★ YAML の値は URDF の <param> より優先される。",
        "#",
        "# 生成し直すには so101_bringup/lerobot_calib.py のドキュメントを参照。",
        "",
        "joints:",
    ]
    order = ["id", "p_coefficient", "i_coefficient", "d_coefficient",
             "return_delay_time", "acceleration", "protection_current",
             "overload_torque", "homing_offset", "range_min", "range_max"]
    for name, values in joints.items():
        lines.append(f"  {name}:")
        for key in order:
            if key in values:
                lines.append(f"    {key}: {values[key]}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="lerobot の較正 JSON を feetech_ros2_driver の joint_config_file へ変換する",
    )
    parser.add_argument("--json", required=True, type=Path, help="lerobot の較正 JSON")
    parser.add_argument(
        "--delta",
        default="",
        help="so101_probe で実測した Δ。例: shoulder_pan=0,gripper=-790",
    )
    parser.add_argument(
        "--emit-ranges",
        action="store_true",
        help="range_min/range_max も書き出す (既定では homing_offset のみ)",
    )
    parser.add_argument("-o", "--output", type=Path, help="出力先 (既定は標準出力)")
    args = parser.parse_args()

    calib = json.loads(args.json.read_text())
    deltas = parse_deltas(args.delta)

    missing = [n for n in LEROBOT_TO_ROS if n not in deltas]
    if missing:
        print(
            f"# 注意: Δ を指定していないモータがある (0 として扱う): {missing}",
            file=sys.stderr,
        )

    joints, errors = convert(calib, deltas, args.emit_ranges)
    if errors:
        for message in errors:
            print(f"エラー: {message}", file=sys.stderr)
        raise SystemExit(1)

    text = dump_yaml(joints, args.json, deltas)
    if args.output:
        args.output.write_text(text)
        print(f"書き出しました: {args.output}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
