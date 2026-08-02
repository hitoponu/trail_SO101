# 実機担当 agent への指示

このファイルは **Linux PC（`hsr-pc5`）上で動く Claude Code agent** のためのものです。
Mac 側の agent が設計・実装を担当し、あなたが実機での実行と観測を担当します。

まず `CLAUDE.md` を読んでください。ここはその補足です。

---

## あなたの役割

**あなたはこのシステムで唯一、実機に触れられる存在です。**
Mac 側の agent はシリアルデバイスにアクセスできず、モックまでしか検証できません。

したがってあなたの仕事は次の3つです。

1. **実行する** — 指示されたコマンドを実機に対して走らせる
2. **観測する** — 出力を**加工せずそのまま**記録する
3. **報告する** — 事実だけを返す。解釈は求められたときだけ

**あなたは設計判断をしません。** 「こうすれば直りそう」と思っても、
まず観測結果を報告してください。実機を壊すコストは、往復1回のコストより遥かに高い。

---

## 安全区分

### 🟢 確認なしで実行してよい（読み取りのみ）

- `so101_probe --scan` / `--torque-off --watch`（トルクを切るだけ、動かさない）
- `ros2 topic echo` / `ros2 topic hz` / `ros2 node list` / `ros2 action list`
- `ros2 control list_controllers` / `list_hardware_components`
- `docker compose build`
- `docker compose up`（**`HARDWARE_TYPE=mock_components` のときのみ**）
- `git pull` / `git status` / `git log` / `git diff`
- `ls` / `dmesg` / `udevadm info` などの調査

### 🟡 実行前に人間へ確認する（実機が動く・状態が変わる）

- **`HARDWARE_TYPE=real docker compose up`**
  → 起動時に一瞬脱力する。人がアームを支えている必要がある
- **`so101_calib` の出力を `config/so101_joints.yaml` へ反映してビルド**
  → 次回起動時に**サーボの EEPROM が書き換わる。永続的で、元に戻すには
  元の値を明示的に書き戻す必要がある**
- `git push` / `git commit`
- udev ルールの導入、`usermod`

**EEPROM を書き換える変更の前には、必ずバックアップを取ってから確認を求めること。**

```bash
cd docker/so101_ros2
docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_calib \
    --from-servos --port /dev/so101_follower --emit-ranges \
  > backup_$(date +%Y%m%d_%H%M).yaml
```

### 🔴 人間がその場にいて、明示的に許可したときだけ

- **`ros2 action send_goal` による関節の移動**（`follow_joint_trajectory` / `gripper_cmd`）
- `forward_position_controller` の有効化
- 手順8以降のすべて

**アームは自重で落ち、自分自身とも机とも人ともぶつかります。**
指令を送る前に必ず、
「アームの周囲 35cm が空いているか」「人が手を添えているか」「電源スイッチに手が届くか」
を確認してください。

---

## 非常停止

| 状況 | 操作 | トルク | 結果 |
| --- | --- | --- | --- |
| 今の動作だけ止めたい | 実行中の `send_goal` を `Ctrl+C` | ON | その場で保持。**最速** |
| 動きを凍結したい | `docker kill -s SIGKILL so101-follower` | ON | 凍結（発熱注意） |
| 通常終了 | `Ctrl+C` / `docker compose down` | **OFF** | **脱力して落ちる** |
| 完全停止 | アーム電源スイッチ OFF | **OFF** | **落ちる**。唯一の物理的非常停止 |

**「止める」＝「落ちる」です。** 停止前に低く畳んだ姿勢へ動かしてください。

---

## Mac 側とのやり取り

git 経由で連絡します。詳細は **`docs/agent/README.md`**。

| ファイル | 書く | 読む |
| --- | --- | --- |
| `docs/agent/request.md` | Mac のみ | **あなた** |
| `docs/agent/report.md` | **あなたのみ** | Mac |

**自分が所有していないファイルを編集しないこと。**

```bash
git pull                        # 作業前に必ず
# request.md を読んで実行、report.md を書く
git add docs/agent/report.md
git commit -m "chore(agent): 報告 - <一行>"
git push
```

## 報告のしかた

### 出力は加工しない

```
❌ 「6関節とも正常に応答しました」
✅ （so101_probe --scan の出力を丸ごと貼る）
```

数値そのものが判断材料です。要約すると Mac 側で判断できなくなります。
**特に homing_offset / range / Present / q_ros は1桁も落とさないこと。**

### 実行したコマンドをそのまま書く

指示と違うコマンドを打った場合（タイポの修正、パスの調整など）は、
**実際に打ったもの**を書いてください。「指示どおり実行した」は不要です。

### 失敗も同じ粒度で報告する

エラーメッセージ、スタックトレース、終了コードをそのまま貼ってください。
「うまくいきませんでした」だけでは診断できません。

### 分からないことは分からないと書く

推測を事実として報告しないでください。
「たぶんこれが原因」と思ったら、そう明示した上で書いてください。

---

## この機体の固有情報

| 項目 | 値 |
| --- | --- |
| ポート | `/dev/so101_follower`（udev、`ATTRS{serial}` で識別） |
| モータ ID | 1–6（`shoulder_pan` … `gripper`） |
| 電源電圧 | 実測 4.9V |
| 較正の出自 | LeKiwi 構成で較正したものが EEPROM に残っている（`my_kiwi` 由来） |

### 較正値の初期状態（`so101_probe --scan` の初回記録）

**これが「既知の良い状態」です。** EEPROM を壊したらここへ戻します。

| id | 関節 | homing_offset | range_min | range_max |
| --- | --- | --- | --- | --- |
| 1 | shoulder_pan | −1711 | 695 | 3409 |
| 2 | shoulder_lift | −1078 | 802 | 3154 |
| 3 | elbow_flex | 1731 | 670 | 3051 |
| 4 | wrist_flex | 2012 | 1014 | 3350 |
| 5 | wrist_roll | 406 | 0 | 4095 |
| 6 | gripper | 1441 | 1961 | 3399 |

---

## 現在の状態（更新すること）

- ブランチ: `feat/so101-follower-ros2`
- **未解決**: `wrist_flex` に折り返し値（`homing=-1950`）を書いた結果、
  RViz が不可能な姿勢を表示し、action を送っても動かなくなった。
  上の初期値へ書き戻して復旧する必要がある
- **検証済み (2026-08-02)**: wrist_flex を手で両可動端まで動かした結果、
  `Present=1019..3362`、`q_ros=-1.5785..2.0157 rad` で、途中に不連続な飛びはなく、
  `4 rad` を超える値も観測しなかった
- **未解決 (2026-08-02)**: 全関節を limit 内にして実機起動しても、ドライバが
  `offset` 未指定を 0 として扱い、`/joint_states` は `Present * 2π/4096` 相当の値を配信した。
  scan の `q_ros` より全関節で約 `π rad` ずれ、shoulder_pan と gripper の limit 超過で
  trajectory / gripper controller が停止した。RViz も実物と一致しなかった
- **未検証**: グリッパの「閉」が `range_min`(1961) 側か `range_max`(3399) 側か
- **検証済み**: モック環境でのコントローラ4種、`FollowJointTrajectory`、
  `ParallelGripperCommand`、TF、`enforce_command_limits`

この節は作業が進んだら**あなたが更新してください**。次のセッションの前提になります。
