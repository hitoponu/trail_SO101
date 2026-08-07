# LeKiwi + SO-101 リーチ機能 — 使い方と実機検証項目

ブランチ: `feat/lekiwi-so101-reach`

LeKiwi 移動ベースに SO-101 アームを載せ、**`map` 座標系に固定された点へ手先を伸ばす**機能です。
RViz で点をクリックすると、アームがそこへ届きます。

このドキュメントは概要です。運用の詳細は
[`docker/lekiwi_so101_bringup/README.md`](../docker/lekiwi_so101_bringup/README.md) を参照してください。

---

## 何ができて、何をしないか

| | |
| --- | --- |
| **する** | `map` 上の点へアームの手先を伸ばす |
| **しない** | **ベースを動かすことは一切しない。** 届かなければ警告して何もしない |

ベースを動かさないことは、ノードが `/cmd_vel` の publisher を**一切作らない**ことで
構造的に保証しています（単体テストで機械的に検査しています）。

**精度は数 cm です。**「クリックした点の数 cm 以内に手先を持っていく」もの、
と考えてください。理由は後述します。

---

## 使い方

### 1. 準備（初回のみ）

```bash
cd docker/lekiwi_so101_bringup
cp .env.example .env          # ★ デバイス名と DIALOUT_GID を実機に合わせる
make build
make bootstrap                # ★ 必須。飛ばすと起動できない
```

> **`make bootstrap` は省略できません。**
> このイメージは ROS ワークスペースを焼き込まず、ホストからマウントします。
> `ros2_ws/install` と `ros2_ws/src/ros2_so_arm` は `.gitignore` 済みで
> `git pull` では降ってきません。飛ばすと
> `Package 'lekiwi_so101_bringup' not found` になります。
>
> `bootstrap` は最後に静的検査を 3 つ走らせます。3 つとも `OK` にならなければ
> そこで止めてください。

### 2. 起動

```bash
make mock     # 実機に触れない（Mac でも動く）
make reach    # 実機
```

実機は `backend:=lerobot` と較正 ID の指定が要ります。詳細は運用 README を参照。

### 3. 目標を与える

**RViz の "Publish Point" ツールでクリックする**のがいちばん簡単です。

> ★ RViz の **Fixed Frame を `map`** にしてください。
> Publish Point は Fixed Frame の座標で publish するので、`odom` のままだと
> `REJECTED_WRONG_FRAME` で弾かれます。

コマンドラインからも与えられます。

```bash
docker exec lekiwi-so101-arm /entrypoint.sh \
  ros2 topic pub --once /so101/reach_target geometry_msgs/msg/PoseStamped \
    '{header: {frame_id: map}, pose: {position: {x: 0.35, y: 0.05, z: 0.25}, orientation: {w: 1.0}}}'
```

結果は `/so101/reach_status` に 1 行ずつ出ます。RViz には目標球が出ます
（**緑 = 受理 / 赤 = 棄却**）。

```
ACCEPTED   target=map(0.350,0.050,0.250) iters=10 residual=0.0006 dur=1.2
SUCCEEDED  residual_fk=0.0007
```

届かない場合は、**どの関節が可動限界に張り付いたか**まで出ます。
「遠すぎる」のか「ベースを回せば届く」のかが区別できます。

```
REJECTED_UNREACHABLE residual=0.0912 status=STALLED pinned=['arm_shoulder_lift_joint']
```

### 4. 停止

**★ 順番を守ってください。正常終了でトルクが切れてアームが落ちます。**

```bash
make stow     # 1. アームを低く畳む
make down     # 2. bridgeをshutdownしてトルクOFF後、コンテナを停止
```

---

## ★ 実機で検証が必要なこと

**2026-08-07 に実機起動まで完了しました（`docs/agent/report.md`）。ただしリーチ指令はまだ一度も送っていません。**

### A. 実機に持っていく前に必ず確定させる（測るまで動かさない）

| # | 項目 | 現状 | なぜ必要か |
| --- | --- | --- | --- |
| A-1 | アーム取付 | **✅ 実測済み `(0.08, 0.00, 0.057)` rpy 0。★ CAD の y=−0.04 は誤りで実測は y=0** | 向きは仮定どおりだった |
| A-2 | `laser_link` | **✅ 実測済み `(0.10, 0, 0.03)`、yaw = −7°** | xyz は仮値と一致。yaw だけ補正が要った |
| A-3 | 7.4V と 12V のバス分離 | **✅ 確認済み**（SO-101 側に ID 1–6 のみ。7/8/9 は検出されず） | アームもホイールも同じ STS3215 の 1Mbps で、**物理的には繋がってしまいます**。繋いだ瞬間にアーム側が壊れます |
| A-4 | udev ルール | **✅ 導入済み。★ LeKiwi と SO-101 は同じ VID/PID (1a86:55d3) だったのでシリアルで識別**（LeKiwi=`5A7A017874`） | 無いと `/dev/ttyACM*` の列挙順が運任せで、**12V のホイール指令が 7.4V のアームサーボへ飛びえます** |
| A-5 | **アームのボルト固定** | 未確認 | 天板 0.216m 角に対し支持多角形は車輪円（半径 0.125m）。約 0.75kg を 0.09m 上に片持ちすると**転倒しえます** |

A-1 と A-2 の測り方は [`docs/agent/request.md`](agent/request.md) の手順 0 と手順 3 にあります。
手順 3 では TF の出力と定規の実測を突き合わせます。期待値は
**全関節ゼロで `base_link` → `(0.471, 0.000, 0.283)`** です（y=0 の実測を反映）。

### B. 動かす前に人手で決める

| # | 項目 | 現状 |
| --- | --- | --- |
| B-1 | **`joint_limit_overrides`** | **空のまま。★ 実測で y=0 が確定した結果、`laser_link` との xy 距離は 44.7mm ではなく 20mm。当初の想定より近い。**無通電でアームを手で振って埋めてください |
| B-2 | **`stow_positions` の妥当性** | 実測値 `[0.0322214631, -1.7951958021, 1.7422605412, -1.7721804713, 1.3709465377]`（pan, lift, elbow, wrist_flex, wrist_roll）。グリッパは `0.0363150868`。**初回は必ず無通電で手を添えて干渉しないことを確認**してください |

### C. 実機でしか分からないこと

| # | 項目 | なぜモックで分からないか |
| --- | --- | --- |
| C-1 | **リーチ中にアームが LiDAR のスキャン平面に入るか** | 前下方へ伸ばすと `scan_filter` の前方 ±60° の窓の**内側**を腕が横切り、slam が自分の腕を含むスキャンでマッチングして**地図が壊れます**。`fake_scan` は自機を持たないので再現できません |
| C-2 | **アームを振ったとき機体がずれるか** | `base_driver` は**指令値**を積分しているので、機体が物理的にずれても**オドメトリにも slam にも一切現れません**。指令ゼロで手で押して動くかを確認します |
| C-3 | 制御周期の超過（overrun） | **★ 実機でも発生**（64.1ms > 20.0ms）。Docker Desktop 固有ではなかった。watchdog 誤発火の要因になりうる |
| C-4 | **サーボのトルク・保持力** | **未解決の既知問題があります**（下記） |
| C-5 | **`stopped_velocity_tolerance` の誤検知** | 結合構成では無効化してありますが、実機の速度推定のノイズを見ていません |
| C-6 | **転倒余裕** | アームは 0.54m まで伸びます。実際の重心は測っていません |

### D. モックで確認済み（実機で再確認するとよい）

- 結合 URDF が `base_footprint` を根とする**単一ツリー**になる
- `/robot_description` の publisher が **1**、`/joint_states` が **2**
- コントローラ 3 種が `arm_` 接頭辞付きの関節で active になる
- `map` → `arm_gripper_frame_link` の TF が繋がる
- 到達可能な目標 → `SUCCEEDED`、手先の実測 TF が目標と一致
- 到達不能な目標 → **軌道トピックに 1 件も出ない**（アームは動かない）
- slam を止める → `REJECTED_STALE_TF` / ベースを止める → `REJECTED_STALE_ODOM`

---

## ★ 精度について

**現実的な誤差は 3〜8cm です。ソルバの許容差 5mm とは別物です。**

| 区間 | 寄与 |
| --- | --- |
| `map` → `odom`（slam_toolbox） | **2〜5cm（支配的）** |
| `base_link` → `arm_mount_link` | **実測済み**（y は CAD の −0.04 でなく 0） |
| `arm_mount_link` → `arm_base_link` | 恒等（向きは仮定どおり） |
| アーム FK | 1〜2cm（肩で 1° = 0.35m 先で 6mm） |

`ACCEPTED` に出る `residual` は**ソルバの残差**であって物理精度ではありません。
混同しないでください。

### 精度が出ないうちにデモしたい場合

目標のフレームは `map` でなくても構いません。`reach.yaml` の `expected_frame` を
`odom` か `base_footprint` にすれば `map`→`odom` の誤差を回避できます
（`odom`→`base_footprint` はオドメトリ積分なので短時間なら正確）。

**「アームが壊れている」のか「地図がずれている」のか**の切り分けにも使えます。

---

## 既知の未解決事項

- **対話操作（rqt のスライダ）で保持力が弱い。** 全関節 `P=16`（STS3215 の
  工場出荷値 32 の半分。lerobot が振動回避で下げた値）。位置制御のトルクは概ね
  `P × 位置偏差`で、スライダ操作は偏差がほぼゼロになるため力が出ません。
  **直す場所は ROS 側ではなく LeRobot の設定**です
- **電源電圧が定格より低い。** サーボは 7.4V 定格ですが静止時の実測は 4.9V。
  上記の一因である可能性がありますが**未検証**（動作中の最低電圧は未測定）。
  **8.0V を超えるとサーボが壊れます。**電源の変更は人間の判断が必要です
- **干渉チェックが一切ありません。** 単一 waypoint なので JTC が関節空間で
  補間し、肘が天板や LiDAR を通り抜ける経路を取りえます。本格運用するなら
  MoveIt が次の一手です
- **`nav2.yaml` の `robot_radius: 0.17` は収納状態の前提です。** 伸ばしたまま
  走ると通れない隙間を計画します。**走行前に stow してください**

## 運用上の注意

- **アームのコンテナを再起動すると、slam が `map`→`odom` を出さなくなります。**
  結合ロボットの `robot_state_publisher` がアーム側に居るためです。
  自動では戻らないので、**ベース側も再起動**してください
- アームのブリッジが故障した場合は、アームだけが脱力します。
  RSP は生き残るのでベースの測位は失われません

---

## 関連ドキュメント

| 内容 | 場所 |
| --- | --- |
| 運用の詳細・故障モード・状態メッセージ一覧 | [`docker/lekiwi_so101_bringup/README.md`](../docker/lekiwi_so101_bringup/README.md) |
| 実機での測定手順（手順 0〜4） | [`docs/agent/request.md`](agent/request.md) |
| 実機担当者向けの安全区分・非常停止 | [`docs/hardware_agent.md`](hardware_agent.md) |
| SO-101 アーム単体 | [`docker/so101_ros2/README.md`](../docker/so101_ros2/README.md) |
| LeKiwi ベース単体 | [`docker/lekiwi_base_ros2/README.md`](../docker/lekiwi_base_ros2/README.md) |
