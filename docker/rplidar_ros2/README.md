# RPLIDAR A1M8 + ROS 2 Jazzy + Docker

RPLIDAR A1M8から `/scan` (`sensor_msgs/msg/LaserScan`) を取得し、
`/scan/points` (`sensor_msgs/msg/PointCloud2`) に変換してRViz 2で表示する構成です。
A1M8は平面を測る2D LiDARなので、生成される点群も高さ `z=0` の2D点群です。

## 前提

- Linuxホスト（X11またはXWaylandを利用できるデスクトップ環境）
- Docker EngineとDocker Compose v2（`docker compose` コマンド）
- RPLIDAR A1M8本体、付属USB-UART基板、十分な電力を供給できるUSBポート

以下のコマンドは、このREADMEがあるディレクトリで実行します。

```bash
cd docker/rplidar_ros2
```

## 1. USBデバイスを確認する

LiDARを接続する前後で次を実行します。

```bash
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
dmesg --follow
```

通常は `/dev/ttyUSB0` です。USB-UARTのIDも確認します。

```bash
udevadm info --attribute-walk --name=/dev/ttyUSB0 | grep -m1 -E 'idVendor|idProduct'
```

付属のCP210x基板が `10c4:ea60` なら、同梱ルールで安定した
`/dev/rplidar` シンボリックリンクを作れます。

```bash
sudo cp 99-rplidar.rules /etc/udev/rules.d/99-rplidar.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
# 反映されない場合はUSBを抜き差しする
ls -l /dev/rplidar
```

IDが異なる場合、確認した値に `99-rplidar.rules` の `idVendor` と
`idProduct` を合わせてからコピーしてください。ルールを入れない場合も
`/dev/ttyUSB0` のまま使用できます。

現在ユーザーを `dialout` グループへ追加します。追加後はログアウト・ログインが必要です。

```bash
sudo usermod -aG dialout "$USER"
```

## 2. 環境ファイルを作る

```bash
cp .env.example .env
sed -i "s/^DIALOUT_GID=.*/DIALOUT_GID=$(getent group dialout | cut -d: -f3)/" .env
```

udevルールを使う場合は `.env` を次のように変更します。

```dotenv
RPLIDAR_DEVICE=/dev/rplidar
```

複数のROS 2システムが同じLANにある場合は、衝突しない `ROS_DOMAIN_ID`
（0～232）に変更してください。

## 3. RViz用のX11アクセスを許可する

ホスト上で、ローカルのrootユーザー（コンテナ内ユーザー）だけを許可します。

```bash
xhost +si:localuser:root
```

Wayland環境でも、多くのディストリビューションではXWayland経由で動作します。
`echo "$DISPLAY"` が空なら、先にデスクトップセッション側でX11/XWaylandを
利用可能にする必要があります。SSH接続の場合はX11転送より、後述の
「RVizをホスト側で動かす」方法を推奨します。

## 4. イメージをビルドして起動する

```bash
docker compose build
docker compose up
```

初回ビルドではROS 2 Jazzy環境、公式SLAMTECドライバ、RViz 2を取得して
ビルドします。起動後、モーターが回り、RVizに緑色の点群が表示されます。
RVizのFixed Frameは `laser`、表示トピックは `/scan/points` に設定済みです。

停止は `Ctrl+C`、バックグラウンド起動と停止は次のとおりです。

```bash
docker compose up -d
docker compose logs -f
docker compose down
```

作業終了時にX11許可を取り消す場合は次を実行します。

```bash
xhost -si:localuser:root
```

## 5. データを確認する

別ターミナルからコンテナ内で確認できます。

```bash
docker compose exec rplidar ros2 node list
docker compose exec rplidar ros2 topic list
docker compose exec rplidar ros2 topic hz /scan
docker compose exec rplidar ros2 topic hz /scan/points
docker compose exec rplidar ros2 topic echo /scan --once
```

期待する主なトピックは次の2つです。

- `/scan`: ドライバが出す距離・角度の2Dスキャン
- `/scan/points`: 本構成の変換ノードが出すXYZ点群（`z=0`）

## RVizをホスト側で動かす／GUIなしで動かす

コンテナではドライバだけを起動できます。

```bash
START_RVIZ=false docker compose up
```

ホストにも同じROS 2ディストリビューションとRVizがある場合、
`ROS_DOMAIN_ID` をコンテナと合わせてホストで次を実行します。

```bash
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=0
rviz2
```

RVizでFixed Frameを `laser` にし、PointCloud2表示を追加してトピックを
`/scan/points`、Reliabilityを `Best Effort` にします。

## ポートや起動パラメータを一時的に変更する

別のデバイス名なら、`.env` を編集するかコマンド単位で上書きします。

```bash
RPLIDAR_DEVICE=/dev/ttyUSB1 docker compose up
```

A1M8の標準設定は115200 baud、`Standard` scan modeです。変更が必要なら
リポジトリルートの `ros2_ws/src/rplidar_bringup/launch/a1_points.launch.py` の
パラメータを編集し、
`docker compose build` をやり直します。

## トラブルシュート

### `No such file or directory: /dev/ttyUSB0`

USBを抜き差しして `ls -l /dev/ttyUSB*` を確認し、実際のデバイスを
`RPLIDAR_DEVICE` に設定します。コンテナ起動後に接続した場合は、Composeの
device mappingを作り直すため `docker compose down && docker compose up` が必要です。

### `Permission denied`

```bash
ls -ln /dev/ttyUSB0
getent group dialout
grep DIALOUT_GID .env
```

デバイスのグループIDと `.env` の `DIALOUT_GID` が一致することを確認します。
ホストユーザーのグループ追加後に再ログインしていない場合も反映されません。
切り分け目的に限り `sudo chmod 666 /dev/ttyUSB0` でも確認できますが、抜き差しで
元に戻り、権限も広すぎるため常用しないでください。

### `cannot bind to the specified serial port` / スキャン開始エラー

- 他のプロセスがポートを使用していないか `lsof /dev/ttyUSB0` で確認する
- UbuntuのModemManagerが掴んでいないか `systemctl status ModemManager` で確認する
- USBハブを外し、十分な電力のあるUSBポートへ直接接続する
- A1用の115200 baudになっていることを確認する
- モーターやケーブルを確認し、USBを抜き差ししてコンテナを再作成する

### RVizが開かない／QtまたはGLXエラー

```bash
echo "$DISPLAY"
ls -l /tmp/.X11-unix
xhost
```

`xhost +si:localuser:root` をデスクトップへログインしているユーザーの端末から
再実行してください。本構成はWayland対策として `QT_QPA_PLATFORM=xcb`、コンテナに
`/dev/dri` がない場合の対策として `LIBGL_ALWAYS_SOFTWARE=1` を設定しています。
設定変更後は `docker compose up` だけでは既存コンテナの環境変数が更新されないため、
次のようにコンテナを再作成します。

```bash
docker compose down
docker compose up --force-recreate
```

それでも表示できない場合は `.env` で `START_RVIZ=false` にしてドライバを起動し、
RVizをホスト側で動かします。

### 点群が見えない

`/scan` と `/scan/points` の周波数を上記コマンドで確認します。RVizでは
Fixed Frame=`laser`、Topic=`/scan/points`、Reliability=`Best Effort` を確認し、
TopDownOrthoビューでズームを調整します。LiDARの最小測距より近い物体や、反射しにくい
黒色・透明・鏡面の対象は欠測することがあります。

## ファイル構成

- `Dockerfile`: ROS 2 Jazzy、SLAMTECドライバ、RViz、変換ノードのビルド
- `compose.yaml`: USB、ホストネットワーク、X11をコンテナへ渡す設定
- `99-rplidar.rules`: 安定した `/dev/rplidar` 名とdialout権限（任意）
- `../../ros2_ws/src/rplidar_bringup`: A1ドライバ、LaserScan→PointCloud2、RVizの一括起動パッケージ

SLAMTEC公式パッケージ: https://github.com/Slamtec/sllidar_ros2
ROS 2 Jazzy Dockerガイド: https://docs.ros.org/en/jazzy/How-To-Guides/Run-2-nodes-in-single-or-separate-docker-containers.html
