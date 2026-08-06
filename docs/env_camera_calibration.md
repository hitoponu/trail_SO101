# 環境固定 RealSense の較正手順（実機）

三脚などに据え置いた RealSense D435i の `map` 上の位置姿勢を求める。
求めた点群は RViz でクリックしてリーチ目標にできる。

> **★ この手順を実施するのは、`feat/lekiwi-so101-reach` の実機調整
> （`docs/agent/request.md` の手順 0〜4）が完了してからです。**
> 実機 agent へ依頼するときは、この文書の内容を `docs/agent/request.md` へ
> 転記して送ってください（`request.md` は Mac のみが書き、1 度に 1 依頼）。

---

## 原理: 6 自由度をどう分けているか

| 自由度 | 手段 | なぜそれで決まるか |
| --- | --- | --- |
| roll / pitch | **IMU の重力** | カメラは静止しているので加速度計が読むのは運動加速度の混ざらない純粋な重力。シーンに一切依存しない |
| **z** | **★ メジャーで実測** | 壁は鉛直なので、どの高さで切っても 2D の footprint が同じ。**2D マッチングは z に対して原理的に縮退している**。`map` の z=0 は `base_footprint`（車輪接地面）＝床なので、三脚の床からの高さがそのまま z |
| x / y / yaw | **2D マッチング** | 重力で水平化した点群を水平に切り、slam_toolbox の占有格子へ trimmed ICP で合わせる |

較正ノードは **TF を publish しないし、ロボットも動かしません**。読んで計算して
数値を印字するだけです。反映は人間が `.env` を書き換えて再起動します
（誤った較正が黙って TF に入るのを防ぐため）。

---

## 前提条件（満たせないなら実行せず報告）

1. **`feat/lekiwi-so101-reach` の実機調整が完了していること**
   （特に `arm_mount` の yaw と `laser_link` の実測）
2. **RealSense がロボットと同じ Linux PC に挿さっていること。**
   `ROS_LOCALHOST_ONLY=1` なので別 PC では DDS が繋がりません。
   三脚が離れているなら USB3 アクティブ延長ケーブルを使ってください
3. **保存済み地図があること。** SLAM で毎回地図を作り直すと `map` 原点が変わり、
   較正値は起動のたびに無効になります

---

## 手順

### 手順 C-0 🟢 地図を作って保存する（初回のみ）

```bash
cd docker/lekiwi_so101_bringup
make reach            # SLAM モード。部屋を一周させる
make save-map MAP_NAME=my_room
```

**床に「ホーム位置」をテープで印してください。** 毎回そこから起動すると
amcl の初期姿勢が安定し、較正値の劣化も抑えられます。

`.env` の `MAP_NAME` を合わせてください。

### 手順 C-1 🟢 カメラを設置して高さを測る

三脚に固定します。**★ 以後カメラを動かしたら手順 C-3 からやり直しです。**

- カメラは**ロボットの作業域と、壁の一部が同時に見える**向きに置く
  （壁が写っていないとマッチングの拘束が足りません）
- **★ カメラの光学中心の床からの高さをメジャーで測る**（±1cm）。
  D435i の光学中心は前面の depth モジュール中央です

報告してほしいもの:

- 測った高さ [m]
- カメラのおおよその設置位置（`map` 原点＝ロボットのホーム位置から見て
  前後左右何 m か。**粗くて構いません**。ICP の初期値に使います）
- カメラがどちらを向いているか（`map` の +x を 0 として時計回りに何度か。粗くて可）

### 手順 C-2 🟢 起動して点群と IMU が出ているか確認する

```bash
cd docker/lekiwi_so101_bringup
git pull
make build
make bootstrap        # ★ 飛ばすと起動できません
make reach-with-map
```

別ターミナルで、**以下の生出力をそのまま報告してください**。

```bash
E="docker exec lekiwi-so101-arm /entrypoint.sh"

# 1. ★ 点群のパラメータ名の確定（設計上いちばん不確かな点）
$E ros2 param list /env_camera/env_camera | grep -i pointcloud

# 2. 点群と IMU が流れているか
$E ros2 topic hz /env_camera/env_camera/depth/color/points
$E ros2 topic bw /env_camera/env_camera/depth/color/points
$E ros2 topic hz /env_camera/env_camera/accel/sample

# 3. カメラ内部の TF（フレーム名が env_camera_ になっているか）
$E ros2 run tf2_ros tf2_echo env_camera_link env_camera_depth_optical_frame
$E ros2 topic echo /env_camera/env_camera/accel/sample --once
```

**確認ポイント:**

- 3 のフレーム名が `camera_link` ではなく **`env_camera_link`** になっていること。
  `camera_link` のままなら `camera_name` がパラメータとして効いていません
- 2 の accel の値が、静止時に**ノルム 9.8 前後**であること。
  大きく違えば単位か軸がおかしいので、そこで止めてください

### 手順 C-3 🟢 較正する

**ロボットは動かしません。カメラも動かしません。**

```bash
docker exec lekiwi-so101-arm /entrypoint.sh \
  ros2 run lekiwi_so101_bringup env_camera_calib --ros-args \
    -p camera_height:=<手順 C-1 で測った高さ> \
    -p initial_x:=<粗い x> \
    -p initial_y:=<粗い y> \
    -p initial_yaw:=<粗い yaw [rad]>
```

**出力を丸ごと報告してください。** 成功すると 6 数値と
**残差 RMS / インライア率**が出ます。

失敗する場合、ノードが理由を印字します。よくあるもの:

| 症状 | 対処 |
| --- | --- |
| 入力が揃わない | 印字されるトピック名を見て、点群か IMU が出ていないほうを調べる |
| 加速度計が妥当でない | カメラが揺れている / `enable_imu` が効いていない |
| スライスに点がほとんど無い | `slice_z_min` / `slice_z_max` を実際に壁が写っている高さ帯に変える。`camera_height` が間違っている可能性も |
| インライア率が低い・残差が大きい | 初期値が実際と大きく違う / 帯に壁が写っていない / 地図が古い |

**★ 残差とインライア率も必ず報告してください。** これが**この設置での実測誤差**で、
ドキュメントに書く唯一の根拠になります。

高さ帯を変えて試す場合:

```bash
    -p slice_z_min:=0.3 -p slice_z_max:=1.5
```

### 手順 C-4 🟢 値を反映して確認する

出力の `--- .env へ貼る ---` の 6 行を `docker/lekiwi_so101_bringup/.env` に
貼り、再起動します。

```bash
make down
make reach-with-map
```

確認:

```bash
E="docker exec lekiwi-so101-arm /entrypoint.sh"
$E ros2 run tf2_ros tf2_echo map env_camera_depth_optical_frame
```

RViz で:

1. Fixed Frame が `map` であることを確認
2. Displays の **"Env Camera Cloud" を有効化**（既定は無効）
3. **★ 点群とロボットモデル・地図が重なっているか目視する。**
   ずれていればスクリーンショットを報告してください

### 手順 C-5 🟢 ★ RViz で点群の点をクリックできるか

**これは設計上の未検証事項です。** RViz の `get3DPoint` は描画ジオメトリに
当たらないとイベント自体が起きません。

1. "Publish Point" ツールを選ぶ
2. 点群の点をクリックする
3. `$E ros2 topic echo /so101/reach_status` に何か出るか

**クリックしても何も起きない場合**、RViz 下部のステータスバーに
`Move over an object to select the target point.` と出ているはずです。
その文言が出るかどうかを報告してください（出るなら「当たっていない」、
出ないなら別の問題です）。

代替として `Select` ツールで座標を読み、手打ちで送る方法もあります。

### 手順 C-6 🟡 リーチしてみる（**人が立ち会うこと**）

> **★ アームが実際に動きます。**周囲 35cm を空け、人が電源スイッチに手が
> 届く位置にいること。

1. ロボットを目標の近く（0.5m 以内）へ走らせて**停止**させる
2. 点群上の点をクリックする
3. `/so101/reach_status` を読む

**報告してほしいもの:**

- `/so101/reach_status` の生出力
- **クリックした点と、実際に手先が来た位置の距離を定規で測った値**

`REJECTED_OUT_OF_RANGE` が出る場合は目標が遠すぎます（`max_reach_radius` は
0.55m）。ベースをもっと近づけてください。

---

## 報告のまとめ

1. 手順 C-1 の実測値（高さ、粗い位置と向き）
2. 手順 C-2 の生出力すべて（**特に `ros2 param list | grep pointcloud`**）
3. 手順 C-3 の較正出力（**残差 RMS とインライア率**）
4. 手順 C-4 の目視（点群と地図が重なっているか）
5. 手順 C-5（クリックが当たるか、当たらないならステータスバーの文言）
6. 手順 C-6 の実測誤差

## やらないでほしいこと

- **較正値を推測で `.env` に書くこと。** ノードの出力をそのまま貼ってください
- **較正の途中でカメラや三脚に触ること**
- **手順 C-6 を人がいないときに実行すること**
- 手順 C-3 で残差が大きいまま手順 C-6 へ進むこと（アームが見当違いの方向へ動きます）

---

## 既知の未検証事項

- `pointcloud.stream_filter` の正確なパラメータ名（手順 C-2 の 1 で確定する）
- RViz の Publish Point が点群にヒットするか（手順 C-5）
- D435i の depth 精度と、この設置での実効誤差（手順 C-3 の残差と手順 C-6 の実測）
- カメラの視野に壁が十分入るか（入らないとマッチングの拘束が足りない）
- IMU の外部パラメータが `/tf_static` に出るか（手順 C-2 の 3）
