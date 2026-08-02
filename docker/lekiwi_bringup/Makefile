# LeKiwi Nav2 操作の窓口。
#
# 使い方:
#   make build          イメージをビルド
#   make slam           SLAM モードで起動 (地図を作りながらナビゲーション)
#   make nav            保存済み地図でナビゲーション
#   make shell          動いているコンテナにインタラクティブで入る
#   make save-map       現在の地図を保存 (SLAM 中に実行)
#   make save-map MAP_NAME=living_room  ファイル名を指定して保存
#   make down           全コンテナを停止・削除
#   make logs           lekiwi-nav のログをリアルタイムで表示

# .env が存在すれば読み込む
-include .env

MAP_NAME ?= my_room

# SLAM モードで起動するコンテナ名 (compose.nav.yaml の service 名から決まる)
NAV_CONTAINER := lekiwi-nav

# ------------------------------------------------------------------

.PHONY: build slam nav shell save-map down logs

build:
	docker compose -f compose.nav.yaml build

# SLAM + Nav2: 地図を作りながらナビゲーションできる状態で起動する。
# 地図を保存するには別ターミナルで make save-map を実行する。
slam:
	mkdir -p $${MAP_DIR:-$$HOME/maps}
	docker compose -f compose.nav.yaml up

# 保存済み地図を使ったナビゲーション。
# .env の MAP_NAME が読み込まれる (既定: my_room)。
nav:
	docker compose -f compose.nav_with_map.yaml up

# 動いている lekiwi-nav コンテナにインタラクティブで入る。
# "make slam" を別ターミナルで動かしてから実行すること。
shell:
	docker exec -it $(NAV_CONTAINER) bash

# SLAM で構築中の地図をファイルに保存する。
# slam が動いている状態で別ターミナルから実行する。
#   make save-map
#   make save-map MAP_NAME=living_room
save-map:
	docker exec $(NAV_CONTAINER) \
		ros2 run lekiwi_base_bringup save_map $(MAP_NAME)

# 全コンテナを停止・削除する。
down:
	docker compose -f compose.nav.yaml down 2>/dev/null || true
	docker compose -f compose.nav_with_map.yaml down 2>/dev/null || true

# lekiwi-nav のログをリアルタイム表示する。
logs:
	docker logs -f $(NAV_CONTAINER)
