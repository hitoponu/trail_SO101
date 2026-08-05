# 依頼（Mac → 実機）

- **更新**: 2026-08-02（5回目）
- **状態**: 実行待ち
- **安全区分**: 🟡（実機を起動します。人がアームを支える必要あり）

## 前回の報告への回答

**仮説が確認できました。**

```
 id      P    D    I  MaxTorque  TorqueLim  ProtCurrent  Overload
  1     16   32    0       1000       1000          500        80
  ...
  6     16   32    0        500        500          250        25
```

- **全関節が `P=16`** … STS3215 の工場出荷値 32 の半分。lerobot が振動回避で下げた値
- **id 1–5 はトルク上限が満載（1000）** … 絞られてはいない
- **弱いのは全関節** … グリッパだけではないので `MaxTorque=500` は主因ではない
- **操作は `rqt_joint_trajectory_controller` のスライダ** … まさに「偏差が小さい」場面

位置制御のトルクは概ね `P × 位置偏差` です。スライダ操作は指令が実位置に
張り付くので偏差がほぼゼロになり、`P` が小さいと力が出ません。
`send_goal` は時間軸のある軌道で指令が先行するので偏差が持続し、力が出ます。

`wrist_roll = 2116` の測定もありがとうございます。リポジトリに反映しました。

## 修正内容

### 1. P ゲインを工場出荷値へ戻した

`control/so101_follower.ros2_control.xacro` の冒頭に切り出しました。

```xml
<xacro:property name="so101_p_gain" value="32"/>   <!-- 16 → 32 -->
<xacro:property name="so101_i_gain" value="0"/>
<xacro:property name="so101_d_gain" value="32"/>
```

### 2. 再ビルド不要の開発オーバーレイを追加した

**設定を変えるたびに `docker compose build` する必要はもうありません。**

```bash
docker compose -f compose.yaml -f compose.dev.yaml up
```

イメージは `--symlink-install` でビルドしてあり、
`install → build → src` が全部 symlink で繋がっています。
`compose.dev.yaml` がホストの `ros2_ws/src/so101_bringup` をマウントするので、
**編集して再起動するだけで反映されます**（Mac で検証済み）。

新規ファイル追加や `setup.py` の変更だけは従来どおり再ビルドが必要です。

### 3. `so101_probe --set-pid` を追加した

ROS を止めた状態で EEPROM へ直接 PID を書けます。値を探す実験用です。

## やってほしいこと

### 手順 1 🟢 更新

```bash
git pull
cd docker/so101_ros2
docker compose build     # setup.py が変わったので今回は必要
```

### 手順 2 🟡 P=32 で起動して確かめる（人がアームを支えること）

> 起動時に一瞬脱力します。**人が手を添えてから**。周囲 35cm を空けること。
> 事前にアームの電源を入れ直してください。

```bash
HARDWARE_TYPE=real docker compose -f compose.yaml -f compose.dev.yaml up 2>&1 \
  | tee /tmp/so101_p32.log
```

`--torque` で `P=32` になっていることを確認してください。

```bash
docker compose exec so101-follower /entrypoint.sh \
  ros2 control list_controllers
```

### 手順 3 🔴 保持力を確かめる（**人がその場にいること**）

`rqt_joint_trajectory_controller` で前回と同じ操作をして、
**力が改善したかを体感で比べてください。**

```bash
docker compose exec -it so101-follower /entrypoint.sh \
  ros2 run rqt_joint_trajectory_controller rqt_joint_trajectory_controller
```

**同時に、振動していないかを必ず見てください。** lerobot が P を下げた理由が
「shakiness（振動）回避」なので、32 で振動が出る可能性があります。

観察するポイント:

- 静止時に**唸り・小刻みな震え**が出ていないか
- 目標位置に着いたあと**行き過ぎて戻る**（オーバーシュート）動きが無いか
- サーボが**熱くならないか**（`--torque` の温度列でも見られます）

### 手順 4 🟢 振動する場合は下げて試す

振動が出たら、ROS を止めて直接書き換えて試せます。

```bash
docker compose down
docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_probe --port /dev/so101_follower --set-pid 24
```

24 → 20 → 18 と下げ、**「力が足りて、かつ振動しない」上限**を探してください。

見つけた値は `control/so101_follower.ros2_control.xacro` の
`so101_p_gain` に書けば、次回以降その値で起動します
（`compose.dev.yaml` を使えば再ビルド不要）。

## 報告してほしいこと

1. `P=32` での**保持力の体感**（前回と比べて改善したか）
2. **振動が出たか**。出たなら、どの関節で、どんな出方か
3. 振動して下げた場合、**最終的に決めた P の値**
4. 手順2の `--torque` 出力（`P=32` が反映されているかの確認）

## 電圧の測定について（前回の質問への回答）

**動作中の電圧は、ソフトからは測りにくいです。**
`so101_probe` はシリアルポートを占有するので、ros2_control が動いている間は
使えません（同じポートを二重に開けない）。

現実的な方法は2つです。

- **テスターを電源コネクタに当てる**（一番確実。負荷を掛けた瞬間の降下が見える）
- **P=32 の結果で判断する**。これで十分な力が出れば電圧は主因ではなかったことになる

**まずは手順3の体感を優先してください。** 電圧の切り分けは、
P を上げても足りない場合に初めて必要になります。

その場合の対策は電源を 7.4V 側へ上げることですが、
**8.0V を超えるとサーボが壊れます**。ハードウェアの変更なので人間の判断が要ります。

## やらないでほしいこと

- **`send_goal` で大きく動かすこと**。今回は保持力の確認が目的です
- P を **32 より上げること**。振動が悪化します
