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
- 依頼書 (`docs/agent/request.md`) で 🔴 と印の付いた手順すべて

**アームは自重で落ち、自分自身とも机とも人ともぶつかります。**
指令を送る前に必ず、
「アームの周囲 35cm が空いているか」「人が手を添えているか」「電源スイッチに手が届くか」
を確認してください。

---

## 非常停止

### ★★ 非常停止は物理スイッチだけです

**`docker kill` を非常停止に使わないでください。**

`docker/robot`（統合スタック、1 コンテナ）ではアームとベースが同じコンテナに居ます。
SIGKILL を送ると停止処理（Python の `finally`）が一切走らず、

- アームは**トルクが入ったまま凍り**、
- **ホイールは最後の指令速度で回り続けます**（STS3215 にコマンドウォッチドッグは無い）。

つまり「凍結」と引き換えに**機体が走り去る**ことになります。

| 状況 | 操作 | アームのトルク | ホイール |
| --- | --- | --- | --- |
| 今の動作だけ止めたい | 実行中の `send_goal` を `Ctrl+C` | ON（その場で保持。**最速**） | 影響なし |
| 通常終了 | launch を `Ctrl+C` | **OFF → 脱力して落ちる** | 速度ゼロ + トルク OFF |
| **完全停止（非常停止）** | **電源スイッチ OFF** | **OFF → 落ちる** | 止まる。**唯一の非常停止** |
| ~~動きを凍結したい~~ | ~~`docker kill -s SIGKILL`~~ | ~~凍結~~ | **★ 回り続ける。使わないこと** |

**「止める」＝「落ちる」です。** 停止前に低く畳んだ姿勢へ動かしてください（`make stow`）。

### 異常終了（SIGKILL / OOM / コンテナ強制削除）からの復帰

停止処理が走らなかった場合、**サーボは指令を保持したままです。**
復帰専用のコマンドがあります（ROS を使わず、シリアルポートを直接開きます）。

```bash
cd docker/robot
make down            # ★ 先に。ROS のノードが生きているとポートを掴んでいます
make release-check   # 読むだけ。いまトルクが入っているかの確認（何も書きません）
make release-wheels  # ホイールだけ止める（アームは落ちない）。走り出したときの一次対応
make release         # ホイールを止めて**アームのトルクも切る**（★ アームは落ちます）
```

> ★ **`robot` コンテナが動いている間は `make release*` を実行できません**
> （guard が止めます）。Feetech のバスはマスタが 1 つだけで、launch が
> 開いたまま触ると混線し、ブリッジが通信異常と判定してトルクを切るためです
> （＝アームがその場で落ちます）。「読むだけ」でも送信が要るので同じです。

> ★ `make release-check` は**トルクが入っていると exit 1** を返します
> （`make: *** Error 1`）。解放前に叩けばそれが正常な結果です。

> ★ `make release` は**アームが落ちます**。人が支えてから実行してください。
> `--yes` を付けなければ確認を求めます。
> 実行後に `Torque_Enable` を読み戻して、本当に切れた ID だけを成功として表示します。

### ★ 旧スタック（4 コンテナ）を使う場合

**スタックによってアームのコンテナ名が違います。名前を間違えると空振りします。**

| スタック | アームのコンテナ名 |
| --- | --- |
| `docker/robot`（**統合、これを使う**） | `robot`（アームもベースも同じ） |
| `docker/so101_ros2`（アーム単体） | `so101-follower` |
| `docker/lekiwi_so101_bringup`（ベース + アーム、4 コンテナ） | `lekiwi-so101-arm` |
| 同上のモック | `lekiwi-so101-arm-mock` |

```bash
docker ps --format '{{.Names}}'    # 実際に動いている名前を先に確認する
```

`docker/so101_ros2`（アーム単体、ホイールが無い）でだけは
`docker kill -s SIGKILL so101-follower` に「トルクを保持したまま凍結する」意味があります。
**ベースが同じコンテナに居るスタックでは使わないでください。**

> ★ `docker/lekiwi_so101_bringup` の `make down` は bridge の shutdown service を先に
> 呼び、トルク OFF を待ってからコンテナを停止します。直接 `docker compose down` する
> 場合はこの保証がありません。`docker/robot` では launch を前面で `Ctrl+C` する運用
> なので、この回避策そのものが不要です。

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

- ブランチ: **`feat/single-container`**（統合スタック `docker/robot`。
  1 イメージ 1 コンテナ 1 launch。旧 4 コンテナ構成は単体デバッグ用に残存）
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
- **`ros2_control_node` の周期超過**。★ **実機でも発生している**（64.1ms > 20.0ms）。
  Docker Desktop 固有ではなかった。watchdog 誤発火の要因になりうる

### 実機で検証済み

- 結合スタックの起動（ベース / LiDAR / アーム）、コントローラ 3 種が active
- `make down` で 6 軸すべてトルク OFF
- ナビゲーション（`/goal_pose` からの走行）
- **リーチの実行**
  ★ 実行したという事実のみ。**結果・精度・実施日は `report.md` に記録が無い。**
  次に触ったときに追記すること
- アーム取付位置の実測（`(0.08, 0.00, 0.057)`。CAD の y=−0.04 は誤りだった）
- `laser_link` の実測（xyz は仮値と一致、yaw のみ −7°）
- バス分離（SO-101 側に ID 1–6 のみ）、udev（★ LeKiwi と SO-101 は同じ
  VID/PID なのでシリアルで識別）

**★ 上はすべて旧 4 コンテナ構成（`docker/lekiwi_so101_bringup`）での結果です。**

### ★ 統合スタック（`docker/robot`）で**まだ実機検証していないこと**

- **`release_all` が実際にトルクを落とすか**（最重要。これが通らないと
  1 コンテナ化は安全側に成立しない）
- `docker kill` 後にホイールが回り続けることの実地確認と、そこからの復帰
- `privileged` で 3 デバイス + RealSense が同時に見えるか
- 実機での `Ctrl+C` 停止（全ノードが cleanly に落ちるか）

いずれも `docs/agent/request.md`（7回目）の手順 2〜5 です。

### ★ 実機で未確定のまま残っているもの

- **`joint_limit_overrides` が空**。アームが LiDAR / カメラマウントに
  当たらないための唯一の防御。`laser_link` と `arm_mount_link` は
  実測 **20mm** しか離れていない
- 手首カメラの取付姿勢。既定値は **D405 + 公式ホルダ前提の幾何計算値**で、
  手元の D435i とは前提が違う（`docs/wrist_camera.md`）

### モックのみで検証（実機で再確認するとよい）

- 結合 URDF が `base_footprint` を根とする単一ツリーになる
- `/robot_description` の publisher が 1、`/joint_states` が 2
- コントローラ 3 種が `arm_` 接頭辞付きの関節で active になる
- `map` → `arm_gripper_frame_link` の TF が繋がる
- リーチ: 到達可能 → `SUCCEEDED`、到達不能 → 軌道を 1 件も出さない、
  TF が古い → `REJECTED_STALE_TF`、odom が古い → `REJECTED_STALE_ODOM`

この節は作業が進んだら**あなたが更新してください**。次のセッションの前提になります。
