"""ROS 2 環境なしで pytest を回すための sys.path 設定。

``kinematics.py`` は numpy だけに依存し rclpy を import しないので、ROS 2 を
入れていないホスト (実機もコンテナも無い状態) で単体テストできる。これは
Phase D のキャリブレーション前に運動学だけを切り離して検証するための入口。

pytest が sys.path に足すのはテストファイルのあるディレクトリ (``test/``) だけ
なので、その 1 つ上 (パッケージルート) を明示的に足して
``import lekiwi_base_bringup.kinematics`` を通す。

``colcon test`` 経由では install space が PYTHONPATH に入っているため、この追加は
無害な重複になる。
"""

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))
