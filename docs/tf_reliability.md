# TF の信頼性一覧

`map` から手先・センサまでの各区間が**何に由来し、どれだけ信用できるか**。

リーチの目標誤差はこの連鎖の積み上げなので、**手先がずれたときにどこを疑うか**の
索引として使う。数値は 2026-08-07 時点。

> ★ ここに書いた誤差は、断りがなければ**見積り**であって実測ではない。
> 「実測」と明記したものだけが測った値。

---

## 信頼度の低い順

| # | 区間 | 由来 | 信頼度 | 影響 |
| --- | --- | --- | --- | --- |
| 1 | `arm_gripper_link → wrist_camera_mount_link → wrist_camera_link` | **持っていない機材の幾何計算** | ★最低 | 点群が丸ごとずれる |
| 2 | `odom → base_footprint` | **指令値の積分**（実測ではない） | ★低 | 走行中に累積。slam が直すまで戻らない |
| 3 | `map → odom` | slam_toolbox / amcl | 低（2〜5cm） | **リーチ誤差の支配項** |
| 4 | `base_link → camera_mount_link` | CAD 由来・未実測・**未使用** | 低 | 現状どこからも使われていない |
| 5 | アームの関節角（`arm_base_link` … `arm_gripper_link`） | サーボ EEPROM の較正値 | 中 | 1° で 0.35m 先が 6mm |
| 6 | `base_footprint → base_link` | 公称車輪半径からの導出 | 中〜高（±0.8mm） | 小さい |
| 7 | `base_link → laser_link` | **実測済み** | 高 | 地図の歪みに効く |
| 8 | `base_link → arm_mount_link` | **実測済み** | 高 | リーチに直接効く |
| 9 | `wrist_camera_link → *_optical_frame` | カメラの工場出荷値 | 高 | 小さい |
| 10 | アーム内部のリンク寸法 | 上流 CAD | 高 | 小さい |

---

## 個別

### 1. ★最低 — 手首カメラの取付（`arm_gripper_link → wrist_camera_link`）

```
arm_gripper_link → wrist_camera_mount_link   xyz=(0,0,0) rpy=(0,0,0)
wrist_camera_mount_link → wrist_camera_link  xyz=(0,-0.07112,-0.02074)
                                             rpy=(3.14159, 1.13445, 1.57080)
```

**この値は D405 + 公式 `Wrist_Roll_D405_Holder` を前提に STL から幾何計算したもの。**
手元のカメラは **D435i** で、**SO-101 用の公式マウントが存在しない**
（公式 D435 マウントは SO-100 専用で SO-101 の手首に受け穴が無い）。

→ **この値がそのまま正しくなる構成は現時点で存在しない。**
実測（`docs/wrist_camera.md` の手順 W-5）で置き換わるまで、点群の絶対位置は信用しない。

さらに、幾何計算そのものにも:
- ±2mm / ±2° 程度の残差（円筒検出が面取りを拾う、3D プリントの公差）
- **roll に ±180° の曖昧さ**が残る（カメラ y 軸がネジ 2 本の線に平行なところまでしか
  幾何では決まらない。RViz で画像を 1 枚見れば判別できる）

### 2. ★低 — `odom → base_footprint`

**`base_driver` は送った指令値を積分している。実測ではない。**
スリップも外乱も**アームを振った反動も**現れない。

> 約 0.75kg のアームがオムニ車輪の上で振れれば実際の姿勢はずれるが、
> **オドメトリにも slam にも見えない**（`minimum_travel_distance: 0.1` なので
> 3cm のずれでは再マッチが起きない）。

短時間・静止中なら誤差は小さいので、`expected_frame` を `odom` にすると
`map→odom` の誤差を避けられる（`reach.yaml` 参照）。

### 3. 低 — `map → odom`（2〜5cm、リーチ誤差の支配項）

slam_toolbox（SLAM 構成）または amcl（保存地図構成）が出す。

- A1M8 の測距精度は距離の約 1%（3m で ±3cm）
- `base_link → laser_link` の xy 誤差は**回転時のてこ比**として効くので、
  誤差が**向き依存**になる

**★ 較正をリーチ直前にやり直せば、この項は代数的に消える**（環境固定カメラの
設計で使った性質。`map` と `odom` が式から落ちる）。手首カメラは URDF 固定なので
この技は使えない。

### 4. 低 — `base_link → camera_mount_link`（未使用）

`xyz=(0.1, -0.02, 0.05)`。CAD 由来で未実測。
**手首カメラ構成では使っていない。**将来ベースにカメラを載せるときのための予約。

### 5. 中 — アームの関節角

リンク寸法は上流 CAD で正確だが、**関節のゼロ点はサーボ EEPROM の較正値**に依存する。
実機では起動時に LeRobot の較正 JSON から `range_min/max` を rad へ変換して
URDF の関節 limit に反映している（`calibration_limits.py`）。

肩で 1° の誤差 = 0.35m 先で 6mm。4 関節ぶん積み上がる。

### 6. 中〜高 — `base_footprint → base_link`

`z = wheel_radius(0.05) − axle_z(0.01786) = 0.03214`。
CAD 実測は `0.032924`（そのとき車輪半径 0.050784）なので **約 0.8mm** の差。
公称値を使っても車輪が接地するよう導出式にしてある。

### 7. 高 — `base_link → laser_link`（実測済み）

`xyz=(0.10, 0, 0.03)`、`yaw=−7°`（`−0.1221730476 rad`）。
xyz は仮値と一致し、yaw だけ補正が入った。

### 8. 高 — `base_link → arm_mount_link`（実測済み）

`xyz=(0.08, 0.00, 0.057)`、rpy 0。
★ **CAD の `y=−0.04` は誤りで、実測は `y=0` だった。**
その結果 `laser_link`(0.10, 0) との xy 距離は **44.7mm ではなく 20mm**。
当初の想定より近いので、干渉の危険が上がっている。

`arm_mount_link → arm_base_link` は恒等（取付の向きは仮定どおりだった）。

---

## ★ RViz のマゼンタ表示は当てにならない

`lekiwi_tbd`（マゼンタ）材質が付いているリンク:

```
arm_mount_link      ← ★ 実測済みなのにマゼンタのまま
laser_link          ← ★ 実測済みなのにマゼンタのまま
camera_mount_link       未実測・未使用
wrist_camera_mount_link 未実測
wrist_camera_link       未実測
```

**`arm_mount_link` と `laser_link` は実測が終わっているのにマーカーが残っている。**
RViz の色を「未確定の目印」として使う運用なので、**色を見て未確定だと判断しない**こと。
この表を見ること。

---

## 誤差収支（`map` → 手先、リーチの場合）

| 区間 | 寄与 |
| --- | --- |
| `map → odom` | **2〜5cm（支配項）** |
| `odom → base_footprint` | 静止中なら小 |
| `base_footprint → base_link` | ±0.8mm |
| `base_link → arm_mount_link` | 実測済み |
| アーム FK（関節較正） | 1〜2cm |

**現実的な合計は 3〜8cm。** ソルバの許容差 5mm とは 1 桁違う。

`/so101/reach_status` の `residual` は**ソルバの残差**であって物理精度ではない。

---

## 関連

| 内容 | 場所 |
| --- | --- |
| リーチの概要と実機検証項目 | [`docs/lekiwi_so101_reach.md`](lekiwi_so101_reach.md) |
| 手首カメラの実機手順（W-5 で取付を実測） | [`docs/wrist_camera.md`](wrist_camera.md) |
| 実機の現在の状態 | [`docs/hardware_agent.md`](hardware_agent.md) |
| 運用・インターフェース一覧 | [`docker/lekiwi_so101_bringup/README.md`](../docker/lekiwi_so101_bringup/README.md) |
