# 報告（実機 → Mac）

- **更新**: 2026-08-07（`make reach` 最終確認）
- **対応する依頼**: 2026-08-05（6回目）
- **状態**: 実機起動成功（リーチ指令は未送信）
- **ブランチ**: `feat/lekiwi-so101-reach`

初回確認時は実機デバイスがこのLinux環境に接続されていなかったため、手順0の一部と実機起動を実行できなかった。その後、接続・固定後に再確認し、実機起動まで完了した。実機を動かす指令、`lerobot-calibrate`、EEPROM変更は実行していない。

## 実行したコマンド

```bash
git pull --ff-only
```

```text
Already up to date.
```

```bash
getent group dialout
```

```text
dialout:x:20:hsr_pc5
```

```bash
for dev in /dev/lekiwi /dev/so101_follower /dev/rplidar; do echo "--- $dev ---"; if [ -e "$dev" ]; then ls -l "$dev"; udevadm info -q property -n "$dev" | grep -iE '^(ID_SERIAL|ID_SERIAL_SHORT|ID_VENDOR|DEVPATH)=' || true; else echo 'NOT FOUND'; fi; done
```

```text
--- /dev/lekiwi ---
NOT FOUND
--- /dev/so101_follower ---
NOT FOUND
--- /dev/rplidar ---
NOT FOUND
```

```bash
ls -la ~/.cache/huggingface/lerobot/calibration/robots/so_follower/
```

```text
total 20
drwxr-xr-x 3 nobody nogroup 4096 Aug  5 21:09 .
drwxr-xr-x 3 nobody nogroup 4096 Aug  2 10:48 ..
drwxr-xr-x 2 nobody nogroup 4096 Aug  2 10:48 my_awesome_follower_arm.json
-rw-r--r-- 1 nobody nogroup  917 Aug  5 15:48 my_follower.json
-rw-rw-r-- 1 hsr_pc5 hsr_pc5  914 Aug  5 21:08 my_follower2.json
```

```bash
cd docker/lekiwi_so101_bringup
make build
make bootstrap
```

`.env` は作成した。`DIALOUT_GID=20`、`/dev/lekiwi`、`/dev/so101_follower`、`/dev/rplidar`、`ROS_DOMAIN_ID=7` を設定した。

`make build` は成功し、以下のイメージを生成した。

```text
local/lekiwi-base-ros2:jazzy
local/rplidar-a1-ros2:jazzy
local/so101-ros2:jazzy
```

`make bootstrap` の末尾:

```text
Summary: 5 packages finished [2.54s]
  4 packages had stderr output: lekiwi_description lekiwi_so101_bringup so101_bringup so_arm_utils

== 静的検査 ==
  Python import: OK
  アーム単体 URDF: OK
  結合 URDF: OK

== 完了 ==
```

## モック構成

```bash
make mock
```

`make mock` は `guard-mock` の変数エスケープ不具合で起動しなかった。

```text
ERROR: 13213name が起動中。ROS_DOMAIN_ID が衝突して
       /robot_description が二重に latch され、/tf も混信する。
       先に停止すること: docker stop 13213name
make: *** [Makefile:61: guard-mock] Error 1
```

既存コンテナが空であることを確認後、以下を直接実行した。

```bash
docker compose -f compose.mock.yaml up
make check
```

`make check` の出力:

```text
--- /robot_description (期待: 1) ---
Publisher count: 1
--- /joint_states (期待: 2) ---
Publisher count: 2
--- controllers (期待: active 3 つ) ---
gripper_controller          parallel_gripper_action_controller/GripperActionController  active
joint_trajectory_controller joint_trajectory_controller/JointTrajectoryController       active
joint_state_broadcaster     joint_state_broadcaster/JointStateBroadcaster               active
--- map -> arm_gripper_frame_link ---
- Translation: [0.471, -0.040, 0.315]
```

```bash
docker exec lekiwi-so101-arm-mock /entrypoint.sh timeout 5 ros2 run tf2_ros tf2_echo map arm_gripper_frame_link
```

```text
- Translation: [0.471, -0.040, 0.315]
- Rotation: in Quaternion (xyzw) [0.000, 0.707, 0.001, 0.707]
- Rotation: in RPY (radian) [2.032, 1.569, 2.032]
- Rotation: in RPY (degree) [116.405, 89.898, 116.451]
```

```bash
docker exec lekiwi-so101-arm-mock /entrypoint.sh ros2 run tf2_tools view_frames -o /tmp/frames
docker cp lekiwi-so101-arm-mock:/tmp/frames.pdf /home/hsr_pc5/frames_mock.pdf
```

```text
-rw-r--r-- 1 hsr_pc5 hsr_pc5 18K Aug  7 10:18 /home/hsr_pc5/frames_mock.pdf
```

TFツリーは `map -> odom -> base_footprint -> base_link -> arm_mount_link -> arm_base_link` で接続され、車輪3関節とアーム6関節が同一ツリー内にある。

```bash
make down
```

実行後、残存コンテナはない。

## 初回確認時点で未実行だった項目

- `0-1` LiDAR回転中心の実測
- `0-2` アーム取付位置・yawの実測
- `0-3` udev `ID_SERIAL_SHORT` の2ポート比較
- `0-4` `/dev/so101_follower` のサーボIDスキャン
- 手順4以降の移動・リーチ指令

実機接続後に、上記以外の確認項目は再実行した。

## 2026-08-07 追加確認

接続・固定後に、実機を動かさず再確認した。

```text
--- /dev/lekiwi ---
NOT FOUND
--- /dev/so101_follower ---
lrwxrwxrwx 1 root root 7 Aug  7 10:30 /dev/so101_follower -> ttyACM1
DEVPATH=/devices/pci0000:00/0000:00:14.0/usb1/1-12/1-12.3/1-12.3:1.0/tty/ttyACM1
ID_VENDOR=1a86
ID_SERIAL=1a86_USB_Single_Serial_5A7A018080
ID_SERIAL_SHORT=5A7A018080
--- /dev/rplidar ---
NOT FOUND
```

生デバイス:

```text
--- /dev/ttyACM0 ---
ID_SERIAL_SHORT=5A7A017874
--- /dev/ttyACM1 ---
ID_SERIAL_SHORT=5A7A018080
--- /dev/ttyUSB0 ---
ID_SERIAL_SHORT=0001
```

属性値:

```text
ttyACM0: idVendor=1a86 idProduct=55d3 serial=5A7A017874
ttyUSB0: idVendor=10c4 idProduct=ea60 serial=0001
```

SO-101側のバス分離スキャン:

```bash
docker compose -f docker/lekiwi_so101_bringup/compose.yaml run --rm lekiwi-so101-arm python3 -c "from lerobot.motors.feetech import FeetechMotorsBus; print('スキャン結果:', FeetechMotorsBus.scan_port('/dev/so101_follower'))"
```

```text
Motors found for baudrate=1000000: {1: 777, 2: 777, 3: 777, 4: 777, 5: 777, 6: 777}
スキャン結果: {1000000: [1, 2, 3, 4, 5, 6]}
```

ID 7、8、9はSO-101側で検出されなかった。

初回確認時はホストの `/etc/udev/rules.d` に `99-so101.rules` のみ存在し、`99-lekiwi.rules` と `99-rplidar.rules` は存在しなかった。その後、ホスト側で導入・reloadされ、下記のシンボリックリンクを確認した。

## udevルール変更

`docker/lekiwi_base_ros2/99-lekiwi.rules` のLeKiwi識別を、共有VID/PIDから実測シリアル `5A7A017874` に変更した。

ホストへの導入を試みたが、sudoパスワードが必要で停止した。

```text
sudo: a password is required
```

導入に必要だったコマンド:

```bash
sudo install -m 0644 docker/lekiwi_base_ros2/99-lekiwi.rules /etc/udev/rules.d/99-lekiwi.rules
sudo install -m 0644 docker/rplidar_ros2/99-rplidar.rules /etc/udev/rules.d/99-rplidar.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

その後のudev確認:

```text
/dev/lekiwi          -> ttyACM0
/dev/so101_follower  -> ttyACM1
/dev/rplidar         -> ttyUSB0
ID_SERIAL_SHORT(lekiwi)=5A7A017874
ID_SERIAL_SHORT(rplidar)=0001
```

## 実機起動試行

旧スタックの停止済みコンテナ名が衝突したため、停止済みの `rplidar-a1` と `lekiwi-nav` を削除してから統合Composeを起動した。

```bash
docker compose -f compose.yaml up -d
docker compose exec -it lekiwi-so101-arm /entrypoint.sh \
  ros2 launch lekiwi_so101_bringup reach.launch.py \
  backend:=lerobot robot_id:=my_follower start_rviz:=false
```

Composeの3コンテナは起動した。LeRobotブリッジも一度readyになったが、状態読み取り中に停止した。

```text
[lerobot_bridge]: SO-101 bridge ready with backend=lerobot
[lerobot_bridge]: Rejected hardware command: joint positions must all be finite
[lerobot_bridge]: control cycle overran: 64.1ms > period 20.0ms
[lerobot_bridge]: SO-101 bridge fault: Failed to sync read 'Present_Position' on ids=[1, 2, 3, 4, 5, 6] after 1 tries. [TxRxResult] There is no status packet!
[ERROR] [so101_lerobot_bridge-2]: process has died ... exit code 1
```

コントローラ側では以下も観測した。

```text
Joint position is out of bounds for the joint : 'arm_shoulder_lift_joint' actual position: -1.7951958020513104 limits: [-1.74533, 1.74533]
```

実機への移動指令は送っていない。ブリッジ停止後、個別読み取りと一括読み取りを指令なしで確認した結果は次のとおり。

```text
個別Present_Position: {'shoulder_pan': -4.835164835164835, 'shoulder_lift': -102.85714285714286, 'elbow_flex': 99.82417582417582, 'wrist_flex': -97.93406593406593, 'wrist_roll': -62.72527472527472, 'gripper': 2.0026702269692924}
sync Present_Position: {'shoulder_pan': -4.835164835164835, 'shoulder_lift': -102.85714285714286, 'elbow_flex': 99.82417582417582, 'wrist_flex': -97.93406593406593, 'wrist_roll': -62.72527472527472, 'gripper': 2.0026702269692924}
```

再スキャンではサーボ6台が応答した。

```text
スキャン結果: {1000000: [1, 2, 3, 4, 5, 6]}
```

RPLIDARは正常起動し、health status `OK`、scan frequency `10.0 Hz` だった。統合スタックは `make down` で停止済み。

アーム取付位置の実測結果として、`y=0 mm`、その他の仮値は一致との報告を受けた。URDFを次へ更新した。

```text
base_link -> arm_mount_link: xyz=(0.080, 0.000, 0.057) m, rpy=(0, 0, 0)
```

更新後の `make bootstrap`:

```text
Summary: 5 packages finished [2.38s]
  3 packages had stderr output: lekiwi_so101_bringup so101_bringup so_arm_utils

== 静的検査 ==
  Python import: OK
  アーム単体 URDF: OK
  結合 URDF: OK

== 完了 ==
```

LiDARの実測値は仮値と一致したとの報告を受けた。URDFのTBD表記を実測済みに変更した。

```text
base_link -> laser_link: xyz=(0.100, 0.000, 0.030) m, rpy=(0, 0, 0)
```

更新後の `make bootstrap`:

```text
Summary: 5 packages finished [2.39s]
  3 packages had stderr output: lekiwi_so101_bringup so101_bringup so_arm_utils

== 静的検査 ==
  Python import: OK
  アーム単体 URDF: OK
  結合 URDF: OK

== 完了 ==
```

## 姿勢変更後の実機再試行

アーム姿勢を変更した後、起動前に読み取り専用で実測値を再取得した。肩リフトは約 `+5.1 deg` で、前回の範囲外状態ではなかった。

```text
個別Present_Position: {'shoulder_pan': -4.571428571428571, 'shoulder_lift': 5.0989010989010985, 'elbow_flex': 10.417582417582418, 'wrist_flex': -14.593406593406593, 'wrist_roll': 79.16483516483517, 'gripper': 2.202937249666222}
```

```bash
docker compose -f docker/lekiwi_so101_bringup/compose.yaml up -d
docker compose -f docker/lekiwi_so101_bringup/compose.yaml exec -T lekiwi-so101-arm /entrypoint.sh \
  ros2 launch lekiwi_so101_bringup reach.launch.py \
  backend:=lerobot robot_id:=my_follower start_rviz:=false
```

ブリッジは `ready` になり、前回の `There is no status packet!` による終了は再発しなかった。起動後も約2分間プロセスが継続し、アーム実測トピックを受信できた。

```text
/so101/hardware_states:
  arm_shoulder_pan_joint:  -0.07978648009116934
  arm_shoulder_lift_joint:  0.11814536475038538
  arm_elbow_flex_joint:     0.20176773330747633
  arm_wrist_flex_joint:    -0.23935944027350803
  arm_wrist_roll_joint:     1.3816870254249616
  arm_gripper_joint:        0.030640854472630173

controllers:
  gripper_controller:          active
  joint_trajectory_controller: active
  joint_state_broadcaster:     active
```

起動中に `joint positions must all be finite` と制御周期超過の警告は出たが、ブリッジのプロセス終了や通信断は確認されていない。移動・リーチ指令は送っていない。

確認後、`Ctrl+C` と `docker compose ... down` で通常停止した。停止処理中に最後の状態読み取りが1回 `There is no status packet!` になったが、Composeの停止は終了コード `0` で完了し、残存コンテナはない。

## `make reach` 修正後の実機テスト

`make reach` のGuard誤検出を修正し、Composeをバックグラウンド起動してから `reach.launch.py` を自動実行するようにした。修正後のテストではGuardを通過し、Compose 3コンテナと `reach.launch.py` の起動、ブリッジの `ready` までは確認できた。

```text
[lerobot_bridge]: SO-101 bridge ready with backend=lerobot
```

ただし、実機状態がURDF範囲外となり、アームの軌道コントローラは `unconfigured` だった。

```text
joint_trajectory_controller ... unconfigured

/so101/hardware_states:
  arm_shoulder_lift_joint:  1.813608066687734
  arm_wrist_flex_joint:    -1.6571038172781327
```

URDFの範囲はそれぞれ肩リフト `[-1.74533, 1.74533]`、手首フレックス `[-1.6, 1.6]` である。起動中は `joint positions must all be finite` が継続したため、移動指令を送らず `Ctrl+C` と `make down` で停止した。停止後の読み取りでも次を確認した。

```text
停止後Present_Position: {'shoulder_pan': 2.021978021978022, 'shoulder_lift': 103.91208791208791, 'elbow_flex': 1.89010989010989, 'wrist_flex': -94.94505494505495, 'wrist_roll': 78.72527472527473, 'gripper': 2.202937249666222}
```

現在、実機コンテナは残っていない。範囲外姿勢を手動で安全範囲へ戻すまで、`make reach` の再実行は保留する。

## `make reach` 最終確認

その後、起動前にLeRobot較正込みの読み取り専用確認を行い、次の姿勢で範囲内であることを確認した。

```text
Present_Position(calibrated): {'shoulder_pan': 13.186813186813186, 'shoulder_lift': 22.593406593406595, 'elbow_flex': 12.615384615384615, 'wrist_flex': 13.89010989010989, 'wrist_roll': 69.75824175824175, 'gripper': 1.6688918558077435}
```

修正した `make reach START_RVIZ=true` を実行した結果:

- `SO-101 bridge ready with backend=lerobot`
- RViz2起動、OpenGL 4.5確認
- `joint_state_broadcaster`、`joint_trajectory_controller`、`gripper_controller` がすべて `active`
- `/so101/hardware_states` と `/so101/hardware_commands` の全関節値が有限
- 起動前後の実測値が一致し、移動・リーチ指令は未送信

起動直後にros2_controlが出す未初期化NaNコマンドはサーボへ送らず破棄し、警告を1秒間隔に抑制した。Ctrl+C停止時にバックエンド切断競合をFATAL扱いしないようにした。モックでもRViz起動、全コントローラactive、停止処理を確認した。

変更・確認後は実機およびモックのComposeを停止・削除し、残留コンテナがない状態である。

## `make down` のトルクOFF修正と実機確認

`docker compose down` は `docker compose exec` で起動したlaunchプロセスのLeRobot切断処理を呼ばないため、`make down` に先行して呼ぶshutdownサービスを追加した。サービス応答後、ブリッジプロセスの終了を待ってからComposeを停止する。サービス未応答時はSIGINTへフォールバックする。

実機を `make reach START_RVIZ=false` で目標なし起動し、別のシェルから `make down` を実行した。

```text
response:
  std_srvs.srv.Trigger_Response(success=True, message='shutting down')

Torque_Enable(raw): {'shoulder_pan': 0, 'shoulder_lift': 0, 'elbow_flex': 0, 'wrist_flex': 0, 'wrist_roll': 0, 'gripper': 0}
```

6軸すべてトルクOFFを確認した。移動・リーチ指令は送信していない。

## LiDAR yaw変更

依頼により `laser_rpy` のyawを `-10°`（`-0.1745329252 rad`）へ変更した。

追加変更として、yawを `-7°`（`-0.1221730476 rad`）へ更新した。
