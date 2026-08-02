# 依頼（Mac → 実機）

- **更新**: 2026-08-02（4回目）
- **状態**: 実行待ち
- **安全区分**: 🟢 読み取りのみ

## 前回の報告への回答

**offset 修正は完全に効いています。** 検算しました。

```
関節               (Present-offset)*k  /joint_states    差[deg]
shoulder_pan                 0.1764         0.1764      0.00
shoulder_lift                0.3083         0.3053      0.18
elbow_flex                  -0.0307        -0.0322      0.09
wrist_flex                   0.0430         0.0414      0.09
wrist_roll                   1.8239         1.8208      0.18
gripper                      0.4847         0.4832      0.09
```

全関節一致、`ERROR` も消え、`joint_trajectory_controller` と `gripper_controller` が
`active` になりました。π rad のずれは解消です。

`wrist_roll` の調整完了もありがとうございます。
**`config/so101_offsets.xacro` の値を教えてください**（リポジトリに反映します）。

## 今回の課題: 対話型でモータの力が弱い

`send_goal` では問題ないが対話操作で弱い、という報告について、
原因の候補が2つあります。**どちらがどれだけ効いているかを実測で切り分けたい**です。

### 候補1: P ゲインが既定の半分

lerobot が SO-101 に対して意図的に下げています。

```python
# lerobot/robots/so_follower/so_follower.py
# Set P_Coefficient to lower value to avoid shakiness (Default is 32)
self.bus.write("P_Coefficient", motor, 16)
```

私はこれをそのまま `so101_follower.ros2_control.xacro` に写しました（`p_cofficient: 16`）。
**STS3215 の既定は 32 なので半分です。**

位置制御のトルクは概ね `P × 位置偏差` です。

- `send_goal` … 時間軸のある軌道なので指令が実位置を先行し、**偏差が持続する** → 力が出る
- 対話操作 … 指令が実位置に張り付くので **偏差がほぼゼロ** → 力が出ない

**これが「対話型でだけ弱い」の説明になります。**

### 候補2: 電源電圧が定格より低い

実測 **4.8〜4.9V**。このアームのサーボは 7.4V 版（許容 4.0〜8.0V）です。

DC モータの拘束トルクは概ね電圧に比例するので、
**4.85 / 7.4 ≒ 66%**、つまり定格の約 2/3 しか出ていない計算になります。
7.4V にすれば約 **1.5 倍**です。

こちらは全体的な弱さで、モードによらず効きます。

### 候補3（グリッパのみ）: トルク上限が 50%

lerobot はグリッパだけ `Max_Torque_Limit=500`（最大 1000 の 50%）、
`Overload_Torque=25` を EEPROM に書きます。焼損防止です。
v0.2.2 はこのレジスタを触らないので、**lerobot が書いた値が残っています**。

## やってほしいこと

### 手順 1 🟢 更新

```bash
git pull
cd docker/so101_ros2
docker compose build
```

`so101_probe` に `--torque` を追加しました。トルク関連のレジスタを読みます。

### 手順 2 🟢 現在のトルク設定を読む

```bash
docker compose down
docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_probe --port /dev/so101_follower --torque
```

### 手順 3 🟢 電圧を確認する

```bash
docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_probe --port /dev/so101_follower --scan
```

`V` 列を見てください。**アームを動かしている最中**の電圧も知りたいので、
可能なら `--watch` で動かしながら見て、**最低値**を教えてください
（電圧降下が大きいなら電源容量の問題も疑えます）。

## 報告してほしいこと

1. `--torque` の出力（全部）
2. `--scan` の `V` 列。動作中の最低電圧も分かれば
3. **`wrist_roll` の最終的な offset 値**（`so101_offsets.xacro` に何を入れたか）
4. **「弱い」と感じた具体的な操作**。次のどれですか？
   - `rqt_joint_trajectory_controller` のスライダ操作
   - `forward_position_controller` を有効化しての操作
   - その他（具体的に）
5. **どの関節が特に弱いか**。全部か、特定の関節か
   （グリッパだけなら候補3、根元の関節なら候補2 の可能性が高い）

## 次にやること（報告を見てから）

**候補1 なら**: `so101_follower.ros2_control.xacro` の `p:=16` を 24〜32 に上げます。
xacro の1行なので試行は簡単です。ただし lerobot が下げた理由が
「shakiness（振動）回避」なので、**上げると振動する可能性があります**。
上げてから静止時に唸り・小刻みな振動が出ないか確認が要ります。

**候補2 なら**: 電源を 7.4V 側へ上げる検討です。**ただし 8.0V を超えないこと。**
これはハードウェアの変更なので、判断は人間にお願いします。

## やらないでほしいこと

- **`send_goal` による関節の移動**（🔴）
- **P ゲインを勝手に上げること**。振動するとアームが暴れます。報告を待ってください
