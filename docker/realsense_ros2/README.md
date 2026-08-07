# RealSense D435i ROS2 Docker

Intel RealSense D435i をROS2 Jazzy + Dockerで動かすセットアップ。

## ホスト側の準備（Linux）

### udevルールの設定
```bash
sudo cp 99-realsense.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo usermod -aG plugdev $USER
```

### .envファイルの作成
```bash
cp .env.example .env
```

## 起動方法（Linux）

```bash
# ビルド
docker compose build

# 起動（RViz表示あり）
xhost +local:docker
docker compose up

# バックグラウンド起動（RVizなし）
START_RVIZ=false docker compose up -d
```

## macOS での注意事項

macOSのDocker Desktopは `/dev/bus/usb` の直接パススルーに対応していません。
以下のいずれかの方法を使用してください。

### 方法1: Limaを使う（推奨）
```bash
limactl start --set '.mounts[0].writable=true' default
```

### 方法2: colima + USB転送
```bash
colima start --vm-type vz
# USB/IPでRealSenseデバイスを転送
```

### 方法3: RVizのみmacOSで確認（カメラはLinux側）
macOSからはトピックをサブスクライブするだけでも確認可能。
`ROS_DOMAIN_ID` を合わせてネットワーク越しに受信する。

## 公開されるROSトピック

| トピック | 型 | 内容 |
|---|---|---|
| `/camera/camera/color/image_raw` | `sensor_msgs/Image` | RGBカラー画像 |
| `/camera/camera/depth/image_rect_raw` | `sensor_msgs/Image` | 深度画像 |
| `/camera/camera/color/camera_info` | `sensor_msgs/CameraInfo` | カメラ内部パラメータ |
| `/camera/camera/depth/camera_info` | `sensor_msgs/CameraInfo` | 深度カメラパラメータ |
| `/camera/camera/aligned_depth_to_color/image_raw` | `sensor_msgs/Image` | Color座標系に合わせた深度 |
