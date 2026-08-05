# 依頼（Mac → 実機）

- **更新**: 2026-08-05（6回目）
- **状態**: 実行待ち
- **安全区分**: 🟡（実機を起動します。人がアームを支える必要あり）
- **ブランチ**: `feat/lekiwi-so101-reach`

## ★ 前回（5回目・P ゲイン）の依頼は取り下げます

**実行しないでください。** あの依頼は前提が崩れています。

その後 `feat/so101-follower-ros2` が LeRobot ブリッジ方式に書き換わり、
依頼が使っていたものが**すべて無くなりました**。

- `so101_probe`（`--set-pid` を含む）… 削除済み
- `compose.dev.yaml` … 削除済み
- `control/so101_follower.ros2_control.xacro` の `so101_p_gain` … 削除済み

現在はモータ設定・較正・PID の責任がすべて LeRobot 側にあります。
**「対話操作で力が弱い」問題自体は未解決のまま**ですが、直す場所が
ROS 側の xacro ではなく LeRobot の設定に変わりました。別途あらためて依頼します。

---

## 今回やりたいこと

**LeKiwi ベースに SO-101 アームを載せ、`map` 上の点へ手先を伸ばす**構成を
実機で検証したい。ただし**今回は計測と無動作確認まで**です。

**アームを動かす手順（🔴）は今回含めていません。** 手順 0 の実測値が返ってきて
から、それを URDF に反映したうえで別途依頼します。取付位置が未確定のまま
アームを動かすのは危険なので、順番を守らせてください。

## ★ 前提条件（満たせないなら実行せず `保留` で報告してください）

1. **アームが `arm_mount_link` の位置にボルトで固定されていること。**
   テープや両面テープは不可。約 0.75kg のアームを 0.09m 上に片持ちさせるので、
   直径 0.25m の車輪円しか支持多角形が無いこの機体では**転倒しえます**。

2. **udev ルールが 2 つとも入っていること**
   （`docker/lekiwi_base_ros2/99-lekiwi.rules`, `docker/so101_ros2/99-so101.rules`）。
   無いと `/dev/ttyACM*` の列挙順が運任せになり、
   **12V のホイール指令が 7.4V のアームサーボへ飛びえます。**

3. **★ アーム（7.4V）とホイール（12V）が同一シリアルバスに繋がっていないこと。**
   どちらも Feetech STS3215 の 1Mbps で、ID も 1–6 / 7–9 と分かれているため
   **物理的には繋がってしまいます**が、繋いだ瞬間にアーム側が壊れます。
   手順 0 でこれを証明してもらいます。

---

## やってほしいこと

### 手順 0 🟢 実測（今回の主目的）

**定規・ノギスで測って数値で報告してください。** ここが今回いちばん重要です。

現在 URDF に入っている値は **CAD 由来で一度も実測していません**。
特に `laser_link` は仮値（TBD）で、ここが違うと地図が向き依存で歪み、
その誤差がそのまま手先に乗ります。

#### 0-1. `base_link` から見た `laser_link` の位置

`base_link` の原点は **CAD 原点（ベースプレート上面の中心）** です。

```
現在の仮値: xyz = (0.10, 0, 0.03)
```

- x（前方が +）, y（左が +）, z（上が +）を mm 単位で
- LiDAR の**回転中心**を測ってください（筐体の角ではなく）

#### 0-2. `base_link` から見たアーム取付位置と**向き**

```
現在の値: xyz = (0.08, -0.04, 0.057), rpy = (0, 0, 0)
```

- xyz を mm 単位で
- **★ yaw が最重要。** アームのゼロ姿勢で、手先は**機体のどちらを向きますか？**
  - 機体前方 → yaw = 0
  - 機体左 → yaw = +90°
  - 機体右 → yaw = -90°
  - 機体後方 → yaw = 180°
- roll / pitch が 0 でない（傾けて付いている）なら、それも報告してください

#### 0-3. デバイスの識別

```bash
udevadm info -q property -n /dev/lekiwi | grep -i 'ID_SERIAL\|ID_VENDOR\|DEVPATH'
udevadm info -q property -n /dev/so101_follower | grep -i 'ID_SERIAL\|ID_VENDOR\|DEVPATH'
ls -l /dev/lekiwi /dev/so101_follower /dev/rplidar
```

**`ID_SERIAL_SHORT` が 2 つで別物であること**を確認してください。
同じなら udev ルールが機能していません（その場合はそこで止めてください）。

#### 0-4. ★ バス分離の証明

**アームの電源を入れた状態で**、それぞれのポートを個別にスキャンしてください。

```bash
# アーム側: ID 1-6 だけが見えるはず
docker compose -f docker/lekiwi_so101_bringup/compose.yaml run --rm lekiwi-so101-arm \
  python3 -c "
from lerobot.motors.feetech import FeetechMotorsBus
print('スキャン結果:', FeetechMotorsBus.scan_port('/dev/so101_follower'))
"
```

**アーム側のスキャンに 7・8・9 が出たら、そこで止めてください。**
バスが分離されていません（12V がアームに掛かる構成です）。

### 手順 1 🟢 取得とビルド

```bash
git pull
git switch feat/lekiwi-so101-reach
cd docker/lekiwi_so101_bringup
cp .env.example .env      # ★ デバイス名と DIALOUT_GID を実機に合わせる
make build
```

`getent group dialout` の出力も報告してください（`DIALOUT_GID` の確認）。

### 手順 2 🟢 アーム電源 OFF でモック起動

**★ アームの電源を切ってから実行してください。** 何も動きません。

```bash
make mock
```

別ターミナルで:

```bash
make check
```

報告してほしい出力（**そのまま貼ってください**）:

- `/robot_description` の Publisher count → **1 のはず**
- `/joint_states` の Publisher count → **2 のはず**
- `ros2 control list_controllers` → **3 つが active のはず**
- `tf2_echo map arm_gripper_frame_link` の Translation

さらに TF ツリーの PDF を取ってください。

```bash
docker exec lekiwi-so101-arm-mock /entrypoint.sh \
  ros2 run tf2_tools view_frames -o /tmp/frames
docker cp lekiwi-so101-arm-mock:/tmp/frames.pdf ~/frames_mock.pdf
```

`base_footprint` を根に、車輪 3 関節とアーム 6 関節が**1 本の木**に
繋がっていることを確認してください（別々の木に割れていたら報告）。

終わったら `make down`。

### 手順 3 🟡 アーム電源 ON、指令なし（**人がアームを支えること**）

> **★ 起動時に一瞬トルクが抜けます。人が手を添えてから実行してください。**
> 周囲 35cm を空けること。**この手順ではアームを動かす指令は送りません。**

```bash
make reach   # backend は既定で mock なので、実機は下記のように明示する
```

ではなく、明示的に:

```bash
docker compose -f compose.yaml up -d
docker compose exec -it lekiwi-so101-arm /entrypoint.sh \
  ros2 launch lekiwi_so101_bringup reach.launch.py \
    backend:=lerobot robot_id:=<較正ID> start_rviz:=false
```

報告してほしいもの:

```bash
E="docker exec lekiwi-so101-arm /entrypoint.sh"
$E ros2 control list_hardware_components
$E ros2 topic echo /joint_states --once
$E ros2 run tf2_ros tf2_echo base_link arm_gripper_frame_link
```

#### ★ ここが取付位置を確定させる手順です

`tf2_echo base_link arm_gripper_frame_link` が出す Translation と、
**実際の手先の位置を定規で測った値**を突き合わせてください。

- URDF が正しければ 1cm 程度で一致するはずです
- **大きくずれる場合、特に x と y が入れ替わっている・符号が逆なら、
  取付の yaw が 0 ではありません**

両方の数値（TF の出力と実測値）を報告してください。

サーボの温度と電圧も分かれば報告してください。

**停止するときは launch 側で `Ctrl+C`。**
（`docker compose down` では `exec` したプロセスに SIGINT が届かず、
トルクが入ったまま残ります。）

### 手順 4 🟡 車輪を浮かせて短く動かす

> **★ 必ず車輪を床から浮かせてブロック等に載せてから。**

手順 3 の状態のまま、別ターミナルで:

```bash
E="docker exec lekiwi-so101-arm /entrypoint.sh"
$E ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist '{linear: {x: 0.05}}'
```

確認してほしいこと:

1. `map`→`odom` が動くか（`$E ros2 run tf2_ros tf2_echo map odom`）
2. **アームの TF が `base_link` に対して固定のままか**（動いたら結合 URDF がおかしい）
3. `/joint_states` の Publisher count が 2 のままか

#### 4-b 🟢 これも見てほしい（重要）

**指令を送っていない状態で、機体を手で押して動きますか？**

`base_driver` は 0.5 秒の watchdog で指令をゼロにしますが、そのとき
STS3215 が位置を保持するのか、それとも自由に転がるのかを知りたいです。

これは「アームを振ったときに機体がずれるか」を決めます。`base_driver` は
**指令値**を積分してオドメトリを出しているので、機体が物理的にずれても
**オドメトリにも slam にも一切現れません**。押して動くなら、リーチ中の
反動で静かに位置がずれることになります。

- 手で押して**動く** / **動かない**
- 動く場合、どのくらいの力で動くか（指1本で押せる、両手で押す必要がある、等）

---

## 報告してほしいこと（まとめ）

1. **手順 0 の実測値すべて**（`laser_link` xyz、アーム取付 xyz と **yaw**、
   `ID_SERIAL_SHORT` 2 つ、バススキャンの結果）
2. 手順 2 の 4 つの出力と、TF ツリーが 1 本に繋がっていたか
3. 手順 3 の TF 出力と**定規による実測値の突き合わせ**
4. 手順 4 の 3 点、および 4-b（手で押して動くか）
5. 途中で出たエラーや、想定と違った挙動（**要約せず生のまま**）

## やらないでほしいこと

- **リーチ目標を送ること**（`/so101/reach_target` や RViz の Publish Point）。
  取付位置が未確定なので、アームがどこへ向かうか予測できません
- **車輪を接地させたまま `/cmd_vel` を送ること**
- **アームを大きく動かすこと**。今回は計測が目的です
- 取付位置の値を**推測で URDF に書き込むこと**。実測値を報告してもらえれば
  こちらで反映します
