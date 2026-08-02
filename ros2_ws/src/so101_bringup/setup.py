import os
from glob import glob

from setuptools import find_packages, setup

package_name = "so101_bringup"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml") + glob("config/*.xacro")),
        (os.path.join("share", package_name, "control"), glob("control/*.xacro")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="maintainer",
    maintainer_email="maintainer@example.com",
    description="Bringup and calibration tools for the standalone SO-101 follower arm.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "so101_probe = so101_bringup.sts_probe:main",
            "so101_calib = so101_bringup.lerobot_calib:main",
        ],
    },
)
