"""Fixtures shared by the pure-Python tests.

The combined URDF is expanded from the real xacro rather than checked in, so
these tests fail if the geometry or the joint naming drifts. Where xacro is not
available (a bare Mac with no ROS), the tests that need it skip.
"""

import functools
import shutil
import subprocess
from pathlib import Path

import pytest

# .../lekiwi_examples/test/conftest.py -> .../ros2_ws/src
SRC = Path(__file__).resolve().parents[2]
COMBINED_XACRO = SRC / "lekiwi_so101_bringup" / "urdf" / "lekiwi_so101.urdf.xacro"


@functools.lru_cache(maxsize=1)
def _expand(path: str) -> str:
    xacro = shutil.which("xacro")
    if xacro is None:
        pytest.skip("xacro が無いので結合 URDF を展開できない")
    if not Path(path).exists():
        pytest.skip(f"{path} が無い")
    try:
        completed = subprocess.run(
            [xacro, path], capture_output=True, text=True, check=True, timeout=120
        )
    except subprocess.CalledProcessError as exc:
        pytest.fail(f"xacro の展開に失敗:\n{exc.stderr}")
    return completed.stdout


@pytest.fixture(scope="session")
def combined_urdf() -> str:
    """The LeKiwi base with the SO-101 arm attached, expanded to plain URDF."""
    return _expand(str(COMBINED_XACRO))
