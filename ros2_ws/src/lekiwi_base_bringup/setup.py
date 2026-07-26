import os
from glob import glob

from setuptools import find_packages, setup

package_name = "lekiwi_base_bringup"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (os.path.join("share", package_name, "config"), glob("config/*.yaml")),
        (os.path.join("share", package_name, "rviz"), glob("rviz/*.rviz")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="maintainer",
    maintainer_email="maintainer@example.com",
    description="ROS 2 driver for the LeKiwi 3-wheel omnidirectional mobile base.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "base_driver = lekiwi_base_bringup.base_driver:main",
            "sts_bus = lekiwi_base_bringup.sts_bus:main",
        ],
    },
)
