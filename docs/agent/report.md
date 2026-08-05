# 報告（実機 → Mac）

- **更新**: 2026-08-02（4回目）
- **対応する依頼**: 2026-08-02（4回目）
- **状態**: 完了

## 実行したコマンド

```bash
git pull --ff-only

cd docker/so101_ros2
docker compose build
docker compose down
docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_probe --port /dev/so101_follower --torque
docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_probe --port /dev/so101_follower --scan
```

## 出力

### `--torque`

```
 id      P    D    I  MaxTorque  TorqueLim  ProtCurrent  Overload
--- ------ ---- ---- ---------- ---------- ------------ ---------
  1     16   32    0       1000       1000          500        80
  2     16   32    0       1000       1000          500        80
  3     16   32    0       1000       1000          500        80
  4     16   32    0       1000       1000          500        80
  5     16   32    0       1000       1000          500        80
  6     16   32    0        500        500          250        25

参考: STS3215 の P 既定は 32。lerobot は shakiness 回避で 16 に下げる。
      MaxTorque の最大は 1000。lerobot は gripper のみ 500 にする。
```

### `--scan`

```
 id  model  Present    Delta   Homing     q_ros    q_deg     Min     Max      V    C
                       (-2048)  offset     [rad]    [deg]
--- ------ -------- -------- -------- --------- -------- ------- ------- ------ ----
  1    777     2055        7    -1711    0.0107      0.62     695    3409    4.9    29
  2    777     1922     -126    -1078   -0.1933    -11.07     802    3154    4.9    27
  3    777     2051        3     1731    0.0046      0.26     670    3051    4.9    27
  4    777     2176      128     2012    0.1963     11.25    1014    3350    4.9    28
  5    777      196    -1852      406   -2.8409   -162.77       0    4095    4.8    29
  6    777     1997      -51     1441   -0.0782     -4.48    1961    3399    4.9    29
```

## 観測したこと

- id 1–6 はすべて `P=16`, `D=32`, `I=0`。
- id 1–5 は `MaxTorque=1000`, `TorqueLim=1000`, `ProtCurrent=500`, `Overload=80`。
- gripper（id 6）は `MaxTorque=500`, `TorqueLim=500`, `ProtCurrent=250`, `Overload=25`。
- 静止時の `V` は `4.8–4.9V`。
- 動作中の最低電圧は未測定。
- `wrist_roll` の `so101_offsets.xacro` 最終値は `2116`。
- 人間が「弱い」と感じた具体的な操作は `rqt_joint_trajectory_controller` のスライダ操作。
- 弱いと感じた関節は特定関節ではなく全関節。
- P ゲイン変更、EEPROM 書き換え、`send_goal` は実行していない。

## 推測・気づき

- 全関節が同じ操作で弱く、全関節の P が16だった。グリッパだけの現象ではなかった。

## 次に必要なこと / 確認したいこと

- 動作中の最低電圧を切り分けに使う場合は、安全な動作方法を指定してほしい。
