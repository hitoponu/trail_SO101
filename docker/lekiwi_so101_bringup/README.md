# LeKiwi + SO-101 — `map` 上の点へのリーチ

LeKiwi 移動ベースに SO-101 アームを載せ、**`map` 座標系に固定された点へ手先を伸ばす**構成。

## できること・できないこと

- **アームのリーチだけ。** 目標が届かなければ**警告して何もしない**。
  ベースは動かさない（ノードは `/cmd_vel` の publisher を一切作らない）
- 精度は**数 cm**。ソルバの許容差 5mm とは別物（後述）

## 構成

```
        map (slam_toolbox)
         └ odom (base_driver のオドメトリ積分)
            └ base_footprint → base_link
                               ├ laser_link      ← RPLIDAR
                               └ arm_mount_link
                                  └ arm_base_link … arm_gripper_frame_link
```

| コンテナ | イメージ | 役割 |
| --- | --- | --- |
| `lekiwi-nav` | `lekiwi-base-ros2` | base_driver, scan_filter, slam_toolbox, Nav2 |
| `rplidar-a1` | `rplidar-a1-ros2` | sllidar_node → `/scan` |
| `lekiwi-so101-arm` | `so101-ros2` | **robot_state_publisher（結合、唯一）**, LeRobot ブリッジ, ros2_control, リーチノード, **RViz（唯一）** |

### なぜ 3 コンテナなのか

2 つのサブシステムで**安全論理が逆**だから。

| | 正常停止 (SIGINT) | SIGKILL |
| --- | --- | --- |
| アーム | トルク OFF → **落ちる** | 保持 → 凍る |
| ベース | 停止 → 安全 | **最後の指令速度で回り続ける** |

`stop_signal` / `stop_grace_period` はサービス単位にしか設定できない。

### なぜ RSP がアームのコンテナにあるのか

結合 URDF は `lekiwi_description` と `so_arm101_description` の**両方**を必要とし、
両方を `$(find)` できるのはこのイメージだけ（xacro の `$(find)` はローカルの
ファイルシステムを見るので DDS では橋渡しできない）。

`/robot_description` は TRANSIENT_LOCAL / depth 1 なので、publisher が 2 つあると
後から繋いだ購読者がどちらの latch を掴むか非決定になる。だから
ベース側は `start_robot_state_publisher:=false` で起動する。

## 使い方

```bash
cp .env.example .env      # ★ 先に実機に合わせて編集する
make build

make mock                 # 実機に触れない（Mac 可）
make reach                # 実機
```

別ターミナルから目標を与える。

```bash
docker exec lekiwi-so101-arm /entrypoint.sh \
  ros2 topic pub --once /so101/reach_target geometry_msgs/msg/PoseStamped \
    '{header: {frame_id: map}, pose: {position: {x: 0.35, y: 0.05, z: 0.25}, orientation: {w: 1.0}}}'

docker exec lekiwi-so101-arm /entrypoint.sh ros2 topic echo /so101/reach_status
```

RViz の **"Publish Point"** ツールでも指定できる。

> ★ RViz の **Fixed Frame を `map`** にすること。Publish Point は Fixed Frame の
> 座標で publish するので、`odom` のままだと `REJECTED_WRONG_FRAME` になる。
>
> ★ Publish Point が出すのは `PointStamped` であって `PoseStamped` ではない
> （`PoseStamped` を出すのは "2D Goal Pose" で、そちらは Nav2 が使っている）。
> ノードは両方の型を購読しているので、remap は不要。

## 停止手順

**★ 順番を守ること。正常終了でトルクが切れてアームが落ちる。**

```bash
make stow     # 1. アームを低く畳む
make down     # 2. コンテナを停止
```

## 状態メッセージ

`/so101/reach_status`（`std_msgs/String`）に 1 行ずつ出る。
`/so101/reach_markers` には目標球（緑 = 受理 / 赤 = 棄却）。

| コード | 意味 |
| --- | --- |
| `ACCEPTED` | 解けた。軌道を送る。`residual` は**ソルバの残差**（物理精度ではない） |
| `SUCCEEDED` | 完了。`residual_fk` は実際の関節角から順運動学で測り直した誤差 |
| `REJECTED_UNREACHABLE` | 届かない。**張り付いた関節名**が出る（「遠すぎる」と「ベースを回すべき」の区別） |
| `REJECTED_STALE_TF` | `map`→`odom` が古い。**slam_toolbox が止まっている可能性** |
| `REJECTED_NO_TF` | TF が引けない。tf2 のメッセージをそのまま出すので、どのリンクが無いか分かる |
| `REJECTED_OUT_OF_RANGE` | 明らかに遠い。200 回反復する前の安い足切り |
| `REJECTED_WRONG_FRAME` | `frame_id` が `map` でない |
| `REJECTED_BELOW_FLOOR` | 床や天板に突っ込む |
| `REJECTED_BUSY` / `REJECTED_TOO_SOON` | 実行中 / 連打 |
| `ABORTED_BASE_MOVED` | リーチ中にベースが動いたのでアクションをキャンセルした |
| `FAILED_ACTION` | コントローラ側の失敗 |

## ★ 精度について（重要）

**数 cm ずれる。精密なリーチとして扱わないこと。**

| 区間 | 寄与 |
| --- | --- |
| `map`→`odom`（slam_toolbox） | **2〜5cm（支配的）** |
| `base_link`→`arm_mount_link` | ±5mm（CAD 由来、**未実測**） |
| `arm_mount_link`→`arm_base_link` | **未検証。yaw が 90° 違う可能性もある** |
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
| `laser_link` の位置 | **TBD 仮値 (0.10, 0, 0.03)。** xy が違うと回転時のてこ比として効き、地図が向き依存で歪む。その誤差がそのまま手先に乗る |
| `arm_mount_link` の位置と **yaw** | CAD 由来で未実測。RViz でマゼンタのマーカーとして見える |
| `joint_limit_overrides` | **空。** `laser_link` と `arm_mount_link` は xy で **44mm** しか離れていない。無通電でアームを手で振り、干渉する角度を調べてから埋めること |
| `stow_positions` | 仮値。実機で低く畳んだ姿勢を測ること |

手順は `docs/agent/request.md` にある。

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
