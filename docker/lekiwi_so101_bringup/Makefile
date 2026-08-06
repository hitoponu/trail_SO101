# LeKiwi + SO-101 リーチ構成の操作窓口。
#
# 使い方:
#   make build       イメージをビルド
#   make bootstrap   ★ 初回とパッケージ追加時。上流取得 + colcon build + 静的検査
#   make mock        実機に触れないモック構成で起動 (Mac 可)
#   make reach       実機で起動 (要 .env、要 udev ルール)
#   make shell       アームのコンテナに入る
#   make stow        アームを低く畳む (★ 停止前に必ず実行する)
#   make save-map    現在の地図を保存
#   make check       ROS グラフの不変条件を確認
#   make down        全コンテナを停止・削除
#   make logs        アームのログを表示
#
# ★ 停止手順は make stow -> make down の順。
#   正常終了でトルクが切れてアームが落ちるため。

-include .env

MAP_NAME ?= my_room
ARM      := lekiwi-so101-arm
ARM_MOCK := lekiwi-so101-arm-mock
E        := /entrypoint.sh

# ★ 他のスタックが同じドメインに居ると /robot_description と /tf が混信する。
#   このスタックのコンテナが同じドメインを共有するのは意図どおりで、
#   防ぎたいのは「別のスタック」が入ってくること。
#   守りたいのは /robot_description の二重 latch と /tf の混信。
#   いちばん有力な二重 publisher は「モック構成のアームコンテナ」なので
#   必ず入れること (以前これが抜けていた)。
#   rplidar-a1 はこのスタック自身が使うので対象外。
CONFLICTS_FOR_REACH := so101-follower lekiwi-base lekiwi-nav-mock lekiwi-so101-arm-mock
CONFLICTS_FOR_MOCK  := so101-follower lekiwi-base lekiwi-nav lekiwi-so101-arm

.PHONY: build bootstrap mock reach shell stow save-map check down logs guard guard-mock

# ★ アーム側は ros2_ws をホストからマウントする方式なので、
#   イメージをビルドしただけでは install/ が空で launch できない。
#   初回と、パッケージを追加したときに実行すること。
#   成果物はホストの ros2_ws/build・install に残る。
bootstrap:
	docker compose -f compose.mock.yaml run --rm --no-deps \
		lekiwi-so101-arm-mock bash /bootstrap.sh

# $(1) に渡した名前のコンテナが動いていたら止める。
define guard_against
	@for name in $(1); do \
	  if [ -n "$$$$(docker ps -q -f name=^$$$$name$$$$)" ]; then \
	    echo "ERROR: $$$$name が起動中。ROS_DOMAIN_ID が衝突して" >&2; \
	    echo "       /robot_description が二重に latch され、/tf も混信する。" >&2; \
	    echo "       先に停止すること: docker stop $$$$name" >&2; \
	    exit 1; \
	  fi; \
	done
endef

guard:
	$(call guard_against,$(CONFLICTS_FOR_REACH))

guard-mock:
	$(call guard_against,$(CONFLICTS_FOR_MOCK))

build:
	docker compose -f compose.yaml build

mock: guard-mock
	docker compose -f compose.mock.yaml up

reach: guard
	@test -f .env || { echo "ERROR: .env が無い。cp .env.example .env して編集すること" >&2; exit 1; }
	mkdir -p $${MAP_DIR:-$$HOME/maps}
	docker compose -f compose.yaml up

shell:
	docker exec -it $(ARM) bash

# ★ アームを低く畳む。コンテナを止める前に必ず実行すること。
stow:
	docker exec $(ARM) $(E) \
		ros2 service call /so101/stow std_srvs/srv/Trigger "{}"

save-map:
	docker exec lekiwi-nav $(E) \
		ros2 run lekiwi_base_bringup save_map $(MAP_NAME)

# ROS グラフの不変条件。モックでも実機でも同じ結果になること。
#   robot_description の publisher が 1 でなければ RViz に別のロボットが出る。
#   joint_states の publisher は 2 (ベースの車輪 3 関節 + アームの 6 関節)。
#
# ★ 起動直後は DDS の discovery が終わっておらず、publisher 数が実際より
#   少なく出る (0 や 1 になる)。ノードの不具合ではないので、
#   数が合うまで最大 60 秒待ってから表示する。
check:
	@C=$$(docker ps -q -f name=^$(ARM)$$ -f name=^$(ARM_MOCK)$$ | head -1); \
	test -n "$$C" || { echo "アームのコンテナが動いていない" >&2; exit 1; }; \
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
	echo "--- map -> arm_gripper_frame_link ---"; \
	docker exec $$C $(E) timeout 5 \
	  ros2 run tf2_ros tf2_echo map arm_gripper_frame_link 2>/dev/null \
	  | grep -a Translation | head -1 || echo "  (TF 未確立)"

down:
	docker compose -f compose.yaml down 2>/dev/null || true
	docker compose -f compose.mock.yaml down 2>/dev/null || true

logs:
	docker logs -f $(ARM)
