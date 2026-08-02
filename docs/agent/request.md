# 依頼（Mac → 実機）

- **更新**: 2026-08-02（2回目）
- **状態**: 実行待ち
- **安全区分**: 🟢 → 🟡（後半で実機を起動します。人がアームを支える必要あり）

## 前回の報告への回答

**ありがとうございます。報告が明快で、2点が確定しました。**

### 1. ファームは Present をラップする【確定】

`wrist_flex` の `Present=1019..3362` を逆算すると `Actual` は
**3031 → 4095 → 0 → 1278** と折り返しをまたいでいます。
それでも Present が連続だったので、`Present = (Actual − homing) mod 4096` と確定しました。
ラップしなければ `Actual=0` で `Present=−2012` へ飛んだはずです。

**したがって `homing` の 4096 折り返しは安全です。**
私が「未検証だから危険」としてオプトインに退避させたのは過剰でした。

### 2. 「不可能な姿勢」の原因は折り返しではなかった

**初回スキャンの時点で（＝設定を変える前から）2関節が URDF limit を超えていました。**

| 関節 | q_ros | URDF limit | 超過 |
| --- | --- | --- | --- |
| `wrist_roll` | +2.9544 | ±2.3 | 0.65 rad (37°) |
| `gripper` | +2.0970 | 0.0〜1.70 | 0.40 rad (23°) |

`gripper` は既知の規約差（URDF のゼロ＝閉、lerobot のゼロ＝可動域中間）で、
Δ 補正で直ります。
`wrist_roll` は `--from-ranges` で補正できない唯一の関節で、**未解決のまま**です。

## 確認したいこと

現在 EEPROM は**初期値に戻っています**（`--scan` の homing が
−1711 / −1078 / 1731 / 2012 / 406 / 1441）。

**これは誰が戻しましたか？** 次のどれか教えてください。

- (a) 人間が復旧用 YAML を適用した
- (b) ドライバが新しい値を書く前にクラッシュしていた（＝そもそも書かれていなかった）
- (c) 分からない

原因の切り分けに必要です。**分からなければ (c) で構いません。**

## やってほしいこと

### 手順 1 🟢 アームを「全関節が limit 内」の姿勢にする

トルクを切り、**手で**次の状態に近づけてください。指令は送りません。

```bash
cd docker/so101_ros2
docker compose down
docker compose run --rm so101-follower \
  ros2 run so101_bringup so101_probe --port /dev/so101_follower --torque-off --watch
```

`q_ros` を見ながら、**6関節すべてを下表の範囲に入れてください**。
できれば 0 に近づけてください（アームは低く畳んだ姿勢にする）。

| id | 関節 | 入れたい範囲 [rad] |
| --- | --- | --- |
| 1 | shoulder_pan | −1.9 〜 +1.9 |
| 2 | shoulder_lift | −1.7 〜 +1.7 |
| 3 | elbow_flex | −1.6 〜 +1.5 |
| 4 | wrist_flex | −1.5 〜 +1.5 |
| 5 | **wrist_roll** | **−2.2 〜 +2.2** ← 前回 +2.95 で超過していた |
| 6 | **gripper** | **+0.1 〜 +1.6** ← 前回 +2.10 で超過していた |

**この状態の `--scan` 出力を記録してください。** 6関節すべてが範囲内であることを確認。

### 手順 2 🟡 実機で起動する（人がアームを支えること）

> 起動時に一瞬脱力します。**人が手を添えてから**実行してください。
> 周囲 35cm を空け、電源スイッチに手が届く位置に。

```bash
HARDWARE_TYPE=real docker compose up 2>&1 | tee /tmp/so101_real.log
```

### 手順 3 🟢 状態を観測する（指令は送らない）

```bash
docker compose exec so101-follower /entrypoint.sh ros2 control list_hardware_components
docker compose exec so101-follower /entrypoint.sh ros2 control list_controllers
docker compose exec so101-follower /entrypoint.sh ros2 topic echo /joint_states --once --field name
docker compose exec so101-follower /entrypoint.sh ros2 topic echo /joint_states --once --field position
docker compose exec so101-follower /entrypoint.sh ros2 topic hz /joint_states
```

## 報告してほしいこと

1. 上の「誰が戻したか」への回答（(a)/(b)/(c)）
2. 手順1の `--scan` 出力（全関節が limit 内になった状態）
3. 手順3の出力すべて
4. **`/tmp/so101_real.log` のうち `ERROR` と `WARN` を含む行すべて**
   ```bash
   grep -E "ERROR|WARN|out of limits" /tmp/so101_real.log
   ```
5. **RViz の見た目**：実物と一致しているか。ずれている関節があればどれか
   （RViz が開かない環境なら「開かない」と書いてください。それで構いません）

## やらないでほしいこと

- **`send_goal` による関節の移動**（🔴）。今回は静止確認までです
- **EEPROM の書き換え**（`so101_joints.yaml` の更新とビルド）

## 意図

「全関節が limit 内」という条件を満たした状態で起動すれば、
RViz が正常になり、`enforce_command_limits` のエラーも消えるはずです。
**そうならなければ、私の仮説（limit 超過が原因）が誤り**なので、
ログから別の原因を探します。
