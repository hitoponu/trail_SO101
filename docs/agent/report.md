# 報告（実機 → Mac）

- **更新**: 2026-08-02（2回目）
- **対応する依頼**: 2026-08-02（2回目）
- **状態**: 完了

## 「誰が戻したか」への回答

**(c) 分からない。**

このセッションを開始した時点で EEPROM は初期値だった。作業ツリーには復旧用の
`so101_joints.yaml` が未コミット変更として存在していたが、それを誰が実機へ適用したか、
または適用されていないかを確認できる記録は見つからなかった。

## 実行したコマンド

```bash
git pull --ff-only

cd docker/so101_ros2
docker compose down
docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_probe --port /dev/so101_follower --torque-off --watch

docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_probe --port /dev/so101_follower --scan

HARDWARE_TYPE=real docker compose up 2>&1 | tee /tmp/so101_real.log

docker compose exec so101-follower /entrypoint.sh ros2 control list_hardware_components
docker compose exec so101-follower /entrypoint.sh ros2 control list_controllers
docker compose exec so101-follower /entrypoint.sh ros2 topic echo /joint_states --once --field name
docker compose exec so101-follower /entrypoint.sh ros2 topic echo /joint_states --once --field position
timeout --signal=INT 8s docker compose exec so101-follower /entrypoint.sh ros2 topic hz /joint_states

grep -E "ERROR|WARN|out of limits" /tmp/so101_real.log

docker compose down
```

## 出力

### 手順1: 全関節を指定範囲内にした後の `--scan`

```
 id  model  Present    Delta   Homing     q_ros    q_deg     Min     Max      V    C
                       (-2048)  offset     [rad]    [deg]
--- ------ -------- -------- -------- --------- -------- ------- ------- ------ ----
  1    777     2170      122    -1711    0.1871     10.72     695    3409    4.8    28
  2    777     2093       45    -1078    0.0690      3.96     802    3154    4.8    27
  3    777     1847     -201     1731   -0.3083    -17.67     670    3051    4.8    27
  4    777     1919     -129     2012   -0.1979    -11.34    1014    3350    4.8    28
  5    777     3145     1097      406    1.6828     96.42       0    4095    4.8    29
  6    777     2541      493     1441    0.7563     43.33    1961    3399    4.8    28
```

### `list_hardware_components`

```
Hardware Component 1
	name: SO_ARM101
	type: system
	plugin name: feetech_ros2_driver/FeetechHardwareInterface
	state: id=3 label=active
	read/write rate: 50 Hz
	is_async: False
	command interfaces
		shoulder_pan_joint/position [available] [unclaimed]
		shoulder_lift_joint/position [available] [unclaimed]
		elbow_flex_joint/position [available] [unclaimed]
		wrist_flex_joint/position [available] [unclaimed]
		wrist_roll_joint/position [available] [unclaimed]
		gripper_joint/position [available] [unclaimed]
```

### `list_controllers`

```
forward_position_controller position_controllers/JointGroupPositionController           inactive
gripper_controller          parallel_gripper_action_controller/GripperActionController  inactive
joint_trajectory_controller joint_trajectory_controller/JointTrajectoryController       unconfigured
joint_state_broadcaster     joint_state_broadcaster/JointStateBroadcaster               active
```

### `/joint_states --field name`

```
['elbow_flex_joint', 'gripper_joint', 'shoulder_lift_joint', 'shoulder_pan_joint', 'wrist_flex_joint', 'wrist_roll_joint']
---
```

### `/joint_states --field position`

```
array('d', [2.8332625152247792, 3.8978451820174143, 3.20601984668099, 3.321068405772413, 2.9391071895888885, 4.824369577900342])
---
```

### `/joint_states` 周波数

```
average rate: 50.003
	min: 0.020s max: 0.020s std dev: 0.00014s window: 52
average rate: 49.999
	min: 0.018s max: 0.021s std dev: 0.00024s window: 102
average rate: 49.998
	min: 0.018s max: 0.021s std dev: 0.00022s window: 152
average rate: 49.998
	min: 0.018s max: 0.021s std dev: 0.00024s window: 202
average rate: 49.999
	min: 0.017s max: 0.023s std dev: 0.00032s window: 253
average rate: 50.000
	min: 0.017s max: 0.023s std dev: 0.00030s window: 304
average rate: 50.000
	min: 0.017s max: 0.023s std dev: 0.00032s window: 354
average rate: 50.001
	min: 0.017s max: 0.023s std dev: 0.00030s window: 405
average rate: 50.000
	min: 0.017s max: 0.023s std dev: 0.00030s window: 455
average rate: 49.999
	min: 0.017s max: 0.023s std dev: 0.00030s window: 505
average rate: 50.001
	min: 0.017s max: 0.023s std dev: 0.00035s window: 556
average rate: 49.998
	min: 0.017s max: 0.023s std dev: 0.00036s window: 606
average rate: 50.000
	min: 0.017s max: 0.023s std dev: 0.00039s window: 657
average rate: 50.000
	min: 0.017s max: 0.023s std dev: 0.00037s window: 708
average rate: 50.000
	min: 0.017s max: 0.023s std dev: 0.00036s window: 759
average rate: 50.000
	min: 0.017s max: 0.023s std dev: 0.00037s window: 810
average rate: 49.999
	min: 0.017s max: 0.023s std dev: 0.00036s window: 860
average rate: 49.999
	min: 0.017s max: 0.023s std dev: 0.00035s window: 910
average rate: 50.000
	min: 0.017s max: 0.023s std dev: 0.00035s window: 961
average rate: 49.999
	min: 0.017s max: 0.023s std dev: 0.00034s window: 1011
average rate: 50.000
	min: 0.017s max: 0.023s std dev: 0.00034s window: 1062
average rate: 50.001
	min: 0.017s max: 0.023s std dev: 0.00037s window: 1113
average rate: 50.000
	min: 0.017s max: 0.023s std dev: 0.00036s window: 1163
```

### `/tmp/so101_real.log` の ERROR / WARN / out of limits

```
so101-follower  | [ros2_control_node-2] [WARN] [1785649079.044294412] [controller_manager]: Could not enable FIFO RT scheduling policy: with error number <1>(Operation not permitted). See [https://control.ros.org/master/doc/ros2_control/controller_manager/doc/userdoc.html] for details on how to enable realtime scheduling.
so101-follower  | [ros2_control_node-2] [ERROR] [1785649080.245807557] [joint_limiter_interface]: Joint position is out of bounds for the joint : 'shoulder_pan_joint' actual position: 3.3287383097118415 limits: [-1.91986, 1.91986]. This could be due to a hardware failure (or) the physical limits of the joint being larger than the ones defined in the URDF. Please recheck the URDF and the hardware to verify the joint limits.
so101-follower  | [ros2_control_node-2] [ERROR] [1785649080.245915213] [controller_manager]: Caught exception of type : St13runtime_error while updating controller 'joint_trajectory_controller': Joint position is out of bounds for the joint : 'shoulder_pan_joint' actual position: 3.3287383097118415 limits: [-1.91986, 1.91986]. This could be due to a hardware failure (or) the physical limits of the joint being larger than the ones defined in the URDF. Please recheck the URDF and the hardware to verify the joint limits.
so101-follower  | [ros2_control_node-2] [ERROR] [1785649080.245958161] [controller_manager]: Deactivating controllers : [ joint_trajectory_controller ] as their update resulted in an error!
so101-follower  | [ros2_control_node-2] [ERROR] [1785649080.246026303] [joint_trajectory_controller]: Caught exception in callback for transition 14
so101-follower  | [ros2_control_node-2] [ERROR] [1785649080.246043223] [joint_trajectory_controller]: Original error: Joint position is out of bounds for the joint : 'shoulder_pan_joint' actual position: 3.3287383097118415 limits: [-1.91986, 1.91986]. This could be due to a hardware failure (or) the physical limits of the joint being larger than the ones defined in the URDF. Please recheck the URDF and the hardware to verify the joint limits.
so101-follower  | [ros2_control_node-2] [WARN] [1785649080.246057743] [joint_trajectory_controller]: Callback returned ERROR during the transition: deactivate
so101-follower  | [ros2_control_node-2] [ERROR] [1785649080.246073316] [controller_manager]: After deactivating, controller 'joint_trajectory_controller' is in state 'unconfigured', expected Inactive
so101-follower  | [ros2_control_node-2] [ERROR] [1785649080.845702294] [controller_manager]: Caught exception of type : St13runtime_error while updating controller 'gripper_controller': Joint position is out of bounds for the joint : 'gripper_joint' actual position: 3.8978451820174143 limits: [0, 1.7]. This could be due to a hardware failure (or) the physical limits of the joint being larger than the ones defined in the URDF. Please recheck the URDF and the hardware to verify the joint limits.
so101-follower  | [ros2_control_node-2] [ERROR] [1785649080.845775412] [controller_manager]: Deactivating controllers : [ gripper_controller ] as their update resulted in an error!
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

- 起動前の `--scan` では6関節すべてが依頼の範囲内だった。
- 起動後の `/joint_states` は全関節で起動前 `q_ros` と一致しなかった。
- RViz は実物と一致せず、「関節角度が不適な値に初期化されているように見える」と人間が目視した。
- 起動ログには全関節について `does not specify an offset parameter - Setting it to 0` と出ていた。
- `/joint_states` の各 position は、対応する scan の `Present` に `2π/4096` を掛けた値とほぼ一致する。
  例: gripper は `Present=2541` に対して `/joint_states=3.8978451820174143 rad`。
- `joint_trajectory_controller` は shoulder_pan の limit 超過で `unconfigured`、
  `gripper_controller` は gripper の limit 超過で `inactive` になった。
- `send_goal`、`so101_joints.yaml` の更新、ビルドは実行していない。
- 最後に `docker compose down` を実行し、実機はトルク OFF。

## 推測・気づき

- 推測: ドライバ側で中心値 `2048` を引くための offset が設定されていないため、
  `/joint_states` が全関節で約 `π rad` ずれている可能性が高い。
- 「全関節を limit 内にして起動すれば正常になる」という仮説は、今回の観測では成立しなかった。

## 次に必要なこと / 確認したいこと

- `feetech_ros2_driver` が期待する `offset` の単位と設定箇所を確認する必要がある。
