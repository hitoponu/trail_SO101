from lerobot.robots.so_follower import SO101FollowerConfig, SO101Follower
from lerobot.teleoperators.so_leader import SO101LeaderConfig, SO101Leader
import argparse

parser = argparse.
config = SO101FollowerConfig(
    port="/dev/tty.usbmodem585A0076891",
    id="my_awesome_follower_arm",
)

follower = SO101Follower(config)
follower.connect(calibrate=False)
follower.calibrate()
follower.disconnect()


config = SO101LeaderConfig(
    port="/dev/tty.usbmodem58760431551",
    id="my_awesome_leader_arm",
)

leader = SO101Leader(config)
leader.connect(calibrate=False)
leader.calibrate()
leader.disconnect()