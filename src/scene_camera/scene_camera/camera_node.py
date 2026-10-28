import cv2
import rclpy

from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


class CameraNode(Node):

    def __init__(self):
        super().__init__("camera_node")

        self.declare_parameter(
            "device",
            "/dev/video0",
        )

        self.declare_parameter(
            "topic",
            "/camera/image_raw",
        )

        self.declare_parameter(
            "frame_id",
            "camera",
        )

        self.declare_parameter(
            "fps",
            10.0,
        )

        self.declare_parameter(
            "width",
            1280,
        )

        self.declare_parameter(
            "height",
            720,
        )

        device = self.get_parameter(
            "device"
        ).value

        topic = self.get_parameter(
            "topic"
        ).value

        self.frame_id = self.get_parameter(
            "frame_id"
        ).value

        fps = float(
            self.get_parameter("fps").value
        )

        width = int(
            self.get_parameter("width").value
        )

        height = int(
            self.get_parameter("height").value
        )

        self.bridge = CvBridge()

        self.publisher = self.create_publisher(
            Image,
            topic,
            qos_profile_sensor_data,
        )

        self.failed_reads = 0

        self.cap = cv2.VideoCapture(
            device,
            cv2.CAP_V4L2,
        )

        if not self.cap.isOpened():
            raise RuntimeError(
                f"Could not open camera: {device}"
            )

        self.cap.set(
            cv2.CAP_PROP_FRAME_WIDTH,
            width,
        )

        self.cap.set(
            cv2.CAP_PROP_FRAME_HEIGHT,
            height,
        )

        self.cap.set(
            cv2.CAP_PROP_FPS,
            fps,
        )

        actual_width = int(
            self.cap.get(
                cv2.CAP_PROP_FRAME_WIDTH
            )
        )

        actual_height = int(
            self.cap.get(
                cv2.CAP_PROP_FRAME_HEIGHT
            )
        )

        actual_fps = self.cap.get(
            cv2.CAP_PROP_FPS
        )

        self.get_logger().info(
            f"Camera device: {device}"
        )

        self.get_logger().info(
            f"Publishing: {topic}"
        )

        self.get_logger().info(
            f"Actual camera mode: "
            f"{actual_width}x{actual_height} "
            f"@ {actual_fps:.2f} FPS"
        )

        self.timer = self.create_timer(
            1.0 / fps,
            self.capture_frame,
        )

    def capture_frame(self):

        ok, frame = self.cap.read()

        if not ok:

            self.failed_reads += 1
            if self.failed_reads >= 10:
                self.cap.release()
                self.cap.open(str(self.get_parameter("device").value), cv2.CAP_V4L2)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(self.get_parameter("width").value))
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.get_parameter("height").value))
                self.cap.set(cv2.CAP_PROP_FPS, float(self.get_parameter("fps").value))
                self.failed_reads = 0
            self.get_logger().warning(
                "Failed to read frame"
            )
            return

        self.failed_reads = 0

        msg = self.bridge.cv2_to_imgmsg(
            frame,
            encoding="bgr8",
        )

        msg.header.stamp = (
            self.get_clock().now().to_msg()
        )

        msg.header.frame_id = self.frame_id

        self.publisher.publish(msg)

    def destroy_node(self):

        if self.cap is not None:
            self.cap.release()

        super().destroy_node()


def main(args=None):

    rclpy.init(args=args)

    node = CameraNode()

    try:
        rclpy.spin(node)

    except KeyboardInterrupt:
        pass

    finally:
        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
