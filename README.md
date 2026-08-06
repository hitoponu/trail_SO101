# trail_SO101

SO101 を lerobot で動かすためのリポジトリ。

## セットアップ

```bash
# macOS (開発機)
brew install ffmpeg

# Ubuntu (実機を繋ぐ PC)
sudo apt-get update && sudo apt-get install -y ffmpeg

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

## IK (placo) の注意 — macOS

`record_and_move_ik.py` は逆運動学に [placo](https://github.com/Rhoban/placo) を使う
（`uv sync` で導入される）。macOS では placo がリンクする `liburdfdom_*.4.0.dylib` と、
依存解決で入る `liburdfdom_*.6.0.0.dylib` の **soname 不一致**で
`Library not loaded: @rpath/liburdfdom_sensor.4.0.dylib` というエラーになる。

暫定対処として 6.0 の実体へ 4.0 名のシンボリックリンクを張る（ABI 互換のため FK/IK は正常動作を確認済み）:

```bash
cd "$(uv run python -c 'import cmeel, pathlib; print(pathlib.Path(cmeel.__file__).resolve().parent.parent/"cmeel.prefix"/"lib")')"
for n in sensor model world; do
  ln -sf "liburdfdom_${n}.6.0.0.dylib" "liburdfdom_${n}.4.0.dylib"
done
```

`uv sync` 等で cmeel-urdfdom が再インストールされた場合は、上記を再実行する。

## ROS 2 (Docker)

ROS 2 Jazzy の構成は `docker/` 以下にまとめてある。ROS 2 パッケージの実体は
`ros2_ws/src/` にある。実機を繋ぐものはいずれも **Linux ホスト**が前提
（macOS の Docker はシリアル/USB デバイスをコンテナへ渡せないため）。

| 対象 | 内容 | ドキュメント |
| --- | --- | --- |
| SO-101 フォロワアーム | LeRobotバックエンドと薄いROSブリッジで`FollowJointTrajectory`とグリッパを提供 | [docker/so101_ros2/README.md](docker/so101_ros2/README.md) |
| LeKiwi ベース | 3輪オムニベースを `/cmd_vel` で駆動し、オドメトリと TF を出す | [docker/lekiwi_base_ros2/README.md](docker/lekiwi_base_ros2/README.md) |
| LeKiwi + SO-101（リーチ） | ベースにアームを載せ、`map` 上の点へ手先を伸ばす | **[docs/lekiwi_so101_reach.md](docs/lekiwi_so101_reach.md)**（概要）/ [docker/lekiwi_so101_bringup/README.md](docker/lekiwi_so101_bringup/README.md)（運用） |
| 環境固定 RealSense（リーチ目標の指定） | 据え置きカメラの点群を `map` に載せ、点をクリックしてリーチ | [docs/env_camera_calibration.md](docs/env_camera_calibration.md)（較正手順） |
| RPLIDAR A1M8 | 2DスキャンをPointCloud2へ変換してRViz 2で表示 | [docker/rplidar_ros2/README.md](docker/rplidar_ros2/README.md) |
| RealSense D435i | D435i を起動してRViz 2で表示 | [docker/realsense_ros2/README.md](docker/realsense_ros2/README.md) |

> **LeKiwi ベースの安全上の注意**: この機体は 7.4V 版アームと 12V 版ホイールの
> 混在構成のため、**12V 給電中にアーム（モータ ID 1〜6）をバスへ繋いではいけない**。
> 詳細は上記 README を参照。

> **SO-101 アームの安全上の注意**: ブリッジの正常終了で
> **トルクが切れてアームが落ちる**。停止前に必ず低く畳んだ姿勢へ動かすこと。
> 詳細は上記 README の冒頭を参照。
