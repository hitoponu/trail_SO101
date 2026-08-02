# 依頼（Mac → 実機）

- **更新**: 2026-08-02（3回目）
- **状態**: 実行待ち
- **安全区分**: 🟡（実機を起動します。人がアームを支える必要あり）

## 前回の報告への回答 — 根本原因が判明しました

**報告の数値が決定的でした。ありがとうございます。**

`/joint_states` が `Present × 2π/4096` と**完全一致**していました
（elbow_flex: `1847 × 2π/4096 = 2.8333` = 報告値そのもの）。
**2048 を引いていない**、つまり全関節が **+π rad** ずれていました。

### 原因: apt の driver と GitHub の main が別物

私は GitHub の main を読んで設計していましたが、
実際に入っているのは **apt の v0.2.2** で、パラメータの意味が違いました。

```
機能                  apt v0.2.2（実機）            GitHub main（私が読んでいた）
中心値の扱い          per-joint の offset           kStsMidpoint(2048) 固定
offset                必須。無いと 0                非推奨・無視される
PID の綴り            p_cofficient（e 抜け）        p_coefficient
joint_config_file     無い                          ある
homing_offset         無い                          ある（EEPROM へ書く）
range_min/max         無い                          ある（EEPROM へ書く）
```

**私が「上流のバグ」として直したものは、すべて v0.2.2 では正しい記述でした。**

- `offset` を削除した → **これが今回の原因**。無いと 0 になり π rad ずれる
- `p_cofficient` を「正しい綴り」に直した → v0.2.2 は読まず、**PID が一度も効いていなかった**
- `joint_config_file` を追加した → **v0.2.2 に無い。`so101_joints.yaml` は完全に無視されていた**

### 良い知らせ: EEPROM は一度も書き換わっていません

`homing_offset` / `range_*` は v0.2.2 に存在しないので、
**サーボの EEPROM には最初から一度も書き込まれていません。**
前回の「(c) 分からない」の答えは **(b) そもそも書かれていなかった** です。
較正値は lerobot が書いたまま無傷です。

## 修正内容

`offset` 方式（v0.2.2）へ全面的に書き直しました。
**EEPROM には一切書きません。純粋なソフト側の補正です。**

`config/so101_offsets.xacro` に機体の値を入れてあります。

```
関節            range        offset   Δ(=offset−2048)
shoulder_pan     695..3409     2052        +4
shoulder_lift    802..3154     1978       −70
elbow_flex       670..3051     1916      −132
wrist_flex      1014..3350     2182      +134
wrist_roll         0..4095     2048        +0    ★暫定（範囲未記録のため計算不可）
gripper         1961..3399     1961       −87    ★「閉」がどちら側か未確認
```

Dockerfile に **driver のバージョン検査**も入れました。
0.2.2 以外になったらビルドが止まり、xacro の更新が必要だと分かります。

## やってほしいこと

### 手順 1 🟢 更新して再ビルド

```bash
git pull
cd docker/so101_ros2
docker compose build
```

### 手順 2 🟡 実機で起動する（人がアームを支えること）

> 起動時に一瞬脱力します。**人が手を添えてから**。周囲 35cm を空けること。
> 事前にアームの電源を入れ直してください。

**まず起動前の `--scan` を取り、その姿勢のまま起動してください。**
比較したいので、起動前後で姿勢を変えないでください。

```bash
docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_probe --port /dev/so101_follower --scan

HARDWARE_TYPE=real docker compose up 2>&1 | tee /tmp/so101_real2.log
```

### 手順 3 🟢 観測する（指令は送らない）

```bash
docker compose exec so101-follower /entrypoint.sh ros2 control list_controllers
docker compose exec so101-follower /entrypoint.sh ros2 topic echo /joint_states --once --field name
docker compose exec so101-follower /entrypoint.sh ros2 topic echo /joint_states --once --field position
grep -E "ERROR|WARN|offset|out of bounds" /tmp/so101_real2.log
```

## 報告してほしいこと

1. 手順2の**起動前** `--scan` 出力（全部）
2. 手順3の出力すべて
3. **RViz と実物が一致しているか。**ずれている関節があればどれか、目測で何度か
4. `list_controllers` で **4つとも `active` / `inactive`（`unconfigured` でない）** か

## 期待する結果

`/joint_states` の各値が、起動前 `--scan` の **`q_ros` 列とほぼ一致**するはずです
（前回は `Present × 2π/4096` になっていました）。

一致すれば π rad のずれは解消です。`wrist_roll` と `gripper` は
まだ暫定値なので、そこだけずれる可能性があります。

### 手順 4 🟢 wrist_roll の可動域を測る（追加）

**`wrist_roll` だけ offset が暫定値（2048＝補正なし）です。**
lerobot がこの関節を「フルターンモータ」扱いして可動域を記録しない
（`Min=0, Max=4095` 固定）ため、他の5関節のように計算で求められません。

トルクを切って**手で**測ってください。

```bash
docker compose down
docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_probe --port /dev/so101_follower --torque-off --watch
```

1. `wrist_roll`（id 5）を**片方の端までゆっくり回し**、`Present` を記録
2. **反対の端まで回し**、`Present` を記録

> ⚠️ **抵抗を感じたら止めてください。無理に回さないこと。**
> 可動端が機械的なストッパーではなく **配線** である可能性があります。
> 力任せに回すとケーブルを切ります。

> ⚠️ **そもそも端が無く、ぐるぐる回り続ける可能性もあります。**
> その場合は「端が無い」と報告してください。別の方法に切り替えます。

## 報告してほしいこと（手順4ぶん）

5. `wrist_roll` の可動端2点の `Present` 値。
   **または「端が無く連続回転する」という事実**

   （中点の計算はこちらでやります。折り返しをまたぐ場合があるので、
   生の2値をそのまま書いてください）

## やらないでほしいこと

- **`send_goal` による関節の移動**（🔴）。今回も静止確認までです
- `wrist_roll` を**力任せに回すこと**
