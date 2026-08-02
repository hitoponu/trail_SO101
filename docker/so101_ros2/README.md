# SO-101 フォロワアーム + ROS 2 Jazzy + Docker

単体の SO-101 アーム（Feetech STS3215 × 6、モータ ID 1–6）を ROS 2 の
`ros2_control` で駆動する構成です。`FollowJointTrajectory` で関節を動かし、
グリッパを `GripperActionController` で開閉できます。

サーボ制御には apt で配布されている
[`feetech_ros2_driver`](https://github.com/ros-physical-ai/feetech_ros2_driver)
（OSRA Physical AI SIG、BSD-3）を使い、URDF は
[`ros2_so_arm`](https://github.com/ros-physical-ai/ros2_so_arm) の
`so_arm101_description` を取り込みます。自前で書いているのは launch と設定、
そして較正まわりのツールだけです。

## 安全上の注意

**必ず先に読んでください。アームは自重で落ちます。**

- **正常終了（`Ctrl+C` / `docker compose down`）でアームは脱力して落ちます。**
  `feetech_ros2_driver` の `on_deactivate()` が全関節のトルクを切るためです。
  **停止する前に必ず低く畳んだ姿勢へ動かしてください。**
- **`docker kill -s SIGKILL` ではトルクは切れません**（その場で凍結します）。
  「今すぐ動きを止めたいが落としたくない」ときはこちらです。ただしサーボは
  保持し続けるので発熱します。
- **起動時に一瞬だけ脱力します。** ドライバが `on_init` で EEPROM を書くために
  一度トルクを切るためです。**初回は手で支えてください。**
- **ROS を起動する前に必ずアームの電源を入れ直してください。**
  サーボの `Goal_Position` に前回セッションの値が残っていると、
  トルクが入った瞬間にそこへ飛びます。
- 半径 35cm 以内を空け、肘の下に発泡ブロックなどの受けを置いてください。
- **アーム専用電源のスイッチが唯一の物理的な非常停止です。** 手の届く所に。
- lerobot 側のプロセスを止めてください。同じポートを二重に開けません。

> この機体は LeKiwi とは**別のアーム**で、自前の 5V/7.4V 電源を持ちます。
> LeKiwi の 12V バスとは無関係なので、電圧に関する制約はありません。
> （LeKiwi 搭載のアームは 7.4V 版で 12V バスに繋いではいけません。別の話です。）

### 非常停止の一覧

| 状況 | 操作 | トルク | 結果 |
| --- | --- | --- | --- |
| 今の動作だけ止めたい | 実行中の `send_goal` を `Ctrl+C`（goal cancel） | ON | その場で保持。**最速のソフト停止** |
| 制御を切り離したい | `ros2 control switch_controllers --deactivate joint_trajectory_controller` | ON | 最後の指令位置で保持 |
| 動きを凍結したい | `docker kill -s SIGKILL so101-follower` | ON | 凍結（発熱注意） |
| 通常終了 | `Ctrl+C` / `docker compose down` | **OFF** | **脱力して落ちる** |
| 完全停止 | アーム電源スイッチ OFF | **OFF** | **脱力して落ちる**。唯一の物理的非常停止 |

## 前提

- Linux ホスト（X11 または XWayland を利用できるデスクトップ環境）
- Docker Engine と Docker Compose v2
- SO-101 フォロワアーム、WaveShare サーボコントローラ、専用電源

> macOS では Docker にシリアルデバイスを渡せないため実機制御はできません。
> ただし**モックでのドライラン（後述の手順4）は macOS でも実行できます。**
> Mac から直接アームを動かす場合は `examples/record_and_move.py` を使ってください。

以下のコマンドは、この README があるディレクトリで実行します。

```bash
cd docker/so101_ros2
```

## 1. USBデバイスを確認する

```bash
ls -l /dev/ttyACM* 2>/dev/null
dmesg --follow
udevadm info --attribute-walk --name=/dev/ttyACM0 | grep -m1 'ATTRS{serial}'
```

**★ VID:PID ではなく `ATTRS{serial}` で識別します。**
SO-101 の基板と LeKiwi ベースの基板は同じ WaveShare 設計で **VID:PID が同一**です。
VID:PID でルールを書くと `/dev/lekiwi` と `/dev/so101_follower` が
同じ基板を指してしまいます。

確認したシリアルを `99-so101.rules` に反映してからコピーします。

```bash
sudo cp 99-so101.rules /etc/udev/rules.d/99-so101.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
# 反映されない場合はUSBを抜き差しする
ls -l /dev/so101_follower
sudo usermod -aG dialout "$USER"   # 追加後は再ログインが必要
```

LeKiwi の基板も繋いでいる場合は、`/dev/lekiwi` と `/dev/so101_follower` が
**別の** `ttyACM*` を指していることを必ず確認してください。

**できれば USB ハブを使わず PC へ直結してください**（禁止ではありません。後述）。
ドライバのシリアル read タイムアウトは **5ms** で、タイムアウトした場合の
リトライがありません。通信エラーが1回起きると `read()` が ERROR を返し、
ハードウェアコンポーネントがエラー状態へ落ちて**制御が切れます**
（トルクは入ったままなので、アームは最後の指令位置で止まります）。
復帰にはスタックの再起動が必要です。

ハブを使う場合の注意点。

- **バスパワーハブでも問題ありません。** サーボの電源は基板の DC ジャックから
  別途供給されており、USB から取るのはブリッジ IC とロジックの分だけなので
  消費はごくわずかです
- **カメラなど帯域を食うデバイスと同じハブに挿さない** — これが一番効きます。
  リスクは電力ではなく帯域と遅延です
- 安価なハブは避ける

`99-so101.rules` の `ID_MM_DEVICE_IGNORE`（ModemManager 対策）は
ハブの有無に関わらず必要です。

## 2. 環境ファイルを作る

```bash
cp .env.example .env
sed -i "s/^DIALOUT_GID=.*/DIALOUT_GID=$(getent group dialout | cut -d: -f3)/" .env
```

## 3. RViz用のX11アクセスを許可する

```bash
xhost +si:localuser:root
```

## 4. モックでドライランする（実機に一切触れない）

**実機を繋ぐ前に必ずここを通してください。** シリアルポートを開かないので
リスクはゼロです。既定値が `mock_components` なので引数は要りません。

```bash
docker compose build
docker compose up
```

別ターミナルで確認します。

```bash
docker compose exec so101-follower ros2 control list_hardware_components
docker compose exec so101-follower ros2 control list_controllers
docker compose exec so101-follower ros2 action list
docker compose exec so101-follower ros2 topic echo /joint_states --once
```

期待する状態:

```
SO_ARM101  system  mock_components/GenericSystem  active

forward_position_controller  position_controllers/JointGroupPositionController           inactive
gripper_controller           parallel_gripper_action_controller/GripperActionController  active
joint_trajectory_controller  joint_trajectory_controller/JointTrajectoryController       active
joint_state_broadcaster      joint_state_broadcaster/JointStateBroadcaster               active

/gripper_controller/gripper_cmd
/joint_trajectory_controller/follow_joint_trajectory
```

`forward_position_controller` だけ `inactive` なのは意図的です
（JTC と同じ command interface を奪い合うため。診断用の逃げ道として置いてあります）。

モック相手に指令を投げて経路全体を検証します。

```bash
docker compose exec so101-follower ros2 action send_goal \
  /joint_trajectory_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory \
  "{trajectory: {joint_names: [shoulder_pan_joint, shoulder_lift_joint, elbow_flex_joint, wrist_flex_joint, wrist_roll_joint],
     points: [{positions: [0.3, 0.0, 0.0, 0.0, 0.0], time_from_start: {sec: 3}}]}}" --feedback

docker compose exec so101-follower ros2 action send_goal \
  /gripper_controller/gripper_cmd control_msgs/action/ParallelGripperCommand \
  "{command: {name: [gripper_joint], position: [0.5]}}" --feedback
```

RViz でモデルが動けば、URDF → コントローラ → TF の経路は正常です。

**★ このときの RViz のゼロ姿勢（全関節 0）を写真に撮っておいてください。**
手順6でこれを基準に使います。

## 5. 実機: 通信だけ確認する（ROS を起動しない）

`.env` の `SO101_DEVICE=/dev/so101_follower` に変更し、**アームの電源を入れ直して**から:

```bash
docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_probe --port /dev/so101_follower --scan
```

期待: ID 1–6 が `model 777`（STS3215）で応答し、電圧が 6.0–8.4V。

読み取れた `Homing offset` / `Min` / `Max` を lerobot の較正値と突き合わせます
（`~/.cache/huggingface/lerobot/calibration/robots/so_follower/*.json`）。
一致していれば、ROS 側は lerobot とまったく同じ較正値を使うことになります。

## 6. 実機: 回転方向を確認し、ゼロ点を合わせる

ドライバは `on_init` でトルクを入れてしまうので、`ros2_control` が動いている
状態ではアームを手で動かせません。トルクを切って生の値を読む計測器を使います。

```bash
docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_probe --port /dev/so101_follower --torque-off --watch
```

### 6.1 回転方向を確認する（これは必須）

#### まず「+ 方向」がどっちかを実機なしで確認する

頭の中で右ねじを考える必要はありません。**スライダを動かして見るのが確実です。**
実機に触れないので、これは Mac でもできます。

```bash
docker compose run --rm --service-ports so101-follower \
  ros2 launch so_arm101_description view_description.launch.py rviz:=true
```

`joint_state_publisher_gui` のスライダが関節ごとに出ます。
**各関節のスライダを + 側（右）へ動かし、モデルがどちらへ回るかを記録します。**
定義上これが + 方向なので、解釈の余地がありません。

6関節ぶん、次のようにメモしておきます（実際の向きは実物で確認してください）。

| 関節 | + 方向 |
| --- | --- |
| `shoulder_pan_joint` | （例）上から見て◯◯回り |
| `shoulder_lift_joint` | （例）前へ倒れる／起き上がる |
| … | … |

> 理屈で確認したい場合: SO-101 は6関節とも `<axis xyz="0 0 1"/>` なので、
> **子リンクのフレームの Z 軸（RViz の TF 表示で青）に右手の親指を向けたとき、
> 指の巻く向き**が + です。子リンクは順に `shoulder_link` / `upper_arm_link` /
> `lower_arm_link` / `wrist_link` / `gripper_link` / `jaw_link`。

#### 次に実機で確かめる

`so101_probe --torque-off --watch` を出したまま、**1関節ずつ**、
上で調べた **+ 方向へ手で押して `Present` が増える**ことを確認します。

`Present` が**減る**関節は、サーボの回転方向が URDF の軸と逆です。
ドライバに反転パラメータはないので、URDF の `<axis xyz>` の符号を
ローカルで反転させるしかありません（`homing_offset` では方向は直せません）。

### 6.2 ゼロ点は可動域から計算できる（目測不要・推奨）

**姿勢を手で作る必要はありません。**

SO-101 の new_calib の規約は「各関節の仮想ゼロ＝**可動域の中間**」です。
そして lerobot の較正はすでに `record_ranges_of_motion` で
**機械的な可動端**を記録しています。可動端は客観的で再現性があるので、
そこからゼロ位置を逆算できます。

**較正値はサーボの EEPROM から直接読めます。lerobot の JSON は不要です。**

```bash
docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_calib \
    --from-servos --port /dev/so101_follower --from-ranges --emit-ranges
```

> lerobot の較正キャッシュ（`~/.cache/huggingface/...`）は
> **較正を実行した PC のホームにしか存在しません**。別の PC で作業している場合、
> そのパスを `-v` でマウントしようとすると Docker が空ディレクトリを作り、
> `IsADirectoryError: Is a directory: '/calib.json'` になります。
> `--from-servos` ならこの問題自体が起きません。
>
> JSON から読みたい場合は `--json <path>` を使います（両者は排他）。

この機体の較正値では次のように出ます。

```
shoulder_pan   Δ =   +62 tick (  +5.4°)
shoulder_lift  Δ =   -11 tick (  -1.0°)
elbow_flex     Δ =  -120 tick ( -10.5°)
wrist_flex     Δ =   -39 tick (  -3.4°)
gripper        Δ =  -790 tick ( -69.4°)
```

非対称な limit（`elbow_flex` は `-1.69..+1.54`）にも対応するため、単純な中点では
なく「limit 内でのゼロの位置比率」で内挿しています。
グリッパは URDF のゼロが「閉」＝可動端なので別式です。

#### この方法の前提と例外

- **較正時に機械的な可動端まで振り切れていること。** 途中で止めていると中点が
  ずれます。再スイープして `range_min`/`range_max` が再現するかで検証できます
- **`wrist_roll` は計算できません。** lerobot がフルターン扱いにして可動域を
  記録しない（`0..4095` 固定）ためです。この関節だけ `--delta wrist_roll=...` で
  個別に与えるか、6.3 の反復補正で合わせます
- **グリッパは「どちらの可動端が閉か」だけ確認が必要です。** 既定は `range_min`。
  逆なら `--gripper-closed max` を付けます。閉じながら `so101_probe` で
  `Present` を見れば一目で分かります

裏付けとして、実測可動域は URDF の limit より片側 5〜16° 広く、
**実測＝機械的ストッパー / URDF＝保守的なソフトリミット**という関係と整合しています。

### 6.3 どこまで精度が要るか

必要な精度は用途次第です。

| 用途 | 必要精度 | 根拠 |
| --- | --- | --- |
| 関節を動かす / RViz と一致させる（このマイルストーン） | **数度で十分** | ずれても表示が少し傾くだけ |
| MoveIt、物を掴む | 1° 程度 | 腕長 0.3m で **1° ≈ 5mm**、5° ≈ 26mm |

エンコーダの分解能は 1 tick = **0.088°**（手先 0.46mm）なので、精度の制約は
機械側ではなく手法側です。ちなみに姿勢を目視で合わせる精度は ±2〜5° 程度で、
6.2 の計算（可動端由来）より一桁粗くなります。**だから目測はしません。**

`--from-ranges` を使わずに Δ=0 のまま始めることもできます。上の表のとおり
`elbow_flex` 以外は数度以内なので、このマイルストーンの範囲なら実害はありません。

### 6.4 仕上げ: RViz と実物のずれで検証する

計算したΔが正しいかは、**RViz と実物を見比べる**のが最終確認です。
ずれていた場合の補正もここで行います（`wrist_roll` はこの方法でしか合わせられません）。

1. 6.2 で生成した設定で手順7へ進んで起動する
2. RViz と実物を見比べ、ずれている関節について「何度ずれているか」だけ目測する
3. `Δ[tick] = ずれ角[°] × 11.38` を足して `so101_joints.yaml` を更新、再ビルド
4. 再起動して確認。必要なら繰り返す

**絶対姿勢を作るのではなく「差」を読むだけ**なので、目測でも十分な精度が出ます。
2〜3回で収束します。

> さらに精度が要る場合は、平らな印刷面に**水平器やスコヤを当てる**方法があります。

### 6.5 設定ファイルへ反映する

6.2 のコマンドの標準出力を
`ros2_ws/src/so101_bringup/config/so101_joints.yaml` へ書き出し、
`docker compose build` し直します（`-o` で直接書き出すこともできます）。

Δ を手で与えたい／6.4 で補正した分を足したい場合は `--delta` を併用します。
`--from-ranges` の結果を関節ごとに上書きできます。

```bash
    --json /calib.json --from-ranges --emit-ranges \
    --delta wrist_roll=-25,elbow_flex=-140
```

生成されたファイルは `homing_offset` が `±2047` を超えないこと、
`range_*` が `0..4095` に収まることを自動で検査します（超えると却下されます。
ドライバが `on_init` でクラッシュするためです）。

### 6.6 lerobot の較正 JSON は必須ではない

**較正値の実体はサーボの EEPROM にあり、JSON はその控えにすぎません。**

ドライバは `homing_offset` / `range_min` / `range_max` が設定に書かれている
ときだけ該当レジスタを書きます（`configure_joints_` は各パラメータについて
「キーが存在すれば書く」という実装）。既定の `so101_joints.yaml` は
**Phase 1**（これらを書かない）状態なので、**JSON が手元に無くても動きます。**
サーボに入っている較正値がそのまま使われます。初回の実機起動はこれで構いません。

JSON が要るのは `so101_calib` で明示的な YAML を作るとき（Phase 2）だけです。
その目的は再現性で、サーボを工場出荷リセットしても設定を復元できる、
2台目の機体に同じ設定を配れる、という利点があります。

JSON が無い場合は **`so101_calib --from-servos`** が EEPROM から
`Homing offset` / `Min` / `Max` を読んで直接 YAML を起こします（6.2 参照）。
lerobot の較正キャッシュは実行した PC のホームにしか無いので、
**別の PC で作業する場合はこちらが本筋**です。

ただし、**一度も較正していないサーボはどこかで較正する必要があります**
（lerobot の `lerobot-calibrate` でも、手で書いても構いません）。
較正されていないと関節角のゼロ点も可動範囲もでたらめになります。

## 7. 実機: 起動して静止を確認する

**アームの電源を入れ直し、手で支えてから:**

```bash
HARDWARE_TYPE=real docker compose up
```

一瞬脱力してから保持に入ります。

```bash
docker compose exec so101-follower ros2 control list_hardware_components
docker compose exec so101-follower ros2 topic hz /joint_states     # 約 50 Hz
```

**まだ何も指令しないでください。** RViz の表示と実物を**2方向から**見比べます。
すべての関節が数度以内で一致していれば次へ進めます。

ずれている関節があれば、**何度ずれているかを目測して 6.4 の補正**を回します
（`Δ[tick] = ずれ角[°] × 11.38`）。`wrist_roll` はここでしか合わせられません。
2〜3 周で収束します。

> `/joint_states` の `velocity` は信用できません（後述の既知バグ）。
> `position` だけを見てください。

## 8. 実機: 1関節ずつ小さく動かす

落下を起こしにくい順に:

**wrist_roll → gripper → wrist_flex → elbow_flex → shoulder_pan → shoulder_lift（最後、必ず手を添える）**

現在の `/joint_states` の値から、**1関節だけ ±0.10 rad** 変えて **4秒かけて**送ります。

```bash
docker compose exec so101-follower ros2 action send_goal \
  /joint_trajectory_controller/follow_joint_trajectory \
  control_msgs/action/FollowJointTrajectory \
  "{trajectory: {joint_names: [shoulder_pan_joint, shoulder_lift_joint, elbow_flex_joint, wrist_flex_joint, wrist_roll_joint],
     points: [{positions: [0.0, 0.0, 0.0, 0.0, 0.10], time_from_start: {sec: 4}}]}}" --feedback
```

毎回: 向きが RViz と一致するか / 動く量が約 0.10 rad（約 5.7°）か /
`SUCCEEDED` で返るか / 静止時に唸っていないか、を確認します。

**`time_from_start` は必ず数秒取ってください。** ドライバは書き込みごとに
`speed=2400`（約 210 deg/s）をハードコードで送るため、大きな位置差を一度に
指令するとその速度で飛びます。JTC が補間してくれるので細かい差分に分かれる、
というだけで守られています。

同じ理由で、**`forward_position_controller` は 0.05 rad 以下の微調整以外に
使わないでください**（補間なしで指令が飛びます）。

向きとゼロ点が全部確認できたら、対話的なツールが使えます。

```bash
docker compose exec -it so101-follower \
  ros2 run rqt_joint_trajectory_controller rqt_joint_trajectory_controller
```

## 9. 実機: 全関節の軌道とグリッパ

ホーム → 控えめな姿勢 → ホーム を各6秒で。RViz が実物に追従することを確認します。

```bash
docker compose exec so101-follower ros2 action send_goal \
  /gripper_controller/gripper_cmd control_msgs/action/ParallelGripperCommand \
  "{command: {name: [gripper_joint], position: [0.6]}}" --feedback
```

半開き（0.6）から始め、柔らかいものを掴んで閉じる（0.05）を試します。
`allow_stalling: true` なので、掴んで止まっても成功で返ります。

## 10. 停止する

**JTC で低く自立する姿勢へ動かしてから** `Ctrl+C` してください。

## トラブルシュート

### `No such file or directory: /dev/so101_follower`

`ls -l /dev/ttyACM*` で実際のデバイスを確認し `.env` の `SO101_DEVICE` を直します。
コンテナ起動後に接続した場合は `docker compose down && docker compose up` が必要です。

### `Permission denied`

```bash
ls -ln /dev/so101_follower
getent group dialout
grep DIALOUT_GID .env
```

デバイスのグループIDと `.env` の `DIALOUT_GID` が一致すること。
グループ追加後に再ログインしていない場合も反映されません。

### 応答しないモータがある

- アームの電源が入っているか（サーボは USB からは給電されません）
- デイジーチェーンのコネクタ
- `so101_probe --scan` で ID ごとの応答を確認（`model 777` が正常）

### 散発的に通信エラーが出る / 突然アームが止まって制御が効かなくなる

read タイムアウトは 5ms しかなく、タイムアウト時のリトライがないため、
通信エラー1回でハードウェアコンポーネントがエラー状態へ落ちます。
**トルクは入ったままなのでアームは落ちませんが、その場で固まって指令を
受け付けなくなります。** 復帰にはスタックの再起動が必要です。

原因の切り分け順:

1. **ModemManager** が接続直後にポートを探っている（最も多い）。
   `99-so101.rules` を導入したか、`systemctl status ModemManager` を確認
2. **USBハブ** — カメラなど帯域を食うデバイスと同じハブに挿していないか確認
   （バスパワーかどうかは関係ありません）。切り分けとして一度直結してみる
3. ケーブルの品質・長さ、コネクタの接触

### `Command of at least one joint is out of limits` が ERROR で出続ける

**これは正常動作です。** `enforce_command_limits: true` により、URDF の
`<limit>` を超える指令がクランプされたことを知らせています。故障ではありません。
関節の速度上限（10 rad/s）に当たった場合も同じログが出ます。

### 軌道が必ず `GOAL_TOLERANCE_VIOLATED` で失敗する

`config/ros2_controllers.yaml` の `stopped_velocity_tolerance` が `0.0` に
なっているか確認してください。ドライバの velocity が信用できないため
（後述）、既定値のままだとゴール到達判定が必ず失敗します。

### グリッパのアクションが返ってこない

同じく velocity バグの影響です。`stall_velocity_threshold` を大きく
（100.0）してあるか確認してください。

### RVizが開かない／QtまたはGLXエラー

```bash
echo "$DISPLAY"; ls -l /tmp/.X11-unix; xhost
```

`xhost +si:localuser:root` をデスクトップにログインしているユーザーの端末から
再実行してください。設定変更後は `docker compose down && docker compose up --force-recreate`。

## 既知の問題（上流）

### 1. ドライバの velocity が符号を復号していない

`feetech_ros2_driver` v0.2.2 の `read()` は `Present_Speed`（reg 58、
sign-magnitude 符号ビット15）をそのまま使っており、**負方向の速度が
約 +50 rad/s と読めます**。

- `/joint_states` の `velocity` は信用できません（`position` のみ）
- `config/ros2_controllers.yaml` の `stopped_velocity_tolerance: 0.0` と
  `stall_velocity_threshold: 100.0` は**この回避策**であって好みの設定ではありません

### 4. 通信エラーからの自動復帰が無い

read タイムアウトは 5ms で、タイムアウト時のリトライがありません。
1回でも失敗すると `read()` が ERROR を返し、ハードウェアコンポーネントが
エラー状態へ遷移して制御が切れます（`component.error()` が呼ばれる経路で、
`on_deactivate()` は通りません）。

**このときトルクは切れません。** STS3215 にコマンドウォッチドッグは無いので、
サーボは最後の指令位置を保持し続けます。アームは落ちませんが固まります。
復帰には `docker compose down && docker compose up` が必要です。

ModemManager 対策と USB 接続の品質が効くのはこのためです。

### 2. 上流の ros2_control xacro に3つのバグがある

`so_arm101_description/control/so_arm101.ros2_control.xacro` には:

1. `<param name="offset">` — ドライバ側で**非推奨・無視される**
2. `p_cofficient`（`e` 抜けの綴り間違い）— **PID 値が一切書き込まれない**
3. `joint_config_file` が無い — **較正 YAML を渡す口が無い**

このため `so101_bringup/control/so101_follower.ros2_control.xacro` で
丸ごと差し替えています（親 xacro の `ros2_control_file:=` 引数を使うので
URDF 本体はフォークしていません）。ビルド時にこれらが混入していないことを
自動検査しています。

### 3. 速度・加速度がハードコード

`write()` は毎回 `speed=2400, accel=50` を送ります（設定不可）。
`time_from_start` を長めに取る必要があるのはこのためです。

## ファイル構成

- `Dockerfile`: ROS 2 Jazzy、feetech_ros2_driver（apt）、上流の取り込み、ビルド時検査
- `compose.yaml`: シリアルデバイス、ホストネットワーク、X11。停止シグナルの扱い
- `99-so101.rules`: `ATTRS{serial}` による `/dev/so101_follower` 固定、ModemManager 除外
- `../../ros2_ws/so101_upstream.repos`: 上流 `ros2_so_arm` のコミット固定
- `../../ros2_ws/src/so101_bringup`: launch、コントローラ設定、ros2_control xacro、較正ツール

上流: https://github.com/ros-physical-ai/ros2_so_arm
ドライバ: https://github.com/ros-physical-ai/feetech_ros2_driver
SO-101 本体: https://github.com/TheRobotStudio/SO-ARM100
