# trail_SO101

SO-101 アームと LeKiwi 移動ベースを lerobot と ROS 2 で動かすリポジトリ。

## マシンの分担

| マシン | 役割 | ハードウェア |
| --- | --- | --- |
| **Mac**（開発機） | 設計・実装・モック検証・コミット | **無し**。Docker にシリアルデバイスを渡せない |
| **Linux PC**（`hsr-pc5`） | **実機検証のみ** | SO-101 アーム（`/dev/so101_follower`） |

**実機に触れるのは Linux PC だけ。** Mac 側は `mock_components` までしか検証できない。
Linux PC 側で作業する agent は `docs/hardware_agent.md` を必ず読むこと。

## ブランチ

| ブランチ | 内容 |
| --- | --- |
| `feat/so101-follower-ros2` | SO-101 アーム。`ros2_control` + apt の `feetech_ros2_driver` |
| `feat/lekiwi-base-ros2` | LeKiwi ベース。3輪オムニ、自作 rclpy ドライバ |

どちらも `main` から分岐。`README.md` と `.dockerignore` で軽く衝突する。

## 実際に踏んだ地雷（繰り返さないこと）

- **`docker compose exec` は ENTRYPOINT を通らない。**
  `ros2` が PATH に無い。`/entrypoint.sh` を前置する。
  `docker compose run` / `up` は通るので前置不要。
- **`docker/` 以下は全部 `network_mode: host` かつ `ROS_DOMAIN_ID` 既定 0。**
  複数スタックを同時に動かすと `/robot_description` と `/tf` が衝突し、
  RViz に別のロボットが出る。同じ LAN の別マシンとも混信する。
- **`joint_state_publisher_gui` は Qt が無いと abort するが RViz は生き残る。**
  「モデルは見えるがスライダが無い」という分かりにくい症状になる。
- **サーボの EEPROM 書き込みは永続的。** `so101_calib` が生成する
  `homing_offset` / `range_*` はドライバが起動時に EEPROM へ書く。
  **変更前に必ず現状をバックアップすること**（後述）。
- **`LeKiwi/` は 289MB。** `.dockerignore` に入れないと全ビルドで毎回転送される。

## SO-101 アームの要点

- モータ ID 1–6、Feetech STS3215、ボーレート 1,000,000
- **正常終了（`Ctrl+C` / `docker compose down`）でトルクが切れてアームが落ちる。**
  `docker kill -s SIGKILL` ではトルクが残り凍結する（安全論理が LeKiwi と逆）
- ドライバは `on_init` でトルクを入れる → **起動中はアームを手で動かせない**
- `/joint_states` の `velocity` は信用できない（ドライバが符号を復号していない既知バグ）
- 較正値の実体は**サーボの EEPROM**。lerobot の JSON はその控えにすぎず、
  較正を実行した PC のホームにしか無い

### 較正値のバックアップ（EEPROM を書き換える前に必ず）

```bash
cd docker/so101_ros2
docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_calib \
    --from-servos --port /dev/so101_follower --emit-ranges \
  > backup_$(date +%Y%m%d_%H%M).yaml
```

`--from-ranges` を付けなければ Δ=0、つまり現状のスナップショットになる。

## ドキュメント

| 対象 | 場所 |
| --- | --- |
| SO-101 アーム（手順・トラブルシュート） | `docker/so101_ros2/README.md` |
| LeKiwi ベース | `docker/lekiwi_base_ros2/README.md`（`feat/lekiwi-base-ros2`） |
| RPLIDAR / RealSense | `docker/rplidar_ros2/`, `docker/realsense_ros2/` |
| 実機担当 agent への指示 | `docs/hardware_agent.md` |

## コミットの慣習

- メッセージは日本語。`feat:` / `fix:` / `docs:` のプレフィックス
- **何を検証したかを本文に書く**。「動くはず」ではなく「こう確認した」
- 推測で断定しない。未検証なら「未検証」と書く
