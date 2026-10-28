import threading

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class TextInterface(Node):

    def __init__(self):
        super().__init__("text_interface")

        self.query_pub = self.create_publisher(
            String,
            "/assistant/query",
            10,
        )

        self.reply_sub = self.create_subscription(
            String,
            "/assistant/reply",
            self.reply_callback,
            10,
        )

        self.get_logger().info("Text interface started")

        print()
        print("======================================")
        print(" ScenePilot Perception Assistant")
        print("======================================")
        print()
        print("Examples:")
        print("  what do you see?")
        print("  track person")
        print("  track the person wearing red")
        print("  stop tracking")
        print()
        print("Type 'exit' to quit.")
        print()

        self.input_thread = threading.Thread(
            target=self.input_loop,
            daemon=True,
        )

        self.input_thread.start()

    def input_loop(self):

        while rclpy.ok():

            try:
                text = input("You > ").strip()

            except EOFError:
                break

            if not text:
                continue

            if text.lower() in ["exit", "quit"]:
                print("Closing...")
                rclpy.shutdown()
                break

            msg = String()
            msg.data = text

            self.query_pub.publish(msg)

    def reply_callback(self, msg):

        print()
        print(f"Assistant > {msg.data}")
        print()


def main(args=None):

    rclpy.init(args=args)

    node = TextInterface()

    try:
        rclpy.spin(node)

    except KeyboardInterrupt:
        pass

    finally:

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
