# 報告（実機 → Mac）

- **更新**: 2026-08-02（3回目）
- **対応する依頼**: 2026-08-02（3回目）
- **状態**: 完了

## 実行したコマンド

```bash
git pull --ff-only

cd docker/so101_ros2
docker compose build

docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_probe --port /dev/so101_follower --scan

HARDWARE_TYPE=real docker compose up 2>&1 | tee /tmp/so101_real2.log

docker compose exec so101-follower /entrypoint.sh ros2 control list_controllers
docker compose exec so101-follower /entrypoint.sh ros2 topic echo /joint_states --once --field name
docker compose exec so101-follower /entrypoint.sh ros2 topic echo /joint_states --once --field position
grep -E "ERROR|WARN|offset|out of bounds" /tmp/so101_real2.log

docker compose down
```

## 出力

### ビルド結果

```
Summary: 3 packages finished [2.89s]
  1 package had stderr output: so_arm_utils
```

driver バージョン検査を含む Docker build step は成功した。

```
#14 [ 9/13] RUN test "$(dpkg-query -W -f='${Version}' ros-jazzy-feetech-ros2-driver | cut -d- -f1)" = "0.2.2"     || (echo "!! feetech_ros2_driver のバージョンが 0.2.2 ではない。"         && echo "!! so101_follower.ros2_control.xacro は v0.2.2 前提 (offset / p_cofficient)。"         && echo "!! 上流の変更点を確認してから xacro を更新すること。" && exit 1)
#14 DONE 0.2s
```

### 起動前 `--scan`

```
 id  model  Present    Delta   Homing     q_ros    q_deg     Min     Max      V    C
                       (-2048)  offset     [rad]    [deg]
--- ------ -------- -------- -------- --------- -------- ------- ------- ------ ----
  1    777     2167      119    -1711    0.1825     10.46     695    3409    4.8    28
  2    777     2179      131    -1078    0.2010     11.51     802    3154    4.8    27
  3    777     1896     -152     1731   -0.2332    -13.36     670    3051    4.8    26
  4    777     2210      162     2012    0.2485     14.24    1014    3350    4.9    28
  5    777     3237     1189      406    1.8239    104.50       0    4095    4.8    29
  6    777     2277      229     1441    0.3513     20.13    1961    3399    4.9    28
```

### `list_controllers`

```
forward_position_controller position_controllers/JointGroupPositionController           inactive
gripper_controller          parallel_gripper_action_controller/GripperActionController  active
joint_trajectory_controller joint_trajectory_controller/JointTrajectoryController       active
joint_state_broadcaster     joint_state_broadcaster/JointStateBroadcaster               active
```

### `/joint_states --field name`

```
A message was lost!!!
	total count change:1
	total count: 1---
['elbow_flex_joint', 'gripper_joint', 'shoulder_lift_joint', 'shoulder_pan_joint', 'wrist_flex_joint', 'wrist_roll_joint']
---
```

### `/joint_states --field position`

```
array('d', [-0.032213596545598466, 0.483203948183977, 0.3052621767892426, 0.17640779060684875, 0.04141748127291231, 1.8208351952202562])
---
```

### `/tmp/so101_real2.log` の ERROR / WARN / offset / out of bounds

```
so101-follower  | [ros2_control_node-2] [WARN] [1785649943.747256649] [controller_manager]: Could not enable FIFO RT scheduling policy: with error number <1>(Operation not permitted). See [https://control.ros.org/master/doc/ros2_control/controller_manager/doc/userdoc.html] for details on how to enable realtime scheduling.
```

### 停止

```
Container so101-follower  Stopping
Container so101-follower  Stopping
Container so101-follower  Stopped
Container so101-follower  Removing
Container so101-follower  Removed
```

## 観測したこと

- 4 controller は3つが `active`、`forward_position_controller` が `inactive`。
  `unconfigured` はなかった。
- 前回のような約 `+π rad` のずれと `out of bounds` エラーは解消した。
- 起動前 scan の `q_ros` と起動後 `/joint_states` position の比較:

| joint | scan `q_ros` | `/joint_states` | 差（後−前） |
| --- | ---: | ---: | ---: |
| elbow_flex | -0.2332 | -0.032213596545598466 | 約 +0.2010 |
| gripper | +0.3513 | +0.483203948183977 | 約 +0.1319 |
| shoulder_lift | +0.2010 | +0.3052621767892426 | 約 +0.1043 |
| shoulder_pan | +0.1825 | +0.17640779060684875 | 約 -0.0061 |
| wrist_flex | +0.2485 | +0.04141748127291231 | 約 -0.2071 |
| wrist_roll | +1.8239 | +1.8208351952202562 | 約 -0.0031 |

- `shoulder_pan` と `wrist_roll` は約 0.0061 rad 以内で一致した。
- `shoulder_lift`、`elbow_flex`、`wrist_flex`、`gripper` は約 0.104〜0.207 rad の差があった。
- 人間の目視では RViz は実物と一致し、正しく動いていた。
- `send_goal` は実行していない。
- 最後に `docker compose down` を実行し、実機はトルク OFF。

## 推測・気づき

- `/joint_states` と scan `q_ros` の残差は、機体別 offset と 2048 の差を反映した値に見える。
  期待結果の「scan の `q_ros` とほぼ一致」は4関節では成立しなかった。

## 次に必要なこと / 確認したいこと

- scan の `q_ros` が固定中心 2048 基準である一方、driver は機体別 offset 基準なので、
  どちらを期待値にするか確認が必要。
