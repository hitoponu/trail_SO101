# メッシュの出自

`xacro lekiwi_base.urdf.xacro use_mesh:=true` で使う STL。
出典は [SIGRobotics-UIUC/LeKiwi](https://github.com/SIGRobotics-UIUC/LeKiwi) の
`URDF/meshes/`（単位はミリメートル。xacro 側で `scale="0.001 0.001 0.001"` を掛けている）。

| ファイル | 出典 | 加工 |
| --- | --- | --- |
| `base_plate_layer1-v5.stl` | 同名ファイル | なし（290KB） |
| `omni_wheel.stl` | `4-Omni-Directional-Wheel_Single_Body-v1.stl` | **31万面 → 2万面に間引き**（15.7MB → 1.0MB） |

## なぜ車輪を間引いたか

元の STL は **1個あたり 314,244 面**で、3輪ぶんで約 94 万面になる。
これをそのまま RViz に読ませると、ソフトウェアレンダリング環境では
**`rviz2` がセグメンテーションフォルトで落ちる**（実測）。
15.7MB × 3 を git に入れる問題もある。

quadric decimation で 20,000 面へ落とした。見た目のローラー形状は保たれており、
表示用途では元と区別がつかない。

再生成するなら:

```python
import trimesh
m = trimesh.load("4-Omni-Directional-Wheel_Single_Body-v1.stl", force="mesh")
m.simplify_quadric_decimation(face_count=20000).export("omni_wheel.stl")
```

## 衝突形状には使わない

`use_mesh:=true` でもコリジョンは円柱・箱のプリミティブのままにしてある
（`lekiwi_base.macro.xacro` を参照）。間引いた後でも衝突判定にメッシュを
使う理由はなく、プリミティブのほうが速く安定する。
