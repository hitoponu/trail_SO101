#include <memory>

#include "laser_geometry/laser_geometry.hpp"
#include "rclcpp/rclcpp.hpp"
#include "sensor_msgs/msg/laser_scan.hpp"
#include "sensor_msgs/msg/point_cloud2.hpp"

class ScanToCloud : public rclcpp::Node
{
public:
  ScanToCloud() : Node("scan_to_cloud")
  {
    const auto sensor_qos = rclcpp::SensorDataQoS();
    publisher_ = create_publisher<sensor_msgs::msg::PointCloud2>("scan/points", sensor_qos);
    subscription_ = create_subscription<sensor_msgs::msg::LaserScan>(
      "scan", sensor_qos,
      [this](sensor_msgs::msg::LaserScan::ConstSharedPtr scan) {
        sensor_msgs::msg::PointCloud2 cloud;
        projector_.projectLaser(*scan, cloud);
        publisher_->publish(cloud);
      });
  }

private:
  laser_geometry::LaserProjection projector_;
  rclcpp::Publisher<sensor_msgs::msg::PointCloud2>::SharedPtr publisher_;
  rclcpp::Subscription<sensor_msgs::msg::LaserScan>::SharedPtr subscription_;
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<ScanToCloud>());
  rclcpp::shutdown();
  return 0;
}
