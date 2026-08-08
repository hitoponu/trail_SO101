# 開発ガイド — 自分でノードを書く

kachaka のシミュレーションから来た人向けです。**書き方はほとんど同じ**ですが、
実機なので違うところがいくつかあります。

- 使い方の手順は [`../README.md`](../README.md)
- 名前と型の一覧は [`interfaces.md`](interfaces.md)
- 中で何が起きているかは [`internals.md`](internals.md)

**★ この文書のコマンドはすべてコンテナ内で実際に通しています。**

---

## 1. 新しいコードをどこに置くか

既存パッケージは 6 つあります。**まず「既にある場所に足せないか」を考えてください。**

| パッケージ | 役割 | ここに足すもの |
| --- | --- | --- |
| `so101_bringup` | アーム。LeRobot ブリッジ、リーチ、逆運動学 | アームの動かし方に関わるもの |
| `lekiwi_base_bringup` | ベース。ドライバ、オドメトリ、スキャン処理 | 走行に関わるもの |
| `lekiwi_so101_bringup` | **合成だけ**。結合 URDF、launch、`release_all` | 全体をまとめる launch や設定 |
| `lekiwi_description` | ベースの URDF | 機体の形 |
| `rplidar_bringup` | LiDAR の launch と点群変換 | LiDAR まわり |
| `realsense_bringup` | カメラの launch | カメラまわり |

**新しいパッケージを作るのは、次のどれかに当てはまるときです。**

- 既存のどれにも属さない**新しい機能**（例: 物体検出、タスク実行）
- 重い依存を足す（例: PyTorch、OpenCV の追加モジュール）
- 他のプロジェクトでも使い回したい

> ★ **`lekiwi_so101_bringup` にアルゴリズムを書かないこと。**
> あそこは「合成だけを持ち、アルゴリズムは持たない」という方針です
> （`package.xml` にそう書いてあります）。リーチのノード本体が
> `so101_bringup` にあるのはそのためです。

---

## 2. パッケージを作る

```bash
# コンテナ内 /ros2_ws/src/
ros2 pkg create --build-type ament_python --license Apache-2.0 \
  --node-name hello my_first_pkg
```

これで次ができます。

```
my_first_pkg/
├── package.xml            ← 依存を書く
├── setup.py               ← entry_points（実行体の登録）
├── setup.cfg
├── resource/my_first_pkg
├── my_first_pkg/
│   ├── __init__.py
│   └── hello.py           ← --node-name で作られる
└── test/                  ← ★ 既定で lint テストが 3 つ入る
```

ビルドして実行します。

```bash
# コンテナ内 /ros2_ws/
colcon build --symlink-install --packages-select my_first_pkg
source install/setup.bash
ros2 run my_first_pkg hello
```

```
Hi from my_first_pkg.
```

> ★ **`make bootstrap` を打ち直せば、`--packages-select` を書かなくても
> 自動でビルド対象に入ります。** `bootstrap.sh` は `--packages-ignore` 方式なので、
> `src/` に置いたものは全部ビルドされます。
>
> ★ **`ament_cmake` ではなく `ament_python` を使ってください。**
> このリポジトリの Python パッケージ（`so101_bringup` など）は全部そうです。

### `package.xml` に依存を書く

```xml
<depend>rclpy</depend>
<depend>sensor_msgs</depend>
<depend>geometry_msgs</depend>
<depend>tf2_ros</depend>
```

> ★ **`feetech-servo-sdk`（import 名 `scservo_sdk`）と `lerobot` には rosdep キーが
> ありません。** `package.xml` に書けないので、`docker/robot/Dockerfile` の
> `pip install` が唯一の導入経路です。新しい pip 依存が要るときは
> Dockerfile に足して `make build` してください。

---

## 3. ノードの書き方

### 最小構成

```python
#!/usr/bin/env python3
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node


class MyNode(Node):
    def __init__(self):
        super().__init__("my_node")
        self.get_logger().info("起動しました")


def main():
    rclpy.init()
    node = MyNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        # ★ ここを書かないと、Ctrl+C のたびにトレースバックと
        #   "process has died [exit code -2]" が launch のログに出ます。
        #   統合スタックは停止経路が Ctrl+C 一本なので、正常な停止でログが
        #   赤くなると本物の異常を見落とします。
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
```

> ★ **`finally` に後片付けを書く習慣をつけてください。** 実機を触るノードでは
> ここが「トルクを切る」「速度をゼロにする」場所になります
> （[`internals.md` の安全論理](internals.md#安全論理--アームとベースで向きが逆)）。

`setup.py` に登録します。

```python
entry_points={
    "console_scripts": [
        "my_node = my_first_pkg.my_node:main",
    ],
},
```

### トピックを受信する

```python
from sensor_msgs.msg import LaserScan
from rclpy.qos import qos_profile_sensor_data

self.create_subscription(
    LaserScan, "/scan_filtered", self._scan_cb, qos_profile_sensor_data
)
```

> ★ **センサ系は `qos_profile_sensor_data`（BEST_EFFORT）を使ってください。**
> 既定は RELIABLE で、publisher が BEST_EFFORT だと**1 通も届きません**。
> エラーも出ないので気付きにくい罠です。実際に `scan_filter` がこれを踏みました。
>
> 該当するもの: `/scan` `/scan_filtered` `/so101/hardware_states`、
> RealSense の点群と画像。

`/joint_states` は特別です。

```python
def _joint_state_cb(self, msg):
    # ★ publisher が 2 つ（車輪 3 関節 / アーム 6 関節）なので、
    #   1 通のメッセージには全関節が入っていません。蓄積が要ります。
    self._positions.update(dict(zip(msg.name, msg.position)))
```

`/robot_description` はさらに特別です。

```python
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy

latched = QoSProfile(
    depth=1,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,   # ★ これが無いと受信できません
    reliability=ReliabilityPolicy.RELIABLE,
)
self.create_subscription(String, "/robot_description", self._cb, latched)
```

### トピックを送信する

```python
from geometry_msgs.msg import PoseStamped

self._pub = self.create_publisher(PoseStamped, "/so101/reach_target", 10)

msg = PoseStamped()
msg.header.stamp = self.get_clock().now().to_msg()
msg.header.frame_id = "map"          # ★ リーチは map 以外を受け付けません
msg.pose.position.x = 0.35
msg.pose.orientation.w = 1.0
self._pub.publish(msg)
```

### パラメータを使う

**★ kachaka との最大の違いです。** kachaka はモジュール定数（`WAYPOINTS = [...]`）で
設定を持っていましたが、**実機では再ビルドせずに調整できることが重要**なので、
このリポジトリは ROS パラメータ + YAML を使います。

```python
self.declare_parameter("max_reach_radius", 0.55)
radius = float(self.get_parameter("max_reach_radius").value)
```

YAML に書いて launch から渡します。

```yaml
# config/my_node.yaml
my_node:
  ros__parameters:
    max_reach_radius: 0.55
```

```python
Node(package="my_first_pkg", executable="my_node",
     parameters=[str(share / "config" / "my_node.yaml")])
```

実行中に変えられます。

```bash
$E ros2 param set /my_node max_reach_radius 0.4
```

### アクションを呼ぶ

ナビもアームもアクションです。**購読コールバックの中で
`spin_until_future_complete` を呼ばないでください**（デッドロックします）。
`add_done_callback` + `MultiThreadedExecutor` + コールバックグループ分離が
このリポジトリの流儀です（`reach_to_point.py` を参照）。

```python
from rclpy.action import ActionClient
from nav2_msgs.action import NavigateToPose

self._client = ActionClient(self, NavigateToPose, "navigate_to_pose")
self._client.wait_for_server()
future = self._client.send_goal_async(goal)
future.add_done_callback(self._on_goal_response)
```

---

## 4. 編集したあと何をすればよいか

| 変えたもの | やること |
| --- | --- |
| Python のコード | **何もしなくていい。** launch を上げ直すだけ（`--symlink-install` のため） |
| YAML / launch / URDF | 同上 |
| **ファイルを追加した** | `colcon build --symlink-install --packages-select <pkg>` |
| **パッケージを追加した** | `make bootstrap`（自動で拾われます） |
| `package.xml` の依存 | `colcon build` |
| Dockerfile（apt / pip） | `make build` してから `make bootstrap` |

---

## 5. テストの書き方

**★ このリポジトリの強みです。136 件のテストが実機なしで走ります。**

コツは **ROS に依存しないロジックを別モジュールに切り出すこと**です。

| ROS 非依存（テストしやすい） | ROS ノード（テストしにくい） |
| --- | --- |
| `cartesian_math.py`（順運動学・ヤコビアン） | `cartesian_jog.py` |
| `reach_solver.py`（IK の収束） | `reach_to_point.py` |
| `bridge_core.py`（単位変換・検証） | `lerobot_bridge.py` |
| `kinematics.py`（オムニの逆運動学） | `base_driver.py` |

```python
# test/test_my_logic.py
from my_first_pkg.my_logic import compute_something


def test_返り値が範囲内に収まる():
    assert 0.0 <= compute_something(1.0) <= 1.0
```

```bash
# コンテナ内 /ros2_ws/src/
python3 -m pytest my_first_pkg -q
```

> ★ `colcon test` ではなく `python3 -m pytest` を使っています。
> `ros2 pkg create` が入れる lint テスト 3 つ（flake8 / pep257 / copyright）は
> このリポジトリでは使っていません。消して構いません。

**構造そのものをテストで固定する**という手も使っています。たとえば
「リーチノードは絶対にベースを動かさない」を、AST を走査して
`/cmd_vel` の publisher が作られていないことで保証しています
（`test_reach_node_contract.py`）。

---

## 6. よくあるつまずきポイント

**Q. `ros2: command not found` / `executable file not found in $PATH`**
A. `docker exec` は ENTRYPOINT を通りません。`/entrypoint.sh` を前置してください。
対話シェル（`docker compose exec -it robot bash`）なら不要です。

**Q. `Package 'lekiwi_so101_bringup' not found`**
A. `make bootstrap` を打っていません。`ros2_ws/install` は `.gitignore` 済みで
`git pull` では降ってきません。

**Q. ビルドしたのに変更が反映されない**
A. `source install/setup.bash` を打ち直してください。`--symlink-install` 付きなら
Python ファイルの**編集**は再ビルド不要ですが、**追加**したときは要ります。

**Q. トピックは出ているのに `ros2 topic echo` に何も出ない**
A. QoS の不一致です。publisher が BEST_EFFORT なら購読側も
`qos_profile_sensor_data` にしてください。`ros2 topic echo` なら
`--qos-reliability best_effort` を付けます。

**Q. `ros2 topic list` に一部しか出ない**
A. DDS の discovery 待ちです。30 秒ほど待つか `make check` を使ってください
（`make check` は publisher 数が揃うまで最大 60 秒待ちます）。

**Q. RViz に見覚えのないロボットが出る / TF が混ざる**
A. `ROS_DOMAIN_ID` の衝突です。`docker/` 以下は全部 `network_mode: host` なので、
別スタックのコンテナや同じ LAN の別マシンと混信します。
`docker ps --format '{{.Names}}'` で他に動いていないか確認してください
（`make up` / `make mock` の guard も検出します）。

**Q. `/scan_filtered` に何も来ない / 地図ができない**
A. `scan_filter` が起動していません。`/scan_filtered` が publisher 0 /
subscriber 4 になっているはずです。Nav2 は `Invalid frame ID map` を
**INFO で**吐き続けるのでエラーに見えません。

**Q. `ros2 topic pub --once` したのに届かない**
A. discovery が終わる前に publisher が終了しています。`-w 1`（購読者を待つ）か、
`-r 10 --times 20`（2 秒流す）を使ってください。`base_driver` の watchdog は
0.5 秒なので、`/cmd_vel` は 1 通だけだとすぐ止まります。

**Q. ブランチを切り替えたら colcon build が `can't copy '...': doesn't exist` で落ちる**
A. `--symlink-install` の壊れたリンクが `build/` に残っています。
`make bootstrap` が検出して作り直します。

**Q. リーチが `REJECTED_WRONG_FRAME` になる**
A. RViz の **Fixed Frame を `map`** にしてください。"Publish Point" は
Fixed Frame の座標で publish します。

**Q. アームが動かない（`joint_trajectory_controller` が `unconfigured`）**
A. 実機の現在姿勢が URDF の可動域の外にあります。手で範囲内へ戻してください。
実機で実際に起きています（`docs/agent/report.md`）。

---

## 7. 参考リンク

- [ROS 2 Jazzy 公式チュートリアル](https://docs.ros.org/en/jazzy/Tutorials.html)
- [Nav2 ドキュメント](https://docs.nav2.org/)
- [ros2_control ドキュメント](https://control.ros.org/jazzy/index.html)
- [LeRobot](https://github.com/huggingface/lerobot)
