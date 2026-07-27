"""SO-101 のサーボを ROS を起動せずに読むための計測器。

**ゼロ点を実測するにはこれが要る。** feetech_ros2_driver は on_init の時点で
トルクを入れてしまうので、ros2_control が上がっている状態ではアームを手で
動かせない。トルクを切ってナマの tick を読む手段が別に必要になる。

    # 疎通確認 (ID 1-6 が model 777 で応答するか)
    ros2 run so101_bringup so101_probe --port /dev/so101_follower --scan

    # トルクを切って手で動かしながら値を見る (ゼロ点の実測)
    ros2 run so101_bringup so101_probe --port /dev/so101_follower --torque-off --watch

`q_ros` 列は driver が実際に publish する値と同じ式で計算している:

    q_ros = (Present_Position - 2048) * 2*pi / 4096

なので、この列が 0 になる姿勢が URDF のゼロ姿勢である。

────────────────────────────────────────────────────────────────
NOTE: lekiwi_base_bringup/lekiwi_base_bringup/sts_bus.py と 80 行ほど重複する。
      意図的に **相互 import しない**:
        * アームのパッケージがベースのパッケージに依存すべきでない
        * 必要なレジスタが違う (速度モード vs 位置モード)
      Feetech の落とし穴 (プロセスグローバル SCS_END、壊れた setPacketTimeout、
      EEPROM の Lock) は両方で同じなので、片方を直したらもう片方も見ること。
────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import argparse
import time

import scservo_sdk as scs

# ── レジスタ (アドレス, バイト数) ───────────────────────────────────────
MODEL_NUMBER = (3, 2)
MIN_ANGLE_LIMIT = (9, 2)
MAX_ANGLE_LIMIT = (11, 2)
HOMING_OFFSET = (31, 2)  # sign-magnitude, 符号ビット 11
TORQUE_ENABLE = (40, 1)
LOCK = (55, 1)  # EEPROM ロック. 0=解錠, 1=施錠
PRESENT_POSITION = (56, 2)
PRESENT_VOLTAGE = (62, 1)  # 単位 0.1V
PRESENT_TEMPERATURE = (63, 1)  # °C

STS3215_MODEL_NUMBER = 777

#: driver (feetech_ros2_driver) が位置の基準にする tick。lerobot は 2047。
STS_MIDPOINT = 2048

TICKS_PER_REV = 4096
SIGN_BIT_HOMING_OFFSET = 11


def decode_sign_magnitude(raw: int, sign_bit: int) -> int:
    magnitude = raw & ((1 << sign_bit) - 1)
    return -magnitude if (raw >> sign_bit) & 1 else magnitude


def ticks_to_rad(ticks: int) -> float:
    """driver の read() と同じ式。"""
    import math

    return (ticks - STS_MIDPOINT) * 2.0 * math.pi / TICKS_PER_REV


def _patched_set_packet_timeout(self, packet_length):
    """lerobot の patch_setPacketTimeout と同じ。

    素の SDK のタイムアウト式は Feetech には小さすぎ、散発的に RX タイムアウトする。
    """
    self.packet_start_time = self.getCurrentTime()
    self.packet_timeout = (self.tx_time_per_byte * packet_length) + (self.tx_time_per_byte * 3.0) + 50


class Probe:
    def __init__(self, port: str, ids: list[int], baudrate: int = 1_000_000) -> None:
        self.ids = ids
        self._port = scs.PortHandler(port)
        # ★ 素の SDK のタイムアウト式は壊れているので差し替える
        self._port.setPacketTimeout = _patched_set_packet_timeout.__get__(
            self._port, scs.PortHandler
        )
        # ★ これはプロセスグローバル SCS_END を書き換える。1 度だけ、0 で。
        self._packet = scs.PacketHandler(0)

        if not self._port.openPort():
            raise RuntimeError(f"ポートを開けない: {port}")
        if not self._port.setBaudRate(baudrate):
            self._port.closePort()
            raise RuntimeError(f"ボーレートを設定できない: {baudrate}")

    def close(self) -> None:
        self._port.closePort()

    def read(self, reg: tuple[int, int], motor_id: int, num_retry: int = 5) -> int | None:
        addr, size = reg
        reader = self._packet.read1ByteTxRx if size == 1 else self._packet.read2ByteTxRx
        for _ in range(1 + num_retry):
            value, comm, err = reader(self._port, motor_id, addr)
            if comm == scs.COMM_SUCCESS and err == 0:
                return value
        return None

    def write(self, reg: tuple[int, int], motor_id: int, value: int, num_retry: int = 5) -> bool:
        addr, size = reg
        writer = self._packet.write1ByteTxRx if size == 1 else self._packet.write2ByteTxRx
        for _ in range(1 + num_retry):
            comm, err = writer(self._port, motor_id, addr, int(value))
            if comm == scs.COMM_SUCCESS and err == 0:
                return True
        return False

    def disable_torque(self) -> None:
        for motor_id in self.ids:
            self.write(TORQUE_ENABLE, motor_id, 0)

    def snapshot(self, motor_id: int) -> dict:
        present = self.read(PRESENT_POSITION, motor_id)
        homing_raw = self.read(HOMING_OFFSET, motor_id)
        return {
            "id": motor_id,
            "model": self.read(MODEL_NUMBER, motor_id),
            "present": present,
            "homing_offset": (
                decode_sign_magnitude(homing_raw, SIGN_BIT_HOMING_OFFSET)
                if homing_raw is not None
                else None
            ),
            "range_min": self.read(MIN_ANGLE_LIMIT, motor_id),
            "range_max": self.read(MAX_ANGLE_LIMIT, motor_id),
            "q_rad": ticks_to_rad(present) if present is not None else None,
            "voltage": (lambda v: v / 10.0 if v is not None else None)(
                self.read(PRESENT_VOLTAGE, motor_id)
            ),
            "temperature": self.read(PRESENT_TEMPERATURE, motor_id),
        }


def _fmt(row: dict) -> str:
    import math

    def n(v, w, prec=None):
        if v is None:
            return "?".rjust(w)
        return (f"{v:{w}.{prec}f}" if prec is not None else f"{v:{w}d}")

    q = row["q_rad"]
    delta = row["present"] - STS_MIDPOINT if row["present"] is not None else None
    return (
        f"{row['id']:>3}  {n(row['model'], 5)}  {n(row['present'], 7)}  {n(delta, 7)}  "
        f"{n(row['homing_offset'], 7)}  "
        f"{n(q, 8, 4)}  {n(math.degrees(q) if q is not None else None, 8, 2)}  "
        f"{n(row['range_min'], 6)}  {n(row['range_max'], 6)}  "
        f"{n(row['voltage'], 5, 1)}  {n(row['temperature'], 4)}"
    )


HEADER = (
    " id  model  Present    Delta   Homing     q_ros    q_deg     Min     Max      V    C\n"
    "                       (-2048)  offset     [rad]    [deg]\n"
    "--- ------ -------- -------- -------- --------- -------- ------- ------- ------ ----"
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SO-101 のサーボをトルクOFFで読む (ゼロ点実測用)",
    )
    parser.add_argument("--port", default="/dev/so101_follower")
    parser.add_argument("--ids", default="1-6", help="例: 1-6 または 1,2,3")
    parser.add_argument("--baudrate", type=int, default=1_000_000)
    parser.add_argument("--scan", action="store_true", help="1回読んで終了")
    parser.add_argument(
        "--torque-off", action="store_true", help="トルクを切る (手で動かせるようにする)"
    )
    parser.add_argument("--watch", action="store_true", help="0.2秒ごとに更新し続ける")
    args = parser.parse_args()

    if "-" in args.ids:
        lo, hi = args.ids.split("-")
        ids = list(range(int(lo), int(hi) + 1))
    else:
        ids = [int(x) for x in args.ids.split(",")]

    probe = Probe(args.port, ids, baudrate=args.baudrate)
    try:
        if args.torque_off:
            probe.disable_torque()
            print("トルクを切りました。アームは自重で落ちます。手で支えてください。\n")

        def dump():
            print(HEADER)
            missing = []
            for motor_id in ids:
                row = probe.snapshot(motor_id)
                if row["present"] is None:
                    missing.append(motor_id)
                    print(f"{motor_id:>3}  応答なし")
                    continue
                print(_fmt(row))
                if row["model"] not in (None, STS3215_MODEL_NUMBER):
                    print(f"     !! ID {motor_id}: model {row['model']} は STS3215 (777) ではない")
            if missing:
                print(f"\n!! 応答しないモータ: {missing} — 配線と電源を確認してください")

        if args.watch:
            print("Ctrl+C で終了。Delta が 0 になる姿勢が URDF のゼロ姿勢です。\n")
            while True:
                dump()
                print()
                time.sleep(0.2)
        else:
            dump()
    except KeyboardInterrupt:
        pass
    finally:
        probe.close()


if __name__ == "__main__":
    main()
