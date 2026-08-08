# インターフェース一覧 — Topic / Service / Action

統合スタック（`docker/robot`）で使えるものの一覧です。
**★ ここに載っているものは、すべてモック構成で実在を確認しています**
（`ros2 topic list -t` / `service list -t` / `action list -t`）。

- 使い方の手順は [`../README.md`](../README.md)
- 中で何が起きているかは [`internals.md`](internals.md)

## 前置き

コンテナの中で叩きます。以降 `$E` は次の意味です。

```bash
# Linux PC（実機）
E="docker compose -f docker/robot/compose.yaml exec robot /entrypoint.sh"

# Mac / 実機なし
E="docker compose -f docker/robot/compose.mock.yaml exec robot-mock /entrypoint.sh"
```

> ★ **`/entrypoint.sh` の前置きは必須。** `docker exec` は ENTRYPOINT を通らないので、
> 付けないと `ros2: executable file not found in $PATH` になります。
> 対話シェル（`docker compose exec -it robot bash`）なら `.bashrc` が
> source するので不要です。
>
> ★ **起動直後は DDS の discovery が終わっておらず、`ros2 topic list` に
> 一部しか出ません。** 30 秒ほど待つか `make check` を使ってください。
>
> ★ 4 コンテナ構成のころは「Nav2 のアクションはベースのコンテナで叩くこと」
> という制約がありましたが、**統合後は不要**です。`nav2_msgs` も `control_msgs` も
> 同じイメージに入っているので、どのコマンドも同じ前置きで叩けます。

---

## まずこれだけ — よく使う 10 個

| # | 名前 | 種別 | 何ができるか |
| --- | --- | --- | --- |
| 1 | `/clicked_point` | Topic | **RViz の "Publish Point" でアームを伸ばす**。いちばん簡単な入口 |
| 2 | `/so101/reach_status` | Topic | リーチの結果が 1 行で出る。**まずこれを流しておく** |
| 3 | `/goal_pose` | Topic | **RViz の "2D Goal Pose" で走らせる** |
| 4 | `/navigate_to_pose` | Action | ナビゲーションの本筋。結果とフィードバックが得られる |
| 5 | `/cmd_vel` | Topic | 速度指令を直接。★ 安全機構より下流（後述） |
| 6 | `/odom` | Topic | 自己位置（★ 指令値の積分。実測ではない） |
| 7 | `/scan_filtered` | Topic | 前方 ±60° のスキャン。**SLAM と costmap はこちらを見る** |
| 8 | `/map` | Topic | SLAM が作った地図 |
| 9 | `/so101/stow` | Service | **アームを畳む。停止前に必ず** |
| 10 | `/joint_trajectory_controller/follow_joint_trajectory` | Action | アームの関節を直接動かす |

---

## トピック

### ベース（走行）

| トピック | 型 | 向き | 用途・注意 |
| --- | --- | --- | --- |
| `/cmd_vel` | `geometry_msgs/Twist` | → ベース | 速度指令。**★ Nav2 の `collision_monitor` より下流**なので、手打ちすると安全機構が効きません |
| `/cmd_vel_nav` | `geometry_msgs/Twist` | Nav2 → | Nav2 の生の出力。`velocity_smoother` が受ける |
| `/cmd_vel_smoothed` | `geometry_msgs/Twist` | smoother → | 加減速を丸めたもの。`collision_monitor` が受ける |
| `/odom` | `nav_msgs/Odometry` | ベース → | ★ **送った指令値の積分**。スリップも外乱もアームの反動も現れません |
| `/joint_states` | `sensor_msgs/JointState` | → RSP | ★ **publisher は 2 つ**（車輪 3 関節 / アーム 6 関節）。購読側は複数メッセージにまたがって蓄積が要ります |

### センサ

| トピック | 型 | 向き | 用途・注意 |
| --- | --- | --- | --- |
| `/scan` | `sensor_msgs/LaserScan` | LiDAR → | 生スキャン（`sim:=true` では `fake_scan` が出す） |
| `/scan_filtered` | `sensor_msgs/LaserScan` | scan_filter → | 前方 ±60° に絞ったもの。**slam_toolbox も costmap もこちらを購読** |
| `/fake_scan/world` | `visualization_msgs/MarkerArray` | fake_scan → | `sim:=true` のときの仮想の部屋。RViz で見える |

### ナビゲーション

| トピック | 型 | 向き | 用途・注意 |
| --- | --- | --- | --- |
| `/goal_pose` | `geometry_msgs/PoseStamped` | → Nav2 | 目標。RViz の **"2D Goal Pose"** |
| `/map` | `nav_msgs/OccupancyGrid` | SLAM → | TRANSIENT_LOCAL |
| `/plan` | `nav_msgs/Path` | Nav2 → | 大域経路 |
| `/optimal_trajectory` | `nav_msgs/Path` | MPPI → | 局所軌道。★ 他構成でよくある `/local_plan` は**この構成には存在しません** |
| `/local_costmap/costmap` `/global_costmap/costmap` | `nav_msgs/OccupancyGrid` | Nav2 → | コストマップ |
| `/local_costmap/published_footprint` | `geometry_msgs/PolygonStamped` | Nav2 → | ★ `robot_radius: 0.17` は**アームを畳んだ前提** |
| `/initialpose` | `geometry_msgs/PoseWithCovarianceStamped` | → amcl | ★ **`use_saved_map:=true` のときだけ存在**。SLAM 構成には居ません |

### アーム・リーチ

| トピック | 型 | 向き | 用途・注意 |
| --- | --- | --- | --- |
| `/so101/reach_target` | `geometry_msgs/PoseStamped` | → リーチ | リーチ目標（`frame_id: map`） |
| `/clicked_point` | `geometry_msgs/PointStamped` | → リーチ | RViz の **"Publish Point"**。★ 型が違うので "2D Goal Pose" とは別物 |
| `/so101/reach_status` | `std_msgs/String` | リーチ → | 判定結果 1 行（下の表） |
| `/so101/reach_markers` | `visualization_msgs/Marker` | リーチ → | 目標球（**緑 = 受理 / 赤 = 棄却**） |
| `/joint_trajectory_controller/joint_trajectory` | `trajectory_msgs/JointTrajectory` | → JTC | 軌道を直接。**到達不能時にここへ 1 件も出ないこと**が「動かない」の確認になります |
| `/robot_description` | `std_msgs/String` | RSP → | ★ **publisher は 1 つでなければなりません**（TRANSIENT_LOCAL / depth 1） |

### 手首カメラ（★ 実機のみ。`sim:=true` では出ません）

| トピック | 型 | 用途・注意 |
| --- | --- | --- |
| `/wrist_camera/wrist_camera/depth/color/points` | `sensor_msgs/PointCloud2` | 点群。`frame_id` は `wrist_camera_depth_optical_frame`。★ **BEST_EFFORT** |
| `/wrist_camera/wrist_camera/color/image_raw` | `sensor_msgs/Image` | カラー画像 |

### 内部用（ふだん触らない）

| トピック | 型 | 用途 |
| --- | --- | --- |
| `/so101/hardware_states` | `sensor_msgs/JointState` | ブリッジ → ros2_control。★ BEST_EFFORT |
| `/so101/hardware_commands` | `sensor_msgs/JointState` | ros2_control → ブリッジ |
| `/dynamic_joint_states` | `control_msgs/DynamicJointState` | ros2_control の内部状態 |

---

## アクション

| アクション | 型 | 用途 |
| --- | --- | --- |
| `/navigate_to_pose` | `nav2_msgs/NavigateToPose` | **ナビゲーションの主入口** |
| `/navigate_through_poses` | `nav2_msgs/NavigateThroughPoses` | 経由点つき |
| `/follow_waypoints` | `nav2_msgs/FollowWaypoints` | ウェイポイント追従 |
| `/compute_path_to_pose` | `nav2_msgs/ComputePathToPose` | **経路計画だけ（走らない）**。到達可能かの確認に便利 |
| `/follow_path` | `nav2_msgs/FollowPath` | 与えた経路の追従だけ |
| `/spin` `/backup` `/drive_on_heading` `/wait` | `nav2_msgs/*` | 復帰 behavior。**単体でも呼べます** |
| `/joint_trajectory_controller/follow_joint_trajectory` | `control_msgs/FollowJointTrajectory` | アーム 5 関節。リーチノードが使います |
| `/gripper_controller/gripper_cmd` | `control_msgs/ParallelGripperCommand` | グリッパ |

> このほか `/dock_robot` `/undock_robot` `/compute_route` などが Nav2 から出ていますが、
> この機体では使っていません（ドックもルートグラフも設定していないため）。

---

## サービス

| サービス | 型 | 用途 |
| --- | --- | --- |
| `/so101/stow` | `std_srvs/Trigger` | **アームを畳む。停止前に必ず** |
| `/so101/lerobot_bridge/ready` | `std_srvs/Trigger` | 起動同期用。launch が待ちます |
| `/so101/lerobot_bridge/shutdown` | `std_srvs/Trigger` | トルク OFF して終了 |
| `/lekiwi_base_driver/recover` | `std_srvs/Trigger` | ベースの過負荷ラッチ解除 + 速度モード再設定 |
| `/controller_manager/list_controllers` | `controller_manager_msgs/ListControllers` | コントローラの状態 |
| `/controller_manager/switch_controller` | `controller_manager_msgs/SwitchController` | 起動・停止 |
| `/joint_trajectory_controller/query_state` | `control_msgs/QueryTrajectoryState` | 軌道の内挿値 |
| `/slam_toolbox/save_map` | `slam_toolbox/SaveMap` | 地図保存（`make save-map` が使うのは `/map_saver/save_map`） |
| `/slam_toolbox/reset` | `slam_toolbox/Reset` | 地図を作り直す |
| `/global_costmap/clear_entirely_global_costmap` | `nav2_msgs/ClearEntireCostmap` | コストマップに幻の障害物が焼き付いたとき |

---

## リーチの状態メッセージ

`/so101/reach_status`（`std_msgs/String`）に 1 行ずつ出ます。

```
ACCEPTED   target=map(0.350,0.050,0.250) arm_base_link(0.270,0.050,0.161) iters=9 residual=0.0042 dur=1.3
SUCCEEDED  residual_fk=0.0042
REJECTED_OUT_OF_RANGE range=1.963m > max_reach_radius=0.55m
```

| コード | 意味 |
| --- | --- |
| `ACCEPTED` | 解けた。軌道を送ります。`residual` は**ソルバの残差**（物理精度ではない） |
| `SUCCEEDED` | 完了。`residual_fk` は実際の関節角から順運動学で測り直した誤差 |
| `REJECTED_UNREACHABLE` | 届かない。**張り付いた関節名**が出るので「遠すぎる」と「ベースを回すべき」を区別できます |
| `REJECTED_OUT_OF_RANGE` | 明らかに遠い。200 回反復する前の安い足切り |
| `REJECTED_WRONG_FRAME` | `frame_id` が `map` でない（RViz の Fixed Frame が `odom` だった事故を捕まえます） |
| `REJECTED_NO_TF` | TF が引けない。tf2 のメッセージをそのまま出します |
| `REJECTED_STALE_TF` | `map`→`odom` が古い。**slam_toolbox が止まっている可能性** |
| `REJECTED_STALE_ODOM` | `/odom` が古い。**ベース側が止まっている可能性** |
| `REJECTED_BELOW_FLOOR` | 床に突っ込む |
| `REJECTED_BUSY` / `REJECTED_TOO_SOON` | 実行中 / 連打 |
| `ABORTED_BASE_MOVED` | リーチ中にベースが動いたのでキャンセルしました |
| `FAILED_ACTION` | コントローラ側の失敗 |

---

## CLI テストコマンド

### 0. まず健全性を見る

```bash
# Mac / Linux PC のホスト側、docker/robot で
make check
```

`/robot_description` = **1**、`/joint_states` = **2**、コントローラ 3 つが `active`、
`/navigate_to_pose` と `follow_joint_trajectory` が**両方**見えれば正常です。

```bash
$E ros2 node list
$E ros2 topic list -t                              # ★ discovery 待ちで最初は少なく出ます
$E ros2 run tf2_tools view_frames -o /tmp/frames    # TF ツリーの PDF
```

### 1. TF（すべての土台）

```bash
$E ros2 run tf2_ros tf2_echo map base_footprint            # 自己位置
$E ros2 run tf2_ros tf2_echo base_link laser_link          # 実測 (0.10, 0, 0.03) yaw −7°
$E ros2 run tf2_ros tf2_echo base_link arm_gripper_frame_link
#   ★ 全関節ゼロなら (0.471, 0.000, 0.283) になるはず
```

### 2. ベース（★ 車輪を浮かせてから）

```bash
# ★ --once は discovery 前に publisher が終わって 1 通も届かないことがあります。
#   base_driver の watchdog も 0.5 秒なので、2 秒流すほうが確実です。
$E ros2 topic pub -r 10 --times 20 /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.05}}'

$E ros2 topic echo /odom --once
$E ros2 service call /lekiwi_base_driver/recover std_srvs/srv/Trigger '{}'
```

### 3. ナビゲーション

```bash
# トピックで送る（RViz の "2D Goal Pose" と同じ）
$E ros2 topic pub --once -w 1 /goal_pose geometry_msgs/msg/PoseStamped \
  '{header: {frame_id: map}, pose: {position: {x: 1.0, y: 0.5}, orientation: {w: 1.0}}}'

# アクションで送る（結果とフィードバックが得られる。こちらが本筋）
$E ros2 action send_goal -f /navigate_to_pose nav2_msgs/action/NavigateToPose \
  '{pose: {header: {frame_id: map}, pose: {position: {x: 1.0, y: 0.5}, orientation: {w: 1.0}}}}'

# 経路計画だけ（走らせずに到達可能かを見る）
$E ros2 action send_goal /compute_path_to_pose nav2_msgs/action/ComputePathToPose \
  '{goal: {header: {frame_id: map}, pose: {position: {x: 1.0, y: 0.5}, orientation: {w: 1.0}}}, use_start: false}'

$E ros2 topic echo /plan --once
$E ros2 lifecycle get /bt_navigator        # active でなければ経路計画も走りません
```

### 4. アーム（★ 🔴 実際に動きます。人が立ち会うこと）

```bash
$E ros2 control list_controllers          # 3 つが active か
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
# 判定を先に流しておく（VOLATILE なので後から繋ぐと取り逃します）
$E ros2 topic echo /so101/reach_status &

# 到達可能な目標
$E ros2 topic pub --once -w 1 /so101/reach_target geometry_msgs/msg/PoseStamped \
  '{header: {frame_id: map}, pose: {position: {x: 0.35, y: 0.05, z: 0.25}, orientation: {w: 1.0}}}'

# 到達不能（★ 軌道トピックに 1 件も出ないこと＝アームが動かないことを確認）
$E ros2 topic pub --once -w 1 /so101/reach_target geometry_msgs/msg/PoseStamped \
  '{header: {frame_id: map}, pose: {position: {x: 2.0, y: 0.0, z: 0.5}, orientation: {w: 1.0}}}'
$E ros2 topic hz /joint_trajectory_controller/joint_trajectory    # 出ないのが正しい

# RViz の Publish Point と同じ経路（型が PointStamped であることに注意）
$E ros2 topic pub --once -w 1 /clicked_point geometry_msgs/msg/PointStamped \
  '{header: {frame_id: map}, point: {x: 0.30, y: -0.10, z: 0.20}}'

# 畳む（★ 停止前に必ず）
$E ros2 service call /so101/stow std_srvs/srv/Trigger '{}'
```

### 6. 手首カメラ（実機のみ）

```bash
$E ros2 run tf2_ros tf2_echo map wrist_camera_depth_optical_frame
$E ros2 topic hz /wrist_camera/wrist_camera/depth/color/points

# ★ フレーム名が camera_link でなく wrist_camera_link になっているか
$E ros2 run tf2_ros tf2_echo wrist_camera_link wrist_camera_depth_optical_frame
```

**点群を `map` 上に置くのに較正は要りません。** カメラは URDF で `arm_gripper_link` に
剛体固定されているので、`map → camera` は TF から出ます。詳細は
[`wrist_camera.md`](wrist_camera.md)。

### 7. 故障を意図的に起こして確認する

```bash
# slam を止める -> REJECTED_STALE_TF（古い座標で黙って解かない）
$E ros2 lifecycle set /slam_toolbox deactivate

# 誤ったフレーム -> REJECTED_WRONG_FRAME
$E ros2 topic pub --once -w 1 /so101/reach_target geometry_msgs/msg/PoseStamped \
  '{header: {frame_id: odom}, pose: {position: {x: 0.3, y: 0.0, z: 0.2}, orientation: {w: 1.0}}}'
```

---

## 関連

| 知りたいこと | どこ |
| --- | --- |
| 起動から停止までの手順 | [`../README.md`](../README.md) |
| 中で何が起きているか | [`internals.md`](internals.md) |
| 自分でノードを書く | [`development.md`](development.md) |
| TF のどこが信用できないか | [`tf_reliability.md`](tf_reliability.md) |
| リーチの精度 | [`lekiwi_so101_reach.md`](lekiwi_so101_reach.md) |
| 停止・非常停止・異常終了からの復帰 | [`../docker/robot/README.md`](../docker/robot/README.md) |
| launch が落ちたときの復帰 | `make release`（コンテナは落とさなくてよい） |
