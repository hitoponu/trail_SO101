# 手首カメラ（RealSense D435i）— 実機手順

アームの `arm_gripper_link` に RealSense D435i を載せ、点群を `map` 上に置く。

> **★ 実機 agent へ依頼するときは、この文書の内容を `docs/agent/request.md` へ
> 転記して送ること**（`request.md` は Mac のみが書き、1 度に 1 依頼）。
> **前の依頼（6 回目）が完了しているかを先に確定してから**上書きすること。

---

## ★ この手順の最重要点

**手順 3 と 4（無通電での確認）が終わるまで、カメラを付けた状態で通電しない。**

理由は 2 つ。

1. **保持力。** D435i は約 72g、マウントとケーブルを足すと 100g 級。アームは
   約 750g で、しかも**全関節 `P=16`（工場出荷 32 の半分）で保持力が弱いという
   未解決問題がある**（`docs/hardware_agent.md`）。これは「悪化するか」ではなく
   **「そもそも保持できるか」**の問題。
2. **起動時に一瞬トルクが抜ける。** 先端重量が増えた状態で落ちる。

## 安全区分の補足

`docs/hardware_agent.md` の 🟢🟡🔴 は「ソフトが何をするか」で切られており、
**物理的な取り付け作業という類型が無い**。この手順では次のように扱う。

| 作業 | 区分 | 補足 |
| --- | --- | --- |
| カメラの取り付け・取り外し | 🟡 | **必ずアームの電源 OFF で。**通電中に手を入れるのは 🔴 |
| 無通電で手を離して姿勢保持を見る | 🟡 | アームが落ちる。人が支えられる位置に居ること |
| カメラだけ起動（アーム電源 OFF） | 🟢 | アームに一切触れない |
| `backend:=lerobot` で通電 | 🟡 | **★ カメラ搭載後の初回だけ 2 人で。**1 人がアームを支え、1 人が電源スイッチに手を掛ける |
| リーチ・stow（関節が動く） | 🔴 | `joint_limit_overrides` が埋まってから |

---

## 手順

### 手順 W-1 🟢 ビルド（★ `make build` は必須）

```bash
git pull
git switch feat/wrist-camera
cd docker/lekiwi_so101_bringup
cp .env.example .env      # まだ無ければ
make build
make bootstrap
```

> **★ `make build` を飛ばさないこと。** `realsense_bringup` は**イメージに
> 焼き込まれます**（`docker/realsense_ros2/Dockerfile` が `COPY` して
> `colcon build` する）。ワークスペースのマウントは効きません。
> しかもイメージのタグ `local/realsense-d435i-ros2:jazzy` は単体構成と**同じ**なので、
> 古いイメージが残っていると `docker compose up` は**それを黙って使います**。
> その場合、トピック名は正しいのに **TF は `camera_link` のまま・点群は出ない**
> という分かりにくい状態になります。

`make bootstrap` の静的検査 3 行がすべて `OK` にならなければ、そこで止めて報告。

### 手順 W-2 🟢 カメラだけ起動して素性を確認（★ アームの電源は OFF）

**アームに触れずにカメラ側だけ切り分けます。**

```bash
docker compose -f compose.yaml up -d realsense
R="docker exec lekiwi-wrist-camera /entrypoint.sh"
```

**以下の生出力をそのまま報告してください。**

```bash
# 1. ★ フレーム名が camera_link でなく wrist_camera_link になっているか
#    （camera_name がパラメータとして効いているかの検査。W-1 の警告の症状）
$R ros2 run tf2_ros tf2_echo wrist_camera_link wrist_camera_depth_optical_frame
$R ros2 run tf2_ros tf2_echo wrist_camera_link wrist_camera_depth_frame

# 2. ★ 点群のパラメータ名の確定（設計上いちばん不確かな点）
$R ros2 param list /wrist_camera/wrist_camera | grep -i pointcloud

# 3. 点群が出ているか・帯域
$R ros2 topic hz /wrist_camera/wrist_camera/depth/color/points
$R ros2 topic bw /wrist_camera/wrist_camera/depth/color/points

# 4. ドメインが 7 になっているか（単体構成は既定 0）
docker exec lekiwi-wrist-camera env | grep ROS_DOMAIN_ID
```

**★ 1 で `camera_link` が出たら、そこで止めて報告してください。**
以降すべてが成り立ちません。

### 手順 W-3 🟡 ★ 取り付けて保持力を見る（**電源 OFF。ここが山場**）

> **アームの電源スイッチを OFF にしてから取り付けること。**

カメラを `gripper_link`（グリッパ本体）に固定したら、**無通電のまま**次を見ます。

**いくつかの姿勢でアームを手で作り、手を離してどれだけ下がるかを mm で報告。**

| 姿勢 | 見るところ |
| --- | --- |
| 水平前方へ伸ばす | いちばん厳しい。モーメントが最大 |
| 上方へ立てる | |
| 下方へ向ける | |

**★ 明確に下がるようなら、そこで止めて報告してください。** リーチどころか
起動時の脱力で落ちます。`P=16` の保持力問題が未解決である以上、
これは想定内の結果です。

併せて報告:

- カメラ+マウント+ケーブルの**実重量**（測れれば）
- どこに、どう固定したか（**写真**があると確実）

### 手順 W-4 🟢 無通電で可動域とケーブルを見る

**電源 OFF のまま**、手で全可動域を通します。

1. **干渉。** カメラが `laser_link`（LiDAR）／ベースの天板／`plate2`／
   グリッパの爪（`arm_jaw_link`）に当たる関節角を報告。
   ★ **`laser_link` と `arm_mount_link` は実測で 20mm しか離れていません。**
2. **ケーブル。** `wrist_roll` と `wrist_flex` を全可動域まで回し、
   **ケーブルが突っ張る角度**を報告。どこで機体に固定したか、たるみは何 cm か。
   ★ ケーブルは抵抗トルクにも転倒モーメントにもなります。
3. **`stow` 姿勢。** 現在の `stow_positions` は実測した
   `[0.0322214631, -1.7951958021, 1.7422605412, -1.7721804713, 1.3709465377]`
   です。手でこの姿勢を作り、カメラが機体と干渉しないかを確認してください。
   ★ **`make stow` は停止手順の必須ステップなので、ここが崩れると安全に停止できません。**

この 3 つの結果が `reach.yaml` の `joint_limit_overrides`（現在 `[""]`）と
`stow_positions` に入るまで、**リーチ（🔴）へ進まないでください。**

### 手順 W-5 🟢 webcamの基準位置を `.env` に書く

**`arm_gripper_link` の原点から見た、webcamの基準位置・姿勢**を設定します。
固定台そのものではなく、webcamが載った位置と向きを基準にします。
この段階では、D435iのレンズ中心との差分だけ補正しません。

現在の既定値は、実機で取得した床上の3点から床面が水平になるように補正した値です。
以前の値は **D405 + Wrist_Roll_D405_Holder 前提の幾何計算値**で、手元のD435iの
実測値ではありませんでした。

```dotenv
WRIST_CAMERA_X=-0.00097
WRIST_CAMERA_Y=-0.06748
WRIST_CAMERA_Z=0.03586
WRIST_CAMERA_ROLL=3.03341
WRIST_CAMERA_PITCH=1.26087
WRIST_CAMERA_YAW=1.46705
```

補正に使った床点（`base_link`座標）は次の3点です。

```text
(0.383,  0.0902, -0.0447)
(0.238, -0.2510, -0.0424)
(0.0634,-0.2270, -0.0100)
```

3点から得た床面の法線は約`(0.1731, -0.0670, 0.9826)`、補正後の3点のzは
約`-0.0368 m`で一致しました。さらに一次補正後に取得した次の3点を使い、
残った傾きと高さを二次補正しました。

```text
(0.496, -0.472, -0.069)
(0.470, -0.056, -0.090)
(0.223, -0.364, -0.086)
```

二次補正後は、この3点が`base_link`上で`z=-0.040 m`に揃う想定です。点の丸め誤差と
実機の取付公差は残るため、最終確認はRVizで行ってください。

この値でまずモックを確認し、D435iを載せた実機では点群の方向と位置を確認します。

```dotenv
WRIST_CAMERA_X=...     # arm_gripper_link 原点 → webcam基準位置 [m]
WRIST_CAMERA_Y=...
WRIST_CAMERA_Z=...
WRIST_CAMERA_ROLL=...  # webcam基準姿勢
WRIST_CAMERA_PITCH=...
WRIST_CAMERA_YAW=...
```

webcamの光軸が `arm_gripper_link` のどちらを向いているか（+x / −x / +z / −z など）を
記録してください。ここではD435i固有のレンズ中心補正はまだ行いません。

書いたらモックで確認します（**アームの電源は OFF のまま**）。

```bash
make mock
make check      # map -> wrist_camera_depth_optical_frame の行を見る
```

★ `★ ... が引けない` と出たら TF が繋がっていません。報告してください。

### 手順 W-6 🟡 通電して点群を見る（**★ 2 人で。1 人が支える**）

> **★ カメラを載せた状態での初回通電です。**起動時に一瞬トルクが抜けます。
> 1 人がアームを支え、1 人が電源スイッチに手が届く位置に居ること。
> 周囲 35cm を空ける。**この手順ではアームを動かす指令は送りません。**

```bash
make down                     # モックを完全に落とす（★ TF の二重定義を防ぐ）
docker compose -f compose.yaml up -d
docker compose -f compose.yaml exec -it lekiwi-so101-arm /entrypoint.sh \
  ros2 launch lekiwi_so101_bringup arm.launch.py \
    backend:=lerobot robot_id:=<較正ID>
```

RViz で:

1. Fixed Frame が `map`
2. Displays の **"Wrist Camera Cloud" を有効化**（既定は無効）
3. **★ 点群がロボットモデル・地図と正しい位置関係になっているか目視**。
   ずれていればスクリーンショットを報告
4. **Displays に赤いエラーが出ていないか**（RViz 設定の記述ミスの検査）

```bash
E="docker exec lekiwi-so101-arm /entrypoint.sh"
$E ros2 run tf2_ros tf2_echo map wrist_camera_depth_optical_frame
$E ros2 run tf2_tools view_frames -o /tmp/frames     # ★ ツリーが 1 本か
```

★ `view_frames` の PDF で **`wrist_camera_link` が孤立した第 2 のルートに
なっていないこと**を確認してください。

### 手順 W-7 🟢 ★ 最短測距（用途の成否に関わる）

**静止した状態で**、対象までの距離を変えながら点群が出るかを見ます。

| 距離 | 点群が出るか |
| --- | --- |
| 0.10 m | |
| 0.20 m | |
| 0.30 m | |
| 0.50 m | |

**D435i の最短測距は約 0.1〜0.2m です。手首カメラは対象に近づくので、
リーチ目標の距離では測距範囲を下回る可能性があります。**
ここが成り立たないと手首カメラの用途自体を見直すことになるので、
早めに確認してください。

併せて、**点群に自分のグリッパの爪（`arm_jaw_link`）が写るか**、
写るなら距離いくつかも報告してください。

### 手順 W-8 🟡 腕を動かして TF が追従するか

> **★ 関節が動きます。人が立ち会うこと。**W-4 の干渉確認が済んでいること。

小さく動かして、点群が `map` 上で正しく動くかを見ます。

```bash
$E ros2 run tf2_ros tf2_echo map wrist_camera_link      # 動かす前
# rqt か軌道アクションで小さく動かす
$E ros2 run tf2_ros tf2_echo map wrist_camera_link      # 動かした後
```

★ **移動中の点群は信用しないでください。**深度は動くと荒れます。
静止してから見ること。`temporal_filter` は既定 false にしてありますが、
静止して撮るなら `temporal_filter:=true` で改善するかも見てください。

---

## 停止手順

**★ 順番を守ること。正常終了でトルクが切れてアームが落ちます。**
カメラを載せたぶん、落ちる勢いが増えています。

```bash
make stow     # 1. 畳む（★ W-4 で干渉しないことを確認済みであること）
make down     # 2. bridge を shutdown してトルク OFF 後、コンテナを停止
```

---

## 報告してほしいことのまとめ

1. W-2 の生出力すべて（**特にフレーム名とパラメータ名**）
2. **W-3 の保持力**（姿勢ごとの下がり量 mm、実重量、写真）← 最重要
3. W-4 の干渉角・ケーブルの突っ張り角・stow 姿勢の可否
4. W-5 の実測値とレンズの向き
5. W-6 の目視（点群と地図の重なり、RViz のエラーの有無、`view_frames` の PDF）
6. W-7 の距離ごとの可否
7. 途中で出たエラー（**要約せず生のまま**）

## やらないでほしいこと

- **W-3・W-4 が終わる前に通電すること**
- **`joint_limit_overrides` が空のままリーチを送ること**
- 取付姿勢を推測で `.env` に書くこと（実測値を報告してもらえれば Mac 側で反映します）
- カメラを載せたまま `make stow` の干渉確認を飛ばすこと

---

## 既知の未検証事項

- `pointcloud` 系パラメータの正確な名前（W-2 の 2 で確定する）
- 帯域と RViz のフレームレート
- カメラ+マウントの実重量と、`P=16` の保持力問題への影響（W-3）
- USB3 ケーブルがどれだけ可動域を削るか（W-4）
- D435i の最短測距がこの用途で足りるか（W-7）
- `wrist_camera_link` と D435i の左 IR イメージャ中心との補正は未実施
