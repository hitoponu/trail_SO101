# 報告（実機 → Mac）

- **更新**: 2026-08-02
- **対応する依頼**: 2026-08-02
- **状態**: 完了

## 実行したコマンド

```bash
git pull --ff-only

cd docker/so101_ros2
docker compose down
backup_file="backup_$(date +%Y%m%d_%H%M).yaml"
docker compose run --rm so101-follower ros2 run so101_bringup so101_calib --from-servos --port /dev/so101_follower --emit-ranges > "$backup_file"

docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_probe --port /dev/so101_follower --scan

docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_probe --port /dev/so101_follower --torque-off --watch
```

## 出力

### git pull

```
Already up to date.
```

### バックアップ

```
Container so101-follower  Stopping
Container so101-follower  Stopping
Container so101-follower  Stopped
Container so101-follower  Removing
Container so101-follower  Removed
# --from-servos: /dev/so101_follower のサーボから較正値を読んだ
# 注意: Δ を指定していないモータがある (0 として扱う): ['shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper']
BACKUP_FILE=backup_20260802_1425.yaml
BACKUP_EXIT=0
```

### `--scan`

```
 id  model  Present    Delta   Homing     q_ros    q_deg     Min     Max      V    C
                       (-2048)  offset     [rad]    [deg]
--- ------ -------- -------- -------- --------- -------- ------- ------- ------ ----
  1    777     2171      123    -1711    0.1887     10.81     695    3409    4.8    29
  2    777     2103       55    -1078    0.0844      4.83     802    3154    4.8    28
  3    777     1917     -131     1731   -0.2010    -11.51     670    3051    4.8    28
  4    777     1893     -155     2012   -0.2378    -13.62    1014    3350    4.9    28
  5    777     3208     1160      406    1.7794    101.95       0    4095    4.8    29
  6    777     1982      -66     1441   -0.1012     -5.80    1961    3399    4.9    29
```

### `--torque-off --watch` の wrist_flex（id 4）両端

最小値:

```
  4    777     1019    -1029     2012   -1.5785    -90.44    1014    3350    4.8    29
```

最大値:

```
  4    777     3362     1314     2012    2.0157    115.49    1014    3350    4.9    28
```

## 観測したこと

- wrist_flex の `Present` 最小値は `1019`、最大値は `3362`。
- wrist_flex の `q_ros` 最小値は `-1.5785 rad`、最大値は `2.0157 rad`。
- 端から端までの移動中、`Present` と `q_ros` に不連続な飛びはなかった。
- `q_ros` が `4 rad` を超える値は観測しなかった。
- バックアップファイルは `docker/so101_ros2/backup_20260802_1425.yaml`。
- EEPROM の書き換えと `send_goal` は実行していない。

## 推測・気づき

- なし。

## 次に必要なこと / 確認したいこと

- なし。
