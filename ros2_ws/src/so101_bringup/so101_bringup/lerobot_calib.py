"""較正値を feetech_ros2_driver の joint_config_file へ変換する。

較正値の入力元は2つ選べる。

    # A) サーボの EEPROM から直接読む (JSON 不要。別の PC で作業するとき推奨)
    ros2 run so101_bringup so101_calib \\
        --from-servos --port /dev/so101_follower --from-ranges --emit-ranges

    # B) lerobot の較正 JSON から読む (較正を実行した PC にしか無い)
    ros2 run so101_bringup so101_calib \\
        --json ~/.cache/huggingface/lerobot/calibration/robots/so_follower/my_awesome_follower_arm.json \\
        --from-ranges --emit-ranges

**較正値の実体はサーボの EEPROM にあり、JSON はその控えにすぎない。**
lerobot の較正キャッシュは実行した PC のホームにしか無いので、
別の PC で作業するときは A を使うこと。

Δ (ゼロ点の補正量) は ``--from-ranges`` で可動域から自動計算できる (目測不要)。
``--delta`` で関節ごとに上書きもできる。

────────────────────────────────────────────────────────────────
Δ をどう決めるか
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

#: driver が位置の基準にする tick (lerobot は 2047)。
STS_MIDPOINT = 2048

#: so_arm101_description の URDF 関節 limit [rad]。
#: ★ URDF (so_arm101_macro.xacro) と一致していること。--from-ranges の計算に使う。
URDF_LIMITS = {
    "shoulder_pan": (-1.91986, 1.91986),
    "shoulder_lift": (-1.74533, 1.74533),
    "elbow_flex": (-1.69, 1.54),
    "wrist_flex": (-1.6, 1.6),
    "wrist_roll": (-2.3, 2.3),
    "gripper": (0.0, 1.70),
}

#: lerobot がフルターン扱いにして可動域を記録しない関節。
#: range が 0..4095 固定なので --from-ranges では Δ を計算できない。
FULL_TURN_MOTORS = {"wrist_roll"}

#: グリッパは URDF のゼロが「閉」= 可動端であって中間ではない。
#: 他の関節とは計算方法が違う。
GRIPPER = "gripper"

#: 既定の調整値。so101_joints.yaml の Phase 1 と揃えてある。
DEFAULT_TUNING = {
    "p_coefficient": 16,
    "i_coefficient": 0,
    "d_coefficient": 32,
    "return_delay_time": 0,
    "acceleration": 20,
}
GRIPPER_EXTRA = {"protection_current": 200, "overload_torque": 40}


def wrap_homing(value: int) -> int:
    """homing_offset をレジスタが表現できる範囲へ折り返す。

    サーボは ``Present = (Actual - Homing_Offset) mod 4096`` で位置を計算するため、
    4096 だけずらした homing_offset は**完全に等価**である。
    ゼロがエンコーダの折り返し点付近にある関節では、素朴に Δ を足すと
    ±2047 のレジスタ範囲を超えるが、折り返せば表現できる。

    ★ ラップすることは **この機体で実機検証済み (2026-08-02)**。
      wrist_flex (homing=2012) を手で両可動端まで動かすと Present は 1019..3362。
      逆算すると Actual は 3031 → 4095 → 0 → 1278 と折り返しをまたぐが、
      Present は連続で飛びが無かった。ラップしなければ Actual=0 で
      Present=-2012 へ飛んだはずである。
      ただし機体やファーム版が変われば前提が変わるので、既定では折り返さず
      --allow-homing-wrap で明示的に選ぶ運用のままにしてある。
    """
    return ((value + 2048) % 4096) - 2048


def deltas_from_ranges(calib: dict, gripper_closed: str) -> tuple[dict[str, int], list[str]]:
    """記録済みの可動域から Δ を計算する（目測不要）。

    SO-101 の new_calib の規約は「各関節の仮想ゼロ＝可動域の中間」なので、
    lerobot が ``record_ranges_of_motion`` で記録した機械的可動端から
    ゼロ位置を逆算できる。可動端は客観的で再現性があるため、
    姿勢を目測で作るより確実。

    URDF の limit が非対称な関節（elbow_flex）に対応するため、単純な中点では
    なく「limit 内でのゼロの位置比率」で内挿する::

        frac = (0 - lower) / (upper - lower)
        zero_tick = range_min + frac * (range_max - range_min)

    グリッパだけは URDF のゼロが「閉」= 可動端なので別扱い。

    ★ 前提: 較正時に**機械的な可動端まで振り切れている**こと。
      途中で止めていると中点がずれる。再スイープして range が再現するかで
      検証できる。
    """
    out: dict[str, int] = {}
    notes: list[str] = []

    for name, (lower, upper) in URDF_LIMITS.items():
        if name not in calib:
            continue
        entry = calib[name]
        rmin, rmax = int(entry["range_min"]), int(entry["range_max"])

        if name in FULL_TURN_MOTORS:
            notes.append(
                f"{name}: lerobot がフルターン扱いで可動域を記録していないため"
                " Δ を計算できない (Δ=0 のまま)。必要なら --delta で個別に与えること"
            )
            continue

        if name == GRIPPER:
            # URDF のゼロは「閉」。どちらの可動端が閉かは機体を見て決める。
            zero_tick = rmin if gripper_closed == "min" else rmax
            notes.append(
                f"{name}: 閉を range_{gripper_closed}({zero_tick}) と仮定した。"
                " 閉じながら so101_probe で Present を見て確認すること"
            )
        else:
            frac = (0.0 - lower) / (upper - lower)
            zero_tick = rmin + frac * (rmax - rmin)

        out[name] = int(round(zero_tick - STS_MIDPOINT))

    return out, notes


def calib_from_servos(port: str, baudrate: int = 1_000_000) -> tuple[dict, list[str]]:
    """サーボの EEPROM から較正値を直接読む（lerobot の JSON が不要になる）。

    較正値の実体はサーボの EEPROM にあり、lerobot の JSON はその控えにすぎない。
    JSON は較正を実行した PC にしか無いので、別の PC で作業するときは
    こちらを使うほうが確実。

    読むレジスタは lerobot の書き込み先と同じ:
        Homing_Offset      reg 31 (sign-magnitude 符号ビット 11)
        Min_Position_Limit reg 9
        Max_Position_Limit reg 11
    """
    from so101_bringup.sts_probe import Probe  # 同一パッケージ内

    ids = {name: idx for idx, name in enumerate(LEROBOT_TO_ROS, start=1)}
    probe = Probe(port, list(ids.values()), baudrate=baudrate)
    warnings: list[str] = []
    calib: dict = {}
    try:
        for name, motor_id in ids.items():
            row = probe.snapshot(motor_id)
            if row["present"] is None:
                raise SystemExit(
                    f"ID {motor_id} ({name}) が応答しません。配線と電源を確認してください"
                )
            rmin, rmax = row["range_min"], row["range_max"]
            calib[name] = {
                "id": motor_id,
                "drive_mode": 0,
                "homing_offset": row["homing_offset"],
                "range_min": rmin,
                "range_max": rmax,
            }
            # 未較正のサーボは可動域が既定の 0..4095 のまま。
            # wrist_roll は lerobot が意図的に 0..4095 にするので除外。
            if name not in FULL_TURN_MOTORS and (rmin, rmax) == (0, MAX_TICK):
                warnings.append(
                    f"{name}: 可動域が 0..{MAX_TICK} のまま = **未較正の可能性**。"
                    " この状態で --from-ranges を使っても意味のあるΔは出ない"
                )
    finally:
        probe.close()

    return calib, warnings


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


def convert(
    calib: dict, deltas: dict[str, int], emit_ranges: bool, allow_wrap: bool = False
) -> tuple[dict, list[str], list[str]]:
    joints: dict[str, dict] = {}
    errors: list[str] = []
    notes: list[str] = []

    for name, ros_name in LEROBOT_TO_ROS.items():
        if name not in calib:
            errors.append(f"{name}: 較正 JSON に存在しない")
            continue

        entry = calib[name]
        delta = deltas.get(name, 0)

        homing = int(entry["homing_offset"]) + delta
        if abs(homing) > MAX_HOMING_OFFSET and allow_wrap:
            wrapped = wrap_homing(homing)
            notes.append(
                f"{name}: homing_offset {homing} を {wrapped} へ折り返した"
                " (--allow-homing-wrap)。★実機で q_ros が異常値になっていないか"
                " 必ず so101_probe で確認すること"
            )
            homing = wrapped
        if abs(homing) > MAX_HOMING_OFFSET:
            over = abs(homing) - MAX_HOMING_OFFSET
            errors.append(
                f"{name}: homing_offset={homing} が ±{MAX_HOMING_OFFSET} を"
                f"{over} tick 超える (driver が on_init でクラッシュするので却下)。\n"
                f"    原因: この関節はゼロがエンコーダの折り返し点付近にあり、\n"
                f"          現在の homing_offset={int(entry['homing_offset'])} がそれを吸収している。\n"
                f"    対処 A: --delta {name}=0 で補正を諦める"
                f" (この関節が {delta * 360 / 4096:+.1f}° ずれたままになる)\n"
                f"    対処 B: この関節を URDF ゼロ姿勢付近に置いて lerobot の較正をやり直す\n"
                f"    対処 C: --allow-homing-wrap で 4096 折り返した等価値を使う。\n"
                f"            ただしサーボが Present をラップしない場合、可動端で\n"
                f"            q_ros が数 rad の異常値になり RViz が破綻する。\n"
                f"            適用後に必ず so101_probe --scan で q_ros を確認すること"
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

    return joints, errors, notes


def dump_xacro(calib: dict, deltas: dict[str, int], source) -> str:
    """feetech_ros2_driver **v0.2.2** 用の offset を xacro プロパティとして出力する。

    v0.2.2 は per-joint の ``offset`` で中心値を扱う（GitHub main の
    ``kStsMidpoint`` 固定とも ``homing_offset`` とも別物）::

        read : q    = (Present - offset) * 2π/4096
        write: tick = q * 4096/2π + offset

    したがって **offset = URDF ゼロ姿勢における Present の tick 値** であり、
    ``2048 + Δ`` に等しい。EEPROM には一切書かない。
    """
    lines = [
        '<?xml version="1.0" ?>',
        "<!--",
        "  so101_calib が生成したファイル (feetech_ros2_driver v0.2.2 用の offset)。",
        f"    出典: {source}",
        "  offset = URDF ゼロ姿勢における Present の tick 値 (= 2048 + Δ)。",
        "  EEPROM には書き込まない。純粋なソフト側の補正値。",
        "-->",
        '<robot xmlns:xacro="http://www.ros.org/wiki/xacro">',
    ]
    for name in LEROBOT_TO_ROS:
        offset = STS_MIDPOINT + deltas.get(name, 0)
        delta = offset - STS_MIDPOINT
        lines.append(
            f'  <xacro:property name="so101_offset_{name}"'
            f' value="{offset}"/>  <!-- Δ={delta:+d} -->'
        )
    lines.append("</robot>")
    return "\n".join(lines) + "\n"


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
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--json", type=Path, help="lerobot の較正 JSON を読む")
    src.add_argument(
        "--from-servos",
        action="store_true",
        help="サーボの EEPROM から較正値を直接読む（JSON 不要。別PCで作業するとき推奨）",
    )
    parser.add_argument("--port", default="/dev/so101_follower", help="--from-servos のときのポート")
    parser.add_argument("--baudrate", type=int, default=1_000_000)
    parser.add_argument(
        "--from-ranges",
        action="store_true",
        help="記録済みの可動域からΔを計算する（目測不要。推奨）",
    )
    parser.add_argument(
        "--gripper-closed",
        choices=("min", "max"),
        default="min",
        help="--from-ranges のとき、グリッパの「閉」がどちらの可動端か（既定: min）",
    )
    parser.add_argument(
        "--delta",
        default="",
        help="Δ を手で与える。--from-ranges と併用すると個別に上書きできる。"
        " 例: shoulder_pan=0,gripper=-790",
    )
    parser.add_argument(
        "--allow-homing-wrap",
        action="store_true",
        help="homing_offset がレジスタ範囲外のとき 4096 折り返した等価値を使う。"
        " ★サーボが Present をラップしない場合 RViz が破綻するので、適用後に"
        " so101_probe --scan で q_ros を必ず確認すること",
    )
    parser.add_argument(
        "--emit-xacro",
        action="store_true",
        help="feetech_ros2_driver v0.2.2 用の offset を xacro 形式で出力する"
        " (config/so101_offsets.xacro へリダイレクトする)",
    )
    parser.add_argument(
        "--emit-ranges",
        action="store_true",
        help="range_min/range_max も書き出す (既定では homing_offset のみ)",
    )
    parser.add_argument("-o", "--output", type=Path, help="出力先 (既定は標準出力)")
    args = parser.parse_args()

    if args.from_servos:
        calib, warnings = calib_from_servos(args.port, args.baudrate)
        print(f"# --from-servos: {args.port} のサーボから較正値を読んだ", file=sys.stderr)
        for w in warnings:
            print(f"# 警告: {w}", file=sys.stderr)
    else:
        if not args.json.exists():
            raise SystemExit(
                f"較正 JSON が見つかりません: {args.json}\n"
                "  この PC で lerobot の較正をしていない場合、そのファイルは存在しません。\n"
                "  --from-servos を使うとサーボから直接読めます (JSON 不要)。"
            )
        calib = json.loads(args.json.read_text())

    deltas: dict[str, int] = {}
    if args.from_ranges:
        deltas, notes = deltas_from_ranges(calib, args.gripper_closed)
        print("# --from-ranges: 可動域からΔを計算した (目測なし)", file=sys.stderr)
        for name, value in deltas.items():
            print(f"#   {name:<14} Δ = {value:+5d} tick ({value * 360 / 4096:+6.1f}°)", file=sys.stderr)
        for note in notes:
            print(f"# 注意: {note}", file=sys.stderr)

    # --delta は --from-ranges の結果を個別に上書きする
    deltas.update(parse_deltas(args.delta))

    missing = [n for n in LEROBOT_TO_ROS if n not in deltas]
    if missing:
        print(
            f"# 注意: Δ を指定していないモータがある (0 として扱う): {missing}",
            file=sys.stderr,
        )

    joints, errors, notes = convert(calib, deltas, args.emit_ranges, args.allow_homing_wrap)
    for note in notes:
        print(f"# 注意: {note}", file=sys.stderr)
    if errors:
        for message in errors:
            print(f"エラー: {message}", file=sys.stderr)
        raise SystemExit(1)

    source = args.json if args.json else Path(f"servo EEPROM ({args.port})")
    if args.emit_xacro:
        text = dump_xacro(calib, deltas, source)
    else:
        text = dump_yaml(joints, source, deltas)
    if args.output:
        args.output.write_text(text)
        print(f"書き出しました: {args.output}", file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
