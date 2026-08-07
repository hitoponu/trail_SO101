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

- `ros2 topic echo` / `ros2 topic hz` / `ros2 node list` / `ros2 action list`
- `ros2 control list_controllers` / `list_hardware_components`
- `ros2 run tf2_ros tf2_echo` / `ros2 run tf2_tools view_frames`
- `docker compose build` / `make build` / `make bootstrap`
- `make mock`（**モック構成のみ。シリアルを開きません**）
- `git pull` / `git status` / `git log` / `git diff`
- `ls` / `dmesg` / `udevadm info` などの調査

### 🟡 実行前に人間へ確認する（実機が動く・状態が変わる）

- **`backend:=lerobot` での launch 起動**
  → 起動時に一瞬脱力する。人がアームを支えている必要がある
- **`lerobot-calibrate` の実行**
  → **サーボの EEPROM が書き換わる。永続的。**
- `git push` / `git commit`
- udev ルールの導入、`usermod`

**EEPROM を書き換える変更の前には、必ずバックアップを取ってから確認を求めること。**
較正は ROS を止めた状態で lerobot のコマンドを使います（ROS 側からは変更できません）。

```bash
cp -a ~/.cache/huggingface/lerobot/calibration/robots/so_follower \
      ~/so_follower_backup_$(date +%Y%m%d_%H%M)
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

### ★ まずコンテナ名を確認すること

**スタックによってアームのコンテナ名が違います。名前を間違えると非常停止が空振りします。**

| スタック | アームのコンテナ名 |
| --- | --- |
| `docker/so101_ros2`（アーム単体） | `so101-follower` |
| `docker/lekiwi_so101_bringup`（ベース + アーム） | **`lekiwi-so101-arm`** |
| 同上のモック | `lekiwi-so101-arm-mock` |

```bash
docker ps --format '{{.Names}}'    # 実際に動いている名前を先に確認する
```

| 状況 | 操作 | トルク | 結果 |
| --- | --- | --- | --- |
| 今の動作だけ止めたい | 実行中の `send_goal` を `Ctrl+C` | ON | その場で保持。**最速** |
| 動きを凍結したい | `docker kill -s SIGKILL <上表のコンテナ名>` | ON | 凍結（発熱注意） |
| 通常終了 | launch を `Ctrl+C` | **OFF** | **脱力して落ちる** |
| 完全停止 | アーム電源スイッチ OFF | **OFF** | **落ちる**。唯一の物理的非常停止 |

**「止める」＝「落ちる」です。** 停止前に低く畳んだ姿勢へ動かしてください。

> ★ `make down` は bridge の shutdown service を先に呼び、トルクOFFを待ってから
> コンテナを停止します。直接 `docker compose down` する場合はこの保証がありません。

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
✅ （実行したコマンドの出力を丸ごと貼る）
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
| サーボの定格 | **7.4V 版**（ホイールは 12V 版。★ 同一バスへ繋がないこと） |
| 電源電圧 | **実測 4.9V（静止時）**。定格 7.4V に対して低い |
| 較正の出自 | LeKiwi 構成で較正したものが EEPROM に残っている（`my_kiwi` 由来） |

> ★ **定格 7.4V と実測 4.9V は別の量**（サーボの型と実際の供給電圧）であり、
> 矛盾ではありません。ただし定格より 2.5V 低い状態で使っていることになります。
> 「対話操作で力が弱い」問題の一因である可能性がありますが**未検証**です
> （動作中の最低電圧も未測定）。テスターを電源コネクタに当てるのが確実です。
> **8.0V を超えるとサーボが壊れます。** 電源の変更は人間の判断が必要です。

> ★ `robot_id`（LeRobot の較正 ID）は機体で確定していません。
> 使う前に実物を確認してください:
> `ls ~/.cache/huggingface/lerobot/calibration/robots/so_follower/`

### 較正値の初期状態（旧 `so101_probe --scan` による初回記録）

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

- ブランチ: **`feat/lekiwi-so101-reach`**（LeKiwi ベース + SO-101 アーム）
- **アーキテクチャが変わりました。** `feetech_ros2_driver` は廃止され、
  `JointStateTopicSystem` + LeRobot ROS ブリッジになっています。
  モータ設定・較正・PID の責任はすべて LeRobot 側にあります。
  `so101_probe` / `so101_calib` / `config/so101_joints.yaml` /
  `compose.dev.yaml` / `HARDWARE_TYPE` は**すべて削除済み**です

### 未解決

- **対話操作（rqt のスライダ）で保持力が弱い。** 全関節 `P=16`
  （STS3215 の工場出荷値 32 の半分。lerobot が振動回避で下げた値）。
  位置制御のトルクは概ね `P × 位置偏差`で、スライダ操作は偏差がほぼゼロに
  なるため力が出ません。**直す場所は ROS 側ではなく LeRobot の設定**に
  変わりました。別途依頼します
- **動作中の最低電圧が未測定**（上記の 4.9V は静止時）
- **グリッパの「閉」が `range_min`(1961) 側か `range_max`(3399) 側か未検証**
- **`ros2_control_node` の周期超過**。Mac のモックで 50Hz に対し最大 62ms の
  overrun を観測。Docker Desktop の性能によるものと見ていますが、
  実機でも出るなら watchdog 誤発火の要因になります

### 統合構成で未確定（実測待ち）

| 項目 | 現状 |
| --- | --- |
| `laser_link` の位置 | **TBD 仮値 (0.10, 0, 0.03)**。xy が違うと地図が向き依存で歪み、その誤差がそのまま手先に乗る |
| アーム取付の位置と **yaw** | CAD 由来 (0.08, -0.04, 0.057) rpy 0 で**未実測**。yaw が 90° 違う可能性がある |
| `joint_limit_overrides` | **空**。`laser_link` と `arm_mount_link` は xy で 44.7mm しか離れていない |
| `stow_positions` | 暫定値。無通電で干渉しないことを確かめてから使うこと |

### 検証済み（Mac のモックのみ。実機は未検証）

- 結合 URDF が `base_footprint` を根とする単一ツリーになる
- `/robot_description` の publisher が 1、`/joint_states` が 2
- コントローラ 3 種が `arm_` 接頭辞付きの関節で active になる
- `map` → `arm_gripper_frame_link` の TF が繋がる
- リーチ: 到達可能 → `SUCCEEDED`、到達不能 → 軌道を 1 件も出さない、
  TF が古い → `REJECTED_STALE_TF`、odom が古い → `REJECTED_STALE_ODOM`

この節は作業が進んだら**あなたが更新してください**。次のセッションの前提になります。
