# LeKiwi + SO-101 — `map` 上の点へのリーチ

## できること

- LIDAR、wristのrealsenseカメラからの点群取得
- LIDARによるSLAM&Navigation
- `map`座標系上の点へのアームのリーチ

## 環境構築

```bash
cp .env.example .env      # ★ 先に実機に合わせて編集する
make build
make bootstrap            # ★ 初回とパッケージ追加時。colcon build --symlink-installしている
```

## 動かし方

```bash
make mock                 # 実機に触れない（Mac 可）
make reach                # 実機
```

rvizで点群の確認、navigationができる。

publish pointによりアームのリーチができる。

ros2コマンドを使う場合は
```bash
docker exec -it lekiwi-so101-arm bash
```

## 停止手順

**★ 順番を守ること。正常終了でトルクが切れてアームが落ちる。**

```bash
make stow     # 1. アームを低く畳む
make down     # 2. bridgeをshutdownしてトルクOFF後、コンテナを停止
```

### トピック

| トピック | 型 | 向き | 用途 |
| --- | --- | --- | --- |
| `/cmd_vel` | `geometry_msgs/Twist` | → ベース | 速度指令。**Nav2 の collision_monitor より下流**なので手打ちには安全機構が効かない |
| `/odom` | `nav_msgs/Odometry` | ベース → | ★ **指令値の積分**。スリップも外乱もアームの反動も現れない |
| `/scan` | `sensor_msgs/LaserScan` | LiDAR → | 生スキャン |
| `/scan_filtered` | `sensor_msgs/LaserScan` | scan_filter → | 前方 ±60° に絞ったもの。**slam と costmap はこちらを見る** |
| `/map` | `nav_msgs/OccupancyGrid` | slam → | TRANSIENT_LOCAL |
| `/goal_pose` | `geometry_msgs/PoseStamped` | → Nav2 | ナビゲーション目標。RViz の **"2D Goal Pose"** |
| `/initialpose` | `geometry_msgs/PoseWithCovarianceStamped` | → amcl | 初期姿勢。**保存地図構成でのみ存在**（SLAM 構成には無い） |
| `/plan` | `nav_msgs/Path` | Nav2 → | 大域経路 |
| `/optimal_trajectory` | `nav_msgs/Path` | MPPI → | 局所軌道。★ 他構成でよくある `/local_plan` は**この構成には無い** |
| `/local_costmap/published_footprint` | `geometry_msgs/PolygonStamped` | Nav2 → | ★ `robot_radius: 0.17` は**アームを畳んだ前提** |
| `/joint_states` | `sensor_msgs/JointState` | → RSP | ★ **publisher は 2 つ**（車輪 3 関節 / アーム 6 関節）。購読側は蓄積が要る |
| `/robot_description` | `std_msgs/String` | RSP → | ★ **publisher は 1 つでなければならない**（TRANSIENT_LOCAL / depth 1） |
| `/so101/reach_target` | `geometry_msgs/PoseStamped` | → リーチ | リーチ目標（`frame_id: map`） |
| `/clicked_point` | `geometry_msgs/PointStamped` | → リーチ | RViz の **"Publish Point"**。★ 型が違うので "2D Goal Pose" とは別物 |
| `/so101/reach_status` | `std_msgs/String` | リーチ → | 判定結果 1 行（下の表） |
| `/so101/reach_markers` | `visualization_msgs/Marker` | リーチ → | 目標球（緑 = 受理 / 赤 = 棄却） |
| `/so101/hardware_states` | `sensor_msgs/JointState` | ブリッジ → | 内部。ros2_control ↔ LeRobot |
| `/so101/hardware_commands` | `sensor_msgs/JointState` | → ブリッジ | 内部 |
| `/wrist_camera/wrist_camera/depth/color/points` | `sensor_msgs/PointCloud2` | カメラ → | 手首カメラの点群。`frame_id` は `wrist_camera_depth_optical_frame`。★ **BEST_EFFORT** |
| `/wrist_camera/wrist_camera/color/image_raw` | `sensor_msgs/Image` | カメラ → | カラー画像 |

### アクション

| アクション | 型 | 用途 |
| --- | --- | --- |
| `/navigate_to_pose` | `nav2_msgs/NavigateToPose` | **ナビゲーションの主入口** |
| `/navigate_through_poses` | `nav2_msgs/NavigateThroughPoses` | 経由点つき |
| `/follow_waypoints` | `nav2_msgs/FollowWaypoints` | ウェイポイント追従 |
| `/compute_path_to_pose` | `nav2_msgs/ComputePathToPose` | 経路計画だけ（走らない） |
| `/follow_path` | `nav2_msgs/FollowPath` | 与えた経路の追従だけ |
| `/spin` `/backup` `/drive_on_heading` `/wait` | `nav2_msgs/*` | 復帰behavior。**単体でも呼べる** |
| `/joint_trajectory_controller/follow_joint_trajectory` | `control_msgs/FollowJointTrajectory` | アーム 5 関節。リーチノードが使う |
| `/gripper_controller/gripper_cmd` | `control_msgs/ParallelGripperCommand` | グリッパ |

### サービス

| サービス | 型 | 用途 |
| --- | --- | --- |
| `/so101/stow` | `std_srvs/Trigger` | **アームを畳む。停止前に必ず** |
| `/so101/lerobot_bridge/shutdown` | `std_srvs/Trigger` | ★ **トルクOFFして終了。`make down` が先に呼ぶ**（`docker compose down` は exec したプロセスに SIGINT を届けないため） |
| `/so101/lerobot_bridge/ready` | `std_srvs/Trigger` | 起動同期用。launch が待つ |
| `/lekiwi_base_driver/recover` | `std_srvs/Trigger` | ベースドライバの復帰 |
| `/controller_manager/list_controllers` | `controller_manager_msgs/ListControllers` | コントローラの状態 |
| `/controller_manager/switch_controller` | `controller_manager_msgs/SwitchController` | 起動・停止 |
| `/joint_trajectory_controller/query_state` | `control_msgs/QueryTrajectoryState` | 軌道の内挿値を問い合わせ |

---

## CLI テストコマンド

### 0. まず健全性を見る

```bash
make check
```

`/robot_description` = **1**、`/joint_states` = **2**、コントローラ 3 つが `active`、
`map → arm_gripper_frame_link` の TF が出れば正常。

```bash
$E ros2 node list                  # ノード一覧
$E ros2 topic list                 # ★ discovery 待ちで最初は少なく出る
$E ros2 action list -t             # 型つき
$E ros2 run tf2_tools view_frames -o /tmp/frames   # TF ツリーの PDF
```

### 1. TF（すべての土台）

```bash
$E ros2 run tf2_ros tf2_echo map base_footprint          # 自己位置
$E ros2 run tf2_ros tf2_echo base_link laser_link        # 実測 (0.10, 0, 0.03) yaw −7°
$E ros2 run tf2_ros tf2_echo base_link arm_gripper_frame_link
#   ★ 全関節ゼロなら (0.471, 0.000, 0.283) になるはず
```

### 2. ベース（★ 車輪を浮かせてから）

```bash
# ★ --once は discovery 前に publisher が終わって 1 通も届かないことがある。
#   base_driver の watchdog も 0.5 秒なので、2 秒流すほうが確実。
$E ros2 topic pub -r 10 --times 20 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.05}}'

$E ros2 topic echo /odom --once
$E ros2 topic hz /joint_states
$E ros2 service call /lekiwi_base_driver/recover std_srvs/srv/Trigger '{}'
```

### 3. ナビゲーション

```bash
# トピックで送る（RViz の "2D Goal Pose" と同じ）
$E ros2 topic pub --once -w 1 /goal_pose geometry_msgs/msg/PoseStamped \
  '{header: {frame_id: map}, pose: {position: {x: 1.0, y: 0.5}, orientation: {w: 1.0}}}'

# アクションで送る（結果とフィードバックが得られる。こちらが本筋）
$N ros2 action send_goal -f /navigate_to_pose nav2_msgs/action/NavigateToPose \
  '{pose: {header: {frame_id: map}, pose: {position: {x: 1.0, y: 0.5}, orientation: {w: 1.0}}}}'

# 経路計画だけ（走らせずに到達可能かを見る）
$N ros2 action send_goal /compute_path_to_pose nav2_msgs/action/ComputePathToPose \
  '{goal: {header: {frame_id: map}, pose: {position: {x: 1.0, y: 0.5}, orientation: {w: 1.0}}}, use_start: false}'

# その場旋回だけ（復帰behavior の単体テスト）
$N ros2 action send_goal /spin nav2_msgs/action/Spin '{target_yaw: 1.57}'

$E ros2 topic echo /plan --once            # 大域経路
$E ros2 topic hz /cmd_vel                  # 走行指令が出ているか
$N ros2 lifecycle get /bt_navigator        # active でなければ経路計画も走らない
```

保存地図構成では、走らせる前に初期姿勢を与える（RViz の **"2D Pose Estimate"**）。

```bash
$E ros2 topic pub --once -w 1 /initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
  '{header: {frame_id: map}, pose: {pose: {position: {x: 0.0, y: 0.0}, orientation: {w: 1.0}}}}'
```

> ★ **SLAM 構成（`make reach`）では `/initialpose` の購読者が居ない**（amcl が動いていない）。
> `-w 1` は購読者を待つので**そのまま固まる**。保存地図構成（`make reach-with-map`）専用。

### 4. アーム（★ 🔴 実際に動く。人が立ち会うこと）

```bash
$E ros2 control list_controllers                       # 3 つが active か
$E ros2 control list_hardware_components
$E ros2 topic echo /joint_states --once

# 軌道を直接送る（リーチノードを介さない最小テスト）
$E ros2 action send_goal -f /joint_trajectory_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory \
  '{trajectory: {joint_names: [arm_shoulder_pan_joint, arm_shoulder_lift_joint,
     arm_elbow_flex_joint, arm_wrist_flex_joint, arm_wrist_roll_joint],
    points: [{positions: [0.0, 0.0, 0.5, 0.5, 0.0], time_from_start: {sec: 3}}]}}'

# グリッパ
$E ros2 action send_goal /gripper_controller/gripper_cmd \
  control_msgs/action/ParallelGripperCommand '{command: {position: [0.5]}}'
```

### 5. リーチ

```bash
# 判定を先に流しておく（VOLATILE なので後から繋ぐと取り逃す）
$E ros2 topic echo /so101/reach_status &

# 到達可能な目標
$E ros2 topic pub --once -w 1 /so101/reach_target geometry_msgs/msg/PoseStamped \
  '{header: {frame_id: map}, pose: {position: {x: 0.35, y: 0.05, z: 0.25}, orientation: {w: 1.0}}}'

# 到達不能（★ 軌道トピックに 1 件も出ないこと＝アームが動かないことを確認する）
$E ros2 topic pub --once -w 1 /so101/reach_target geometry_msgs/msg/PoseStamped \
  '{header: {frame_id: map}, pose: {position: {x: 2.0, y: 0.0, z: 0.5}, orientation: {w: 1.0}}}'
$E ros2 topic hz /joint_trajectory_controller/joint_trajectory    # 出ないのが正しい

# RViz の Publish Point と同じ経路（型が PointStamped であることに注意）
$E ros2 topic pub --once -w 1 /clicked_point geometry_msgs/msg/PointStamped \
  '{header: {frame_id: map}, point: {x: 0.30, y: -0.10, z: 0.20}}'

# 畳む（★ 停止前に必ず）
$E ros2 service call /so101/stow std_srvs/srv/Trigger '{}'
```

### 6. 手首カメラ

**点群を `map` 上に置くのに較正は要らない。** カメラは URDF で
`arm_gripper_link` に剛体固定されているので、`map → camera` は TF から出る。
RViz の Fixed Frame を `map` にして "Wrist Camera Cloud" を有効にすれば、
点群は `map` 上の正しい位置に描画される。

```bash
$E ros2 run tf2_ros tf2_echo map wrist_camera_depth_optical_frame
$E ros2 topic hz /wrist_camera/wrist_camera/depth/color/points
$E ros2 topic bw /wrist_camera/wrist_camera/depth/color/points

# ★ フレーム名が camera_link でなく wrist_camera_link になっているか
#   (camera_name がパラメータとして効いているかの検査)
$E ros2 run tf2_ros tf2_echo wrist_camera_link wrist_camera_depth_optical_frame

# ★ 腕を動かすとカメラ TF が追従することの確認
$E ros2 run tf2_ros tf2_echo map wrist_camera_link      # 動かす前後で変わる
```

> ★ **カメラが動くので、点群を使う側は TF を「メッセージのタイムスタンプ」で
> 引くこと。**最新 TF で解決すると腕の動作中に点群がずれる。RViz は正しく扱う。
>
> ★ **移動中の点群は信用しない。**深度は動くと荒れる。静止して撮ること。
>
> 実機の取り付け手順は **[`docs/wrist_camera.md`](../../docs/wrist_camera.md)**。
> ★ **無通電での保持力確認（積載重量）と干渉確認が終わるまで通電しないこと。**
>
> ★ D435i の最短測距は約 0.1〜0.2m。**手首カメラは対象に近づくので、
> リーチ目標の距離では測距範囲を下回る可能性がある**（実機で要確認）。

### 7. 故障を意図的に起こして確認する

```bash
# slam を止める -> REJECTED_STALE_TF（古い座標で黙って解かない）
$N ros2 lifecycle set /slam_toolbox deactivate

# ベースを止める -> REJECTED_STALE_ODOM
docker stop lekiwi-nav

# 誤ったフレーム -> REJECTED_WRONG_FRAME
$E ros2 topic pub --once -w 1 /so101/reach_target geometry_msgs/msg/PoseStamped \
  '{header: {frame_id: odom}, pose: {position: {x: 0.3, y: 0.0, z: 0.2}, orientation: {w: 1.0}}}'
```

---

## 状態メッセージ

`/so101/reach_status`（`std_msgs/String`）に 1 行ずつ出る。
`/so101/reach_markers` には目標球（緑 = 受理 / 赤 = 棄却）。

| コード | 意味 |
| --- | --- |
| `ACCEPTED` | 解けた。軌道を送る。`residual` は**ソルバの残差**（物理精度ではない） |
| `SUCCEEDED` | 完了。`residual_fk` は実際の関節角から順運動学で測り直した誤差 |
| `REJECTED_UNREACHABLE` | 届かない。**張り付いた関節名**が出る（「遠すぎる」と「ベースを回すべき」の区別） |
| `REJECTED_STALE_TF` | `map`→`odom` が古い。**slam_toolbox が止まっている可能性** |
| `REJECTED_STALE_ODOM` | `/odom` が古い。**ベース側が止まっている可能性**。静止確認ができないので動かさない |
| `REJECTED_NO_TF` | TF が引けない。tf2 のメッセージをそのまま出すので、どのリンクが無いか分かる |
| `REJECTED_OUT_OF_RANGE` | 明らかに遠い。200 回反復する前の安い足切り |
| `REJECTED_WRONG_FRAME` | `frame_id` が `map` でない |
| `REJECTED_BELOW_FLOOR` | 床に突っ込む。**機体そのものは守らない**（下記） |
| `REJECTED_BUSY` / `REJECTED_TOO_SOON` | 実行中 / 連打 |
| `ABORTED_BASE_MOVED` | リーチ中にベースが動いたのでアクションをキャンセルした |
| `FAILED_ACTION` | コントローラ側の失敗 |

## ★ 精度について（重要）

**数 cm ずれる。精密なリーチとして扱わないこと。**

| 区間 | 寄与 |
| --- | --- |
| `map`→`odom`（slam_toolbox） | **2〜5cm（支配的）** |
| `base_link`→`arm_mount_link` | **実測済み**（2026-08-07）。y は CAD の −0.04 ではなく 0 だった |
| `arm_mount_link`→`arm_base_link` | 恒等（実測で向きは仮定どおり） |
| アーム FK | 1〜2cm（肩で 1° = 0.35m 先で 6mm） |

`ACCEPTED` に出る `residual` は**ソルバの残差**であって物理精度ではない。

### 精度が出ないうちにデモしたい場合

ノードは TF で解決できる**任意のフレーム**を受け付ける。
`reach.yaml` の `expected_frame` を `odom` か `base_footprint` にすれば、
`map`→`odom` の誤差を回避できる（`odom`→`base_footprint` はオドメトリ積分なので
短時間なら正確）。**アームが壊れているのではなく地図がずれている**、という
切り分けにも使える。

## ★ 実機投入前に確定させること

| 項目 | 現状 |
| --- | --- |
| `laser_link` の位置 | **実測済み (0.10, 0, 0.03)、yaw = −7°**（2026-08-07） |
| `arm_mount_link` の位置と **yaw** | **実測済み (0.08, 0.00, 0.057) rpy 0**（2026-08-07）。★ CAD の y=−0.04 は誤りで、実測は **y=0** だった |
| `joint_limit_overrides` | **空。★ 実測で y=0 が確定した結果、`laser_link` (0.10, 0) と `arm_mount_link` (0.08, 0) の xy 距離は 44mm ではなく **20mm** しかない。**当初の想定より近い。**無通電でアームを手で振り、干渉する角度を調べてから埋めること |
| `stow_positions` | 実測値 `[0.0322214631, -1.7951958021, 1.7422605412, -1.7721804713, 1.3709465377]`（pan, lift, elbow, wrist_flex, wrist_roll）。グリッパは `0.0363150868`。**初回は必ず無通電で手を添え、干渉しないことを確かめること** |

手順は `docs/agent/request.md` にある。

## 故障したときに何が起きるか

| 故障 | 影響範囲 | 復帰 |
| --- | --- | --- |
| アームのブリッジが fault（シリアル異常・watchdog） | **アームだけ**。トルクが切れて脱力する。`robot_state_publisher` は生き残るので、ベースの slam / Nav2 は測位を失わない | launch を上げ直す |
| ベースのコンテナが停止 | `odom` が止まり slam が更新されない。アームの TF は残る。**リーチは `REJECTED_STALE_ODOM` で止まる** | `compose.yaml` は `restart: "no"` なので手動 |
| **アームのコンテナを再起動** | RSP が一時的に消えるため slam がスキャンを落とし、`map`→`odom` が出なくなる。**自動では戻らない**（モックで確認） | **ベース側も再起動する**必要がある |
| **カメラのコンテナが停止** | 点群が止まるだけ。TF もリーチもナビも影響を受けない（カメラは URDF 側にリンクがあるだけで、誰も購読を必須にしていない） | 手動で起動 |
| slam_toolbox が停止 | `map`→`odom` が凍る。**リーチは `REJECTED_STALE_TF` で止まる**（黙って古い座標で解かない） | slam を上げ直す |

> ★ 合成構成では `follower.launch.py` を `shutdown_on_bridge_exit:=false` で
> include している。単体アームでは既定の `true` で、ブリッジが落ちれば launch 全体が
> 止まる。合成では同じ launch service に**結合ロボット唯一の RSP** が居るため、
> そのままだとアームの故障で `base_footprint`→`laser_link` の TF まで消え、
> **別コンテナの slam と Nav2 が巻き添えで測位を失う**。

## 既知のリスク

- **⚠ リーチ中にアームが LiDAR のスキャン平面に入りうる。**
  下向き前方へ伸ばすと `scan_filter` の前方 ±60° の窓の**内側**を腕が横切り、
  slam が自分の腕を含むスキャンでマッチングして**地図が壊れる**。
  `fake_scan` では再現できない実機限定の問題
- **⚠ 転倒。** 天板 0.216m 角に対し支持多角形は車輪円（半径 0.125m）。
  アームは 0.54m まで伸びる
- **⚠ 干渉チェックが無い。** 単一 waypoint なので JTC が関節空間で補間し、
  肘が天板や LiDAR を通り抜ける経路を取りうる
- **アームの動きはオドメトリに現れない。** `base_driver` は指令値を積分しているため。
  約 0.75kg がオムニ車輪の上で振れると実際の姿勢はずれるが、
  オドメトリにも slam にも見えない
- **`nav2.yaml` の `robot_radius: 0.17` は収納状態の前提。** 走行前に stow すること


## 構成

```
        map (slam_toolbox)
         └ odom (base_driver のオドメトリ積分)
            └ base_footprint → base_link
                               ├ laser_link      ← RPLIDAR
                               └ arm_mount_link
                                  └ arm_base_link … arm_gripper_link
                                       ├ arm_gripper_frame_link  ← リーチの手先
                                       └ wrist_camera_mount_link
                                          └ wrist_camera_link  ← 手首カメラ
```

| コンテナ | イメージ | 役割 |
| --- | --- | --- |
| `lekiwi-nav` | `lekiwi-base-ros2` | base_driver, scan_filter, slam_toolbox, Nav2 |
| `rplidar-a1` | `rplidar-a1-ros2` | sllidar_node → `/scan` |
| `lekiwi-so101-arm` | `so101-ros2` | **robot_state_publisher（結合、唯一）**, LeRobot ブリッジ, ros2_control, リーチノード, **RViz（唯一）** |
| `lekiwi-wrist-camera` | `realsense-d435i-ros2` | 手首カメラ。点群 → `wrist_camera_depth_optical_frame` |


## インターフェース一覧

すべて**モックで実在を確認した**もの（`ros2 topic type` / `action list -t` / `service list -t`）。
コンテナ内で叩くので、以下は共通の前置きを使う。

```bash
E="docker exec lekiwi-so101-arm /entrypoint.sh"       # アーム側（実機）
N="docker exec lekiwi-nav /entrypoint.sh"             # ベース側（実機）

E="docker exec lekiwi-so101-arm-mock /entrypoint.sh"  # アーム側（モック）
N="docker exec lekiwi-nav-mock /entrypoint.sh"        # ベース側（モック）
```

> ★ **`/entrypoint.sh` の前置は必須。** `docker exec` は ENTRYPOINT を通らないので、
> 付けないと `ros2: executable file not found in $PATH` になる。
>
> ★ **`nav2_msgs` はベースコンテナにしか入っていない。**
> Nav2 の**アクション**（`/navigate_to_pose` など）は `$N` で叩くこと。
> `$E` で叩くと `The passed action type is invalid` になる（型を解決できないため）。
> トピック（`/goal_pose` は `geometry_msgs`）はどちらからでも叩ける。
>
> ★ **起動直後は DDS の discovery が終わっておらず、`ros2 topic list` や
> `action list` に一部しか出ない。** 30 秒ほど待つか `make check` を使うこと。