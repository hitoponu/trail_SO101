# 依頼（Mac → 実機）

- **更新**: 2026-08-02
- **状態**: 実行待ち
- **安全区分**: 🟢 読み取りのみ（EEPROM は書き換えない）

## 背景

`wrist_flex` の `homing_offset` に折り返し値（`-1950`）を書いた結果、
RViz が不可能な姿勢を表示し、`send_goal` を送っても動かなくなりました。

サーボが `Present = (Actual − homing) mod 4096` でラップしない場合、
可動端で `q_ros` が 4.49 rad 程度の異常値になります。URDF の上限は ±1.6 rad なので
RViz が破綻し、JTC も `enforce_command_limits` に阻まれます。**症状と一致します。**

これを実データで確定させたいです。

## やってほしいこと

### 1. 現状のバックアップ

```bash
cd docker/so101_ros2
docker compose down
docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_calib \
    --from-servos --port /dev/so101_follower --emit-ranges \
  > backup_$(date +%Y%m%d_%H%M).yaml
```

### 2. サーボの現状を読む

```bash
docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_probe --port /dev/so101_follower --scan
```

### 3. `wrist_flex` を可動端まで動かして `q_ros` を観測する ★これが本題

トルクを切って**手で**動かします。指令は送りません。

```bash
docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_probe --port /dev/so101_follower --torque-off --watch
```

`wrist_flex`（id 4）を**両方の可動端までゆっくり手で動かし**、
`Present` と `q_ros` がどう変化するかを見てください。

**知りたいのは1点だけです。**

- `q_ros` が **±1.6 rad の範囲に収まる** → サーボはラップする（私の推論が正しかった）
- `q_ros` が **4 rad を超える / 不連続に飛ぶ** → サーボはラップしない（私の推論が誤り）

## 報告してほしいこと

1. 手順2の `--scan` 出力（**そのまま全部**）
2. 手順3で `wrist_flex` を端から端まで動かしたときの `Present` と `q_ros` の
   **最小値と最大値**、および**途中で不連続に飛ぶ箇所があったか**
3. バックアップファイル名

## やらないでほしいこと

- **EEPROM の書き換え**（`so101_joints.yaml` の更新とビルド）はまだしないでください。
  上の報告を見てから、書き戻す値を確定させます
- **`send_goal` による関節の移動**（🔴）

## 補足

手順3でアームが脱力します。`wrist_flex` 以外の関節も落ちるので、
**アームを手で支えるか、低い姿勢にしてから**トルクを切ってください。
