# trail_SO101

SO101 を lerobot で動かすためのリポジトリ。

## セットアップ

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
uv sync
```

## examples

設定は `examples/config.toml`（ポート/ID・補間・IK の重み・カメラインデックス）に記述する。

- ポートの調べ方: `uv run python -m lerobot.scripts.lerobot_find_port`
- カメラインデックスの調べ方: `uv run python -m lerobot.scripts.lerobot_find_cameras`

| スクリプト | 内容 |
| --- | --- |
| `examples/record_and_move.py` | leader の関節角度を記録し、follower を同じ角度へ移動 |
| `examples/record_and_move_ik.py` | leader の EE(エンドエフェクタ)位置を記録し、IK で解いて follower を移動 |
| `examples/capture_camera.py` | SO101 付属カメラのライブ映像を表示し、`s` キーで画像を保存 |

```bash
uv run python examples/record_and_move.py
uv run python examples/record_and_move_ik.py
uv run python examples/capture_camera.py
```

## ROS 2 (Docker)

ROS 2 Jazzy の構成は `docker/` 以下にまとめてある。ROS 2 パッケージの実体は
`ros2_ws/src/` にある。Linuxホスト上のDocker Engineで実行する。

| 対象 | 内容 | ドキュメント |
| --- | --- | --- |
| SO-101 フォロワアーム | LeRobotバックエンドと薄いROSブリッジで`FollowJointTrajectory`とグリッパを提供 | [docker/so101_ros2/README.md](docker/so101_ros2/README.md) |
| RPLIDAR A1M8 | 2DスキャンをPointCloud2へ変換してRViz 2で表示 | [docker/rplidar_ros2/README.md](docker/rplidar_ros2/README.md) |

> **SO-101 アームの安全上の注意**: ブリッジの正常終了で
> **トルクが切れてアームが落ちる**。停止前に必ず低く畳んだ姿勢へ動かすこと。
> 詳細は上記 README の冒頭を参照。
