# LeKiwi + SO-101 統合構成 (1 イメージ 1 コンテナ) の操作窓口。
#
# 使い方:
#   make build       イメージをビルド
#   make bootstrap   ★ 初回とパッケージ追加時。上流取得 + colcon build + 静的検査
#   make up          コンテナを起動する (bash が上がるだけ。まだ何も動かない)
#   make run         ★ 実機で launch を起動する (前面。Ctrl+C で止める)
#   make mock        実機に触れないモック構成で起動 (Mac 可)
#   make shell       コンテナに入る
#   make stow        アームを低く畳む (★ 停止前に必ず実行する)
#   make save-map    現在の地図を保存
#   make check       ROS グラフの不変条件を確認
#   make release-check ★ トルクが入っているかを読むだけ (何も書かない)
#   make release     ★ 異常終了後にホイールとアームを解放する
#   make down        コンテナを停止・削除
#
# ■ 停止
#   通常  : make run の端末で Ctrl+C。その前に make stow
#   非常時: **物理スイッチを切る。** docker kill は使わない
#           (SIGKILL では停止処理が走らず、ホイールは最後の指令速度で回り続ける)
#   異常終了からの復帰: make down してから make release

-include .env

MAP_NAME   ?= my_room
SVC        := robot
SVC_MOCK   := robot-mock
E          := /entrypoint.sh
BACKEND    ?= lerobot
ROBOT_ID   ?= my_follower
START_RVIZ ?= true
MOCK_START_RVIZ ?= false

# ★ `-include .env` は make 変数を作るだけで、レシピのシェルへは export されない。
#   レシピ内で `$$LEKIWI_DEVICE` と書いても**必ず空**になる (以前これで
#   .env の設定が黙って無視されていた)。make 変数として `?=` で既定値を与え、
#   `$(...)` で参照すること。
#   compose.yaml 側の `${LEKIWI_DEVICE:-...}` は docker compose が .env を
#   自分で読むので別経路。
LEKIWI_DEVICE  ?= /dev/lekiwi
SO101_DEVICE   ?= /dev/so101_follower
RPLIDAR_DEVICE ?= /dev/rplidar
MAP_DIR        ?= $(HOME)/maps

# ★ 別スタックのコンテナが同じ ROS_DOMAIN_ID に居ると /robot_description が
#   二重に latch され、/tf も混信する (CLAUDE.md の「RViz に別のロボットが出る」)。
#   統合したのでスタック内には 1 コンテナしか無い。止めたいのは
#   **旧 4 コンテナ構成と単体デバッグ用スタックのコンテナ**。
LEGACY := so101-follower lekiwi-base lekiwi-nav lekiwi-nav-mock \
          lekiwi-so101-arm lekiwi-so101-arm-mock rplidar-a1 \
          realsense-d435i lekiwi-wrist-camera
CONFLICTS_FOR_REAL := $(LEGACY) $(SVC_MOCK)
CONFLICTS_FOR_MOCK := $(LEGACY) $(SVC)

.PHONY: build bootstrap up run mock shell stow save-map check release \
        release-wheels release-check down logs guard guard-mock

build:
	docker compose -f compose.yaml build

# ★ ros2_ws をホストからマウントする方式なので、イメージをビルドしただけでは
#   install/ が空で launch できない。初回と、パッケージを追加したときに実行する。
#   成果物はホストの ros2_ws/build・install に残る。
#   --no-deps は不要 (サービスが 1 つしか無い)。デバイスを掴まない mock 側で走らせる。
bootstrap:
	docker compose -f compose.mock.yaml run --rm $(SVC_MOCK) bash /bootstrap.sh

# $(1) に渡した名前のコンテナが動いていたら止めさせる。
define guard_against
	@for name in $(1); do \
	  cids=$$(docker ps -aq -f name=^$$name$$) || { echo "ERROR: Docker状態を確認できない。" >&2; exit 1; }; \
	  for cid in $$cids; do \
	    state=$$(docker inspect -f '{{.State.Status}}' $$cid) || { echo "ERROR: $$name の状態を確認できない。" >&2; exit 1; }; \
	    case "$$state" in \
	      exited|dead|'') ;; \
	      *) \
	        echo "ERROR: $$name が $$state 状態。ROS_DOMAIN_ID が衝突して" >&2; \
	        echo "       /robot_description が二重に latch され、/tf も混信する。" >&2; \
	        echo "       先に停止すること: docker stop $$name" >&2; \
	        exit 1; \
	        ;; \
	    esac; \
	  done; \
	done
endef

guard:
	$(call guard_against,$(CONFLICTS_FOR_REAL))

guard-mock:
	$(call guard_against,$(CONFLICTS_FOR_MOCK))

up: guard
	@test -f .env || { echo "ERROR: .env が無い。cp .env.example .env して編集すること" >&2; exit 1; }
	mkdir -p $(MAP_DIR)
	docker compose -f compose.yaml up -d

# ★ 前面で走らせること。Ctrl+C が launch に届いてはじめて停止処理
#   (アームのトルク OFF + ホイールの速度ゼロ) が走る。
#   docker compose down では届かない。
run: up
	docker compose -f compose.yaml exec -it $(SVC) $(E) \
		ros2 launch lekiwi_so101_bringup robot.launch.py \
		backend:=$(BACKEND) robot_id:=$(ROBOT_ID) start_rviz:=$(START_RVIZ) \
		lekiwi_port:=$(LEKIWI_DEVICE) \
		usb_port:=$(SO101_DEVICE) \
		lidar_port:=$(RPLIDAR_DEVICE)

mock: guard-mock
	docker compose -f compose.mock.yaml up -d
	docker compose -f compose.mock.yaml exec -it $(SVC_MOCK) $(E) \
		ros2 launch lekiwi_so101_bringup robot.launch.py \
		sim:=true backend:=mock start_rviz:=$(MOCK_START_RVIZ) \
		mock_wrist_camera_optical:=true

shell:
	docker compose -f compose.yaml exec -it $(SVC) bash

# ★ アームを低く畳む。launch を止める前に必ず実行すること
#   (正常終了でトルクが切れてアームが落ちるため)。
stow:
	docker compose -f compose.yaml exec $(SVC) $(E) \
		ros2 service call /so101/stow std_srvs/srv/Trigger "{}"

save-map:
	docker compose -f compose.yaml exec $(SVC) $(E) \
		ros2 run lekiwi_base_bringup save_map $(MAP_NAME)

# TF を 1 行表示する。$(1)=サービス, $(2)=親, $(3)=子, $(4)=出なかったときの助言。
#
# ★ `... | head -1 || echo fallback` は**絶対に発火しない**。パイプラインの
#   終了ステータスは head のもので、入力が空でも 0 になるため。その結果
#   「TF が無い」と「検査が空振りした」を区別できなかった。
#   変数に取ってから中身の有無で分岐する。
# ★ timeout は 15 秒。tf2_echo は discovery が終わるまで何も出さないので、
#   短いと TF はあるのに空になりうる。
define echo_tf
out=$$(docker exec $(1) $(E) timeout 15 ros2 run tf2_ros tf2_echo $(2) $(3) 2>/dev/null | grep -a Translation | head -1); if [ -n "$$out" ]; then echo "$$out"; else echo "  ★ $(2) -> $(3) が引けない ($(4))"; fi
endef

# ROS グラフの不変条件。モックでも実機でも同じ結果になること。
#   robot_description の publisher が 1 でなければ RViz に別のロボットが出る。
#   joint_states の publisher は 2 (ベースの車輪 3 関節 + アームの 6 関節)。
#
# ★ 起動直後は DDS の discovery が終わっておらず、publisher 数が実際より
#   少なく出る。数が合うまで最大 60 秒待ってから表示する。
check:
	@C=$$(docker ps -q -f name=^$(SVC)$$ -f name=^$(SVC_MOCK)$$ | head -1); \
	test -n "$$C" || { echo "コンテナが動いていない" >&2; exit 1; }; \
	echo "discovery を待っています..."; \
	for i in $$(seq 1 30); do \
	  n=$$(docker exec $$C $(E) ros2 topic info /joint_states 2>/dev/null \
	       | sed -n 's/.*Publisher count: //p'); \
	  [ "$$n" = "2" ] && break; sleep 2; \
	done; \
	echo "--- /robot_description (期待: 1) ---"; \
	docker exec $$C $(E) ros2 topic info /robot_description | grep 'Publisher count'; \
	echo "--- /joint_states (期待: 2) ---"; \
	docker exec $$C $(E) ros2 topic info /joint_states | grep 'Publisher count'; \
	echo "--- controllers (期待: active 3 つ) ---"; \
	docker exec $$C $(E) ros2 control list_controllers; \
	echo "--- ★ nav2 と ros2_control の action が同時に見えること ---"; \
	docker exec $$C $(E) ros2 action list | grep -E 'navigate_to_pose|follow_joint_trajectory' || \
	  echo "  ★ 片方しか見えない。分割時の症状が残っている"; \
	echo "--- map -> wrist_camera_depth_optical_frame ---"; \
	$(call echo_tf,$$C,map,wrist_camera_depth_optical_frame,realsense が未起動か camera_name 不一致); \
	echo "--- map -> arm_gripper_frame_link ---"; \
	$(call echo_tf,$$C,map,arm_gripper_frame_link,RSP かコントローラが未起動)

# ★★ robot コンテナが動いている間はシリアルバスを触らせない。
#
#   Feetech のバスは**半二重でマスタが 1 つしか居られない**。launch がポートを
#   開いたまま release_all が読み書きすると**パケットが混線し、ブリッジが通信異常と
#   判定してトルクを切る**（＝アームがその場で落ちる）。
#   「読むだけだから安全」は成り立たない。読むにも送信が要るため。
#
#   ★ 異常終了からの復帰では、そもそもコンテナは死んでいるのでここは通る。
#     ここで止まるのは「launch が生きているのに release を叩いた」ときだけで、
#     その場合の正解は make down（または launch を Ctrl+C）。
define guard_serial_bus
	@if [ -n "$$(docker ps -q -f name=^$(SVC)$$)" ]; then \
	  echo "ERROR: コンテナ $(SVC) が動いています。" >&2; \
	  echo "       Feetech のバスはマスタが 1 つだけ。launch が開いたまま" >&2; \
	  echo "       触ると混線し、ブリッジが通信異常と判定してトルクを切ります" >&2; \
	  echo "       （★ アームがその場で落ちます）。" >&2; \
	  echo "       先に launch を Ctrl+C するか make down してから実行すること。" >&2; \
	  exit 1; \
	fi
endef

# ★ 異常終了 (SIGKILL / OOM / コンテナ強制削除) からの復帰。
#   ホイールを止めてアームのトルクを切る。ROS は使わない。
#   ★ アームは支えが無ければ落ちる。人が支えてから実行すること。
release:
	$(call guard_serial_bus)
	docker compose -f compose.yaml run --rm $(SVC) $(E) \
		ros2 run lekiwi_so101_bringup release_all

# ホイールだけ止める (アームは落ちない)。走り出したときの一次対応。
release-wheels:
	$(call guard_serial_bus)
	docker compose -f compose.yaml run --rm $(SVC) $(E) \
		ros2 run lekiwi_so101_bringup release_all --only wheels --yes

# ★ 読むだけ。何も書き込まないので**それ自体では**アームは落ちない。
#   ただし launch 稼働中は上の guard で止める（混線でブリッジが落とすため）。
#   「いまトルクが入っているのか」の確認。release の前後で比べる。
#   ★ exit 1 は「トルクが入っている / 読めない」の意味で、異常とは限らない。
#     make は `Error 1` と表示するが、解放前に叩けばそれが期待どおり。
release-check:
	$(call guard_serial_bus)
	docker compose -f compose.yaml run --rm $(SVC) $(E) \
		ros2 run lekiwi_so101_bringup release_all --dry-run

down:
	docker compose -f compose.yaml down
	docker compose -f compose.mock.yaml down

logs:
	docker compose -f compose.yaml logs -f
