# trail_SO101

**LeKiwi 移動ベースに SO-101 アームを載せた実機ロボット**を、ROS 2 Jazzy と
lerobot で動かすリポジトリです。SLAM で地図を作り、Nav2 で走り、
`map` 上の点へアームを伸ばします。

このドキュメントは**上から順にやれば動く手順書**です。深い話は別ファイルに送ります。

## 目次

1. [マシンの分担を理解する](#1-マシンの分担を理解する) ← ★ 最初に読む
2. [リポジトリを取得する](#2-リポジトリを取得する)
3. [Docker イメージをビルドする](#3-docker-イメージをビルドする)（初回のみ・時間がかかります）
4. [ワークスペースを初期化する](#4-ワークスペースを初期化する)（初回とパッケージ追加時）
5. [実機なしで動かす](#5-実機なしで動かす)（Mac でも動きます）
6. [実機で動かす](#6-実機で動かす)（★ 安全上の注意）
7. [自分でノードを書く](#7-自分でノードを書く)

- [リポジトリ構成](#リポジトリ構成)
- [ドキュメント一覧（読む順番）](#ドキュメント一覧読む順番)

---

## 1. マシンの分担を理解する

**★ ここを飛ばすと必ず混乱します。**

| マシン | 役割 | ハードウェア |
| --- | --- | --- |
| **Mac**（開発機） | 設計・実装・**モック検証**・コミット | **無し。** Docker にシリアルデバイスを渡せません |
| **Linux PC**（`hsr-pc5`） | **実機検証のみ** | SO-101 アーム、LeKiwi ベース、RPLIDAR、RealSense |

**実機に触れるのは Linux PC だけです。** Mac 側は手順 5 までしか実行できません。

以降、コードブロックの先頭に**どこで実行するか**を書いてあります。

```bash
# Mac（開発機）          ← ホストのターミナル
# Linux PC（実機）        ← ホストのターミナル
# コンテナ内 /ros2_ws/    ← docker compose exec で入った中
```

### この機体の構成

```
        map (slam_toolbox が出す)
         └ odom (base_driver のオドメトリ積分)
            └ base_footprint → base_link
                               ├ laser_link      ← RPLIDAR A1
                               └ arm_mount_link
                                  └ arm_base_link … arm_gripper_link
                                       ├ arm_gripper_frame_link  ← リーチの手先
                                       └ wrist_camera_link       ← RealSense D435i
```

| 部位 | モータ | 電圧 | ポート |
| --- | --- | --- | --- |
| アーム | Feetech STS3215 × 6（ID 1–6） | **7.4V** | `/dev/so101_follower` |
| ホイール | Feetech STS3215 × 3（ID 7/8/9） | **12V** | `/dev/lekiwi` |
| LiDAR | RPLIDAR A1M8 | — | `/dev/rplidar` |

> ★ **アームとホイールを同じシリアルバスに繋がないこと。**
> どちらも STS3215 の 1 Mbps で ID も分かれているため**物理的には繋がってしまい**、
> 繋いだ瞬間に 12V が 7.4V のアームサーボに掛かって壊れます。

---

## 2. リポジトリを取得する

```bash
# Mac（開発機） / Linux PC（実機） どちらも
git clone git@github.com:hitoponu/trail_SO101.git
cd trail_SO101
```

**ブランチを確認してください。** 機能ごとに分かれています。

| ブランチ | 内容 |
| --- | --- |
| `main` | 統合済みの安定版 |
| `feat/single-container` | **統合スタック（`docker/robot`）。ふだんはこれ** |

```bash
git switch feat/single-container
```

---

## 3. Docker イメージをビルドする

**初回のみ。20〜40 分かかります**（約 7.9GB）。

```bash
# Mac（開発機） / Linux PC（実機）
cd docker/robot
cp .env.example .env
make build
```

**★ `.env` はここで実機に合わせて編集してください（後回しにしない）。**

```bash
# Linux PC（実機）
getent group dialout        # 出力の3番目の数字が DIALOUT_GID
ls -l /dev/lekiwi /dev/so101_follower /dev/rplidar    # 3つとも見えること
```

見えない場合は udev ルールが入っていません
（`docker/*/99-*.rules` を `/etc/udev/rules.d/` へ）。

**こう出れば成功です。**

```bash
docker images | grep lekiwi-so101
# local/lekiwi-so101   jazzy   ...   7.85GB
```

---

## 4. ワークスペースを初期化する

**★ これを飛ばすと手順 5 が必ず失敗します。**

```bash
# Mac（開発機） / Linux PC（実機）
cd docker/robot
make bootstrap
```

このイメージは ROS ワークスペースを**焼き込まず、ホストからマウント**します。
`ros2_ws/install` は `.gitignore` 済みなので `git pull` では降ってきません。
飛ばすと `Package 'lekiwi_so101_bringup' not found` になります。

**こう出れば成功です**（★ 6 行すべて `OK` であること）。

```
== 上流のバージョン ==
   ros2_so_arm: e166df9
   sllidar_ros2: 3430009

Summary: 9 packages finished

== 静的検査 ==
  Python import: OK
  ナビ・LiDAR・カメラのパッケージ: OK
  アーム単体 URDF: OK
  ベース単体 URDF: OK
  結合 URDF: OK
  launch の読み込み: OK
```

> ★ ネットワークは要りません。上流（`ros2_so_arm` / `sllidar_ros2`）は
> **イメージのビルド時に取得済み**で、ここではコピーするだけです。

---

## 5. 実機なしで動かす

**Mac でも動きます。シリアルも USB も一切開きません。**

```bash
# Mac（開発機） / Linux PC（実機）
cd docker/robot
make mock          # 前面で走ります。この端末は開いたままに
```

別のターミナルで健全性を確認します。

```bash
# Mac（開発機） / Linux PC（実機）
cd docker/robot
make check
```

**こう出れば成功です。**

```
--- /robot_description (期待: 1) ---
Publisher count: 1
--- /joint_states (期待: 2) ---
Publisher count: 2
--- controllers (期待: active 3 つ) ---
gripper_controller           ... active
joint_trajectory_controller  ... active
joint_state_broadcaster      ... active
--- ★ nav2 と ros2_control の action が同時に見えること ---
/joint_trajectory_controller/follow_joint_trajectory
/navigate_to_pose
--- map -> arm_gripper_frame_link ---
- Translation: [0.471, -0.000, 0.315]
```

> ★ 最後の TF の数値は**アームの姿勢によって変わります**。合格条件は
> 「`★ ... が引けない` ではなく数値が出ること」です。
> 上の値は全関節ゼロのときのものです。

### 動かしてみる

```bash
# コンテナ内。まず入る
docker compose -f compose.mock.yaml exec -it robot-mock bash
```

```bash
# コンテナ内 /ros2_ws/
# ① リーチの結果を流しておく
ros2 topic echo /so101/reach_status &

# ② map 上の点へアームを伸ばす
ros2 topic pub --once -w 1 /so101/reach_target geometry_msgs/msg/PoseStamped \
  '{header: {frame_id: map}, pose: {position: {x: 0.35, y: 0.05, z: 0.25}, orientation: {w: 1.0}}}'
#    -> ACCEPTED ... -> SUCCEEDED

# ③ ナビゲーションのゴールを与える
ros2 action send_goal -f /navigate_to_pose nav2_msgs/action/NavigateToPose \
  '{pose: {header: {frame_id: map}, pose: {position: {x: 0.8, y: 0.3}, orientation: {w: 1.0}}}}'
```

**停止**は `make mock` の端末で `Ctrl+C` → `make down`。

> ★ **モックで確認できないこと**: サーボのトルクと PID、実オドメトリの滑り、
> 実スキャンの形、USB の列挙、12V/7.4V の分離、干渉、RealSense の点群。

他に何が叩けるかは [`docs/interfaces.md`](docs/interfaces.md) にあります。

---

## 6. 実機で動かす

> ## ★ 先に読んでください
>
> **「止める」＝「アームが落ちる」です。**
>
> | 場面 | 何が起きるか |
> | --- | --- |
> | `make run` の**起動直後** | ★ **一瞬トルクが抜けます**。人が支えてください |
> | launch を `Ctrl+C` | トルク OFF → **落ちます**。ホイールは停止 |
> | **`docker kill`（使わないこと）** | アームは凍り、**ホイールは最後の指令速度で回り続けます** |
>
> **★ 非常停止は物理スイッチだけです。** `docker kill` は使えません
> （1 コンテナなのでベースのドライバも道連れになり、機体が走り去ります）。
>
> 起動前に確認: **アームの周囲 35cm が空いているか / 人が手を添えているか /
> 電源スイッチに手が届くか / 車輪を浮かせるか**。

```bash
# Linux PC（実機）
cd docker/robot
make run BACKEND=lerobot ROBOT_ID=my_follower
```

`ROBOT_ID` は LeRobot の較正 ID です。実物はここで確認できます。

```bash
# Linux PC（実機）
ls ~/.cache/huggingface/lerobot/calibration/robots/so_follower/
```

### 停止手順（★ 順番を守ること）

```bash
# ① Linux PC（実機）— 別ターミナル
cd docker/robot && make stow      # アームを低く畳む

# ② 人がアームを支える

# ③ make run の端末で Ctrl+C     ← ここでトルクが切れる

# ④ アームが静止してから手を放す

# ⑤ Linux PC（実機）
make down
```

### 異常終了したとき（SIGKILL / OOM / コンテナ強制削除）

停止処理が走らなかった場合、**サーボは指令を保持したままです。**

**★ コンテナを落とす必要はありません。** 止まっている必要があるのは launch だけです。

```bash
# Linux PC（実機）
cd docker/robot
make release-check    # 読むだけ。いまトルクが入っているか確認
make release          # ★ アームもホイールもこれ 1 つで解放（★ アームが落ちます）
make release-wheels   # ホイールだけ止める（アームは落ちない）
```

> ★ launch がまだ生きている場合は、**どのプロセスがポートを掴んでいるかを
> 名指しして中止します**。その場合は先に launch を `Ctrl+C` してください。

詳細は [`docker/robot/README.md`](docker/robot/README.md)。

### 保存した地図で走る

SLAM で走り回ったあと、地図を保存できます。

```bash
# Linux PC（実機）— 別ターミナル
cd docker/robot
make save-map MAP_NAME=my_room       # -> $MAP_DIR/my_room.yaml と .pgm
```

> ★ **`make save-map` は実機構成でしか動きません。** `map_saver_server` を
> 起動しているのは `nav.launch.py`（実機）だけで、`sim_nav.launch.py`（`sim:=true`）
> には入っていません。

次回からは SLAM の代わりに保存地図 + AMCL で走れます。`make run` は
この引数を渡さないので、launch を直接叩きます。

```bash
# Linux PC（実機）
make up
docker compose -f compose.yaml exec -it robot /entrypoint.sh \
  ros2 launch lekiwi_so101_bringup robot.launch.py \
    backend:=lerobot robot_id:=my_follower \
    use_saved_map:=true map_file:=/maps/my_room.yaml
```

★ AMCL は起動直後に自己位置が未確定です。RViz の **"2D Pose Estimate"** で
初期位置を与えてから走らせてください。

---

## 7. 自分でノードを書く

```bash
# コンテナ内 /ros2_ws/src/
ros2 pkg create --build-type ament_python --license Apache-2.0 \
  --node-name hello my_first_pkg
```

```bash
# コンテナ内 /ros2_ws/
colcon build --symlink-install --packages-select my_first_pkg
source install/setup.bash
ros2 run my_first_pkg hello
#    -> Hi from my_first_pkg.
```

**★ `make bootstrap` を打ち直せば、以降は自動でビルド対象に入ります。**

ノードの書き方、QoS の罠、テストの書き方、つまずきポイント集は
**[`docs/development.md`](docs/development.md)** にまとめてあります。

---

## リポジトリ構成

```
trail_SO101/
├── docker/
│   ├── robot/                  ★ 統合スタック。ふだん使うのはこれだけ
│   │   ├── Dockerfile          1 イメージ（ROS + Nav2 + LeRobot + RealSense）
│   │   ├── compose.yaml        1 コンテナ（実機）
│   │   ├── compose.mock.yaml   1 コンテナ（実機に触れない）
│   │   ├── bootstrap.sh        上流の配置 + colcon build + 静的検査
│   │   └── Makefile            build / bootstrap / run / mock / check / release
│   ├── so101_ros2/             以下は 1 サブシステムだけ切り分けたいとき用
│   ├── lekiwi_base_ros2/
│   ├── rplidar_ros2/
│   ├── realsense_ros2/
│   └── lekiwi_so101_bringup/   旧 4 コンテナ構成
├── ros2_ws/src/
│   ├── so101_bringup/          アーム。LeRobot ブリッジ、リーチ、逆運動学
│   ├── lekiwi_base_bringup/    ベース。ドライバ、オドメトリ、スキャン処理
│   ├── lekiwi_so101_bringup/   合成のみ。結合 URDF、robot.launch.py、release_all
│   ├── lekiwi_description/     ベースの URDF
│   ├── rplidar_bringup/        LiDAR
│   └── realsense_bringup/      カメラ
├── examples/                   ROS 2 を使わない lerobot 直叩き（+ SO101 モデル）
└── docs/                       ドキュメント
```

> ★ `ros2_ws/src/ros2_so_arm` と `ros2_ws/src/sllidar_ros2` は**上流**で、
> `.gitignore` 済みです。`make bootstrap` がイメージから配置します。

---

## ドキュメント一覧（読む順番）

| # | ドキュメント | 内容 |
| --- | --- | --- |
| 1 | **この README** | 起動までの手順 |
| 2 | [`docs/interfaces.md`](docs/interfaces.md) | **Topic / Service / Action の一覧と CLI テスト** |
| 3 | [`docs/internals.md`](docs/internals.md) | **内部処理の仕組み。** 指令がどこを通るか |
| 4 | [`docs/development.md`](docs/development.md) | ノードの書き方、つまずきポイント集 |
| 5 | [`docker/robot/README.md`](docker/robot/README.md) | 停止・非常停止・異常終了からの復帰 |

必要になったときに読むもの:

| ドキュメント | 内容 |
| --- | --- |
| [`docs/tf_reliability.md`](docs/tf_reliability.md) | **TF のどこが信用できないか。** 精度で悩んだら |
| [`docs/lekiwi_so101_reach.md`](docs/lekiwi_so101_reach.md) | リーチの設計と精度（数 cm ずれる理由） |
| [`docs/wrist_camera.md`](docs/wrist_camera.md) | 手首カメラの取り付けと較正 |
| [`docs/lerobot_examples.md`](docs/lerobot_examples.md) | ROS 2 を使わない lerobot 直叩き |
| [`docs/hardware_agent.md`](docs/hardware_agent.md) | 実機を触る担当者への指示 |

---

## Requirements

| 項目 | |
| --- | --- |
| ROS 2 | Jazzy（コンテナ内。ホストへの導入は不要） |
| Docker | 最新安定版。Mac は Docker Desktop |
| ディスク | イメージに約 8GB |
| 実機を繋ぐ側 | **Linux 必須**（macOS の Docker はシリアル/USB を渡せません） |

## 参考リンク

- [ROS 2 Jazzy 公式ドキュメント](https://docs.ros.org/en/jazzy/index.html)
- [Nav2 ドキュメント](https://docs.nav2.org/)
- [ros2_control ドキュメント](https://control.ros.org/jazzy/index.html)
- [LeRobot](https://github.com/huggingface/lerobot)
