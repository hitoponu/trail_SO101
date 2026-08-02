cmake_minimum_required(VERSION 3.8)
project(lekiwi_description)

find_package(ament_cmake REQUIRED)

# meshes/ は use_mesh:=true のときだけ参照されるが、同梱しているので常に install する。
# 出自と間引きについては meshes/README.md を参照。
install(DIRECTORY urdf meshes DESTINATION share/${PROJECT_NAME})

ament_package()
