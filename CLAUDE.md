# trail_SO101

SO-101 アームと LeKiwi 移動ベースを lerobot と ROS 2 で動かすリポジトリ。

## マシンの分担

| マシン | 役割 | ハードウェア |
| --- | --- | --- |
| **Mac**（開発機） | 設計・実装・モック検証・コミット | **無し**。Docker にシリアルデバイスを渡せない |
| **Linux PC**（`hsr-pc5`） | **実機検証のみ** | SO-101 アーム（`/dev/so101_follower`）、LeKiwi ベース（`/dev/lekiwi`）、RPLIDAR A1M8 |

**実機に触れるのは Linux PC だけ。** Mac 側は mock backend までしか検証できない。
Linux PC 側で作業する agent は `docs/hardware_agent.md` を必ず読むこと。
依頼と報告のやり取りは `docs/agent/`（`request.md` は Mac が書き、`report.md` は Linux が書く）。

## ブランチ

| ブランチ | 内容 |
| --- | --- |
| `feat/so101-follower-ros2` | SO-101 アーム。`JointStateTopicSystem` + LeRobot ROS ブリッジ |
| `feat/lekiwi-base-ros2` | LeKiwi ベース。3輪オムニ、自作 rclpy ドライバ |
| `feat/lekiwi-nav2-slam` | 上記ベース + RPLIDAR + slam_toolbox + Nav2 |
| `feat/lekiwi-so101-reach` | **統合ブランチ**。nav2-slam から分岐し so101 をマージ。`map` 上の点へアームでリーチ |
| `feat/wrist-camera` | 上記から分岐。RealSense を**アームの手首に**載せ、点群を `map` 上に置く（較正不要。TF から出る） |

前3つは `main` から分岐。`README.md` / `.dockerignore` / `.gitignore` で軽く衝突する
（`ros2_ws/src/` と `docker/` は不干渉なので、衝突するのは常にこの3つだけ）。

## 実際に踏んだ地雷（繰り返さないこと）

- **`docker compose exec` は ENTRYPOINT を通らない。**
  `ros2` が PATH に無い。`/entrypoint.sh` を前置する。
  `docker compose run` / `up` は通るので前置不要。
- **`docker/` 以下は全部 `network_mode: host` かつ `ROS_DOMAIN_ID` 既定 0。**
  複数スタックを同時に動かすと `/robot_description` と `/tf` が衝突し、
  RViz に別のロボットが出る。同じ LAN の別マシンとも混信する。
- **`joint_state_publisher_gui` は Qt が無いと abort するが RViz は生き残る。**
  「モデルは見えるがスライダが無い」という分かりにくい症状になる。
- **サーボの EEPROM 書き込みは永続的。** 較正値の実体は EEPROM 側にあり、
  lerobot の JSON はその控えにすぎない。**変更前に必ずバックアップすること**（後述）。
- **`LeKiwi/` は 289MB。** `.dockerignore` に入れないと全ビルドで毎回転送される。
- **上流の apt 版と GitHub の main はしばしば別物。**
  ソースを読むなら**実際に入っているバージョンのソース**を読むこと。
  過去に `feetech_ros2_driver` で 6 か月ぶんの差異に気付かず、
  正しかったコードを「上流のバグ修正」として壊した（π rad ずれた原因）。

## SO-101 アームの要点

- モータ ID 1–6、Feetech STS3215、ボーレート 1,000,000
- **正常終了（`Ctrl+C`）でトルクが切れてアームが落ちる。**
  `SIGKILL` ではトルクが残り凍結する（安全論理が LeKiwi と逆）。
  なお `docker compose down` は `exec` したプロセスに SIGINT を届けないので、
  トルクは入ったまま残る。落としたいなら launch 側で `Ctrl+C` すること
- ブリッジは起動時にトルクを入れる → **起動中はアームを手で動かせない**
- **`/joint_states` の `velocity` は信用できない。** ブリッジは 50Hz の位置差分で
  推定しているが、STS3215 の分解能は 4096 count/rev ≈ 0.0015 rad なので、
  1 量子ぶんの揺れがそのまま 0.077 rad/s に化ける。
  JTC の `stopped_velocity_tolerance` はこれで誤検知する
- 較正値の実体は**サーボの EEPROM**。lerobot の JSON はその控えにすぎず、
  較正を実行した PC のホームにしか無い

### 較正（EEPROM を書き換える前に必ず控えを取る）

較正は **ROS を止めた状態で lerobot のコマンド**を使う。ROS 側からは変更できない。

```bash
# 控え: 現在の較正 JSON をコピーしておく
cp -a ~/.cache/huggingface/lerobot/calibration/robots/so_follower \
      ~/so_follower_backup_$(date +%Y%m%d_%H%M)

lerobot-calibrate --robot.type=so101_follower \
  --robot.port=/dev/so101_follower --robot.id=my_follower
```

## ドキュメント

| 対象 | 場所 |
| --- | --- |
| SO-101 アーム（手順・トラブルシュート） | `docker/so101_ros2/README.md` |
| LeKiwi ベース | `docker/lekiwi_base_ros2/README.md` |
| LeKiwi + Nav2/SLAM | `docker/lekiwi_bringup/README.md` |
| LeKiwi + SO-101（リーチ） | `docker/lekiwi_so101_bringup/README.md` |
| **TF の信頼性一覧**（どこを疑うかの索引） | `docs/tf_reliability.md` |
| RPLIDAR / RealSense | `docker/rplidar_ros2/`, `docker/realsense_ros2/` |
| 実機担当 agent への指示 | `docs/hardware_agent.md`, `docs/agent/` |

## コミットの慣習

- メッセージは日本語。`feat:` / `fix:` / `docs:` のプレフィックス
- **何を検証したかを本文に書く**。「動くはず」ではなく「こう確認した」
- 推測で断定しない。未検証なら「未検証」と書く
