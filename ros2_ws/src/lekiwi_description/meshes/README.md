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

quadric decimation で 20,000 面へ落とした。形状が保たれていることは
元メッシュとの幾何比較で確認済み。

| | faces | bbox [mm] | 体積 | 表面積 |
| --- | --- | --- | --- | --- |
| 元 | 314,244 | 101.569 × 101.569 × 38.828 | 172.2 cm³ | 1004.2 cm² |
| 間引き後 | 20,000 | 101.673 × 101.851 × 39.113 | 170.1 cm³ | 999.7 cm² |

差は bbox が最大 **0.284 mm**（車輪径 101.6mm に対し 0.28%）、体積 −1.25%、
表面積 −0.44%、最大半径 +0.265 mm。表示用途では問題にならない。

なお元メッシュの時点で `is_watertight == False`（CAD エクスポートによくある
非多様体エッジ）で、間引きで悪化はしていない。表示には無関係だが、
物理シミュレーションに使うなら修復が要る。

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
