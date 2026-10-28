from collections import deque
import textwrap

import cv2
import numpy as np
import rclpy

from rclpy.node import Node
from std_msgs.msg import String


class AssistantPanel(Node):

    def __init__(self):
        super().__init__(
            "assistant_panel"
        )

        # =====================================================
        # DISPLAY SETTINGS
        # =====================================================

        self.width = 1100
        self.height = 760

        self.history = deque(
            maxlen=16
        )

        self.sam_camera = "none"
        self.sam_target = "none"

        self.last_voice_text = None
        self.last_typed_text = None

        # =====================================================
        # ROS SUBSCRIBERS
        # =====================================================

        self.voice_sub = self.create_subscription(
            String,
            "/speech/transcript",
            self.voice_callback,
            10,
        )

        self.text_sub = self.create_subscription(
            String,
            "/assistant/query",
            self.text_callback,
            10,
        )

        self.reply_sub = self.create_subscription(
            String,
            "/assistant/reply",
            self.reply_callback,
            10,
        )

        self.camera_sub = self.create_subscription(
            String,
            "/sam/camera",
            self.camera_callback,
            10,
        )

        self.target_sub = self.create_subscription(
            String,
            "/sam/target",
            self.target_callback,
            10,
        )

        # GUI refresh.
        self.timer = self.create_timer(
            0.05,
            self.update_window,
        )

        self.get_logger().info(
            "Assistant panel started"
        )

        self.get_logger().info(
            "Listening to /speech/transcript"
        )

        self.get_logger().info(
            "Listening to /assistant/reply"
        )

    # =========================================================
    # CALLBACKS
    # =========================================================

    def voice_callback(self, msg):

        text = msg.data.strip()

        if not text:
            return

        self.last_voice_text = text

        self.history.append(
            (
                "USER",
                text,
            )
        )

    def text_callback(self, msg):

        text = msg.data.strip()

        if not text:
            return

        self.last_typed_text = text

        self.history.append(
            (
                "USER",
                text,
            )
        )

    def reply_callback(self, msg):

        text = msg.data.strip()

        if not text:
            return

        self.history.append(
            (
                "ASSISTANT",
                text,
            )
        )

    def camera_callback(self, msg):

        value = msg.data.strip()

        if value:
            self.sam_camera = value

    def target_callback(self, msg):

        value = msg.data.strip()

        if value == "__STOP__":
            self.sam_target = "none"

        elif value:
            self.sam_target = value

    # =========================================================
    # TEXT DRAWING
    # =========================================================

    def draw_text_block(
        self,
        image,
        text,
        x,
        y,
        max_chars=72,
        font_scale=0.70,
        thickness=2,
        line_height=31,
    ):

        wrapped = textwrap.wrap(
            text,
            width=max_chars,
        )

        if not wrapped:
            wrapped = [""]

        for line in wrapped:

            cv2.putText(
                image,
                line,
                (
                    x,
                    y,
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                font_scale,
                (
                    230,
                    230,
                    230,
                ),
                thickness,
                cv2.LINE_AA,
            )

            y += line_height

        return y

    # =========================================================
    # GUI
    # =========================================================

    def update_window(self):

        canvas = np.zeros(
            (
                self.height,
                self.width,
                3,
            ),
            dtype=np.uint8,
        )

        # -----------------------------------------------------
        # HEADER
        # -----------------------------------------------------

        cv2.rectangle(
            canvas,
            (0, 0),
            (
                self.width,
                82,
            ),
            (
                35,
                35,
                35,
            ),
            -1,
        )

        cv2.putText(
            canvas,
            "ROBOT VISION ASSISTANT",
            (
                30,
                48,
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.05,
            (
                255,
                255,
                255,
            ),
            2,
            cv2.LINE_AA,
        )

        # -----------------------------------------------------
        # SAM STATUS
        # -----------------------------------------------------

        status = (
            f"SAM camera: "
            f"{self.sam_camera.upper()}    "
            f"Target: {self.sam_target}"
        )

        cv2.putText(
            canvas,
            status,
            (
                30,
                105,
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (
                0,
                220,
                255,
            ),
            2,
            cv2.LINE_AA,
        )

        cv2.line(
            canvas,
            (
                20,
                125,
            ),
            (
                self.width - 20,
                125,
            ),
            (
                100,
                100,
                100,
            ),
            1,
        )

        # -----------------------------------------------------
        # CONVERSATION
        # -----------------------------------------------------

        y = 160

        items = list(
            self.history
        )

        # Draw the newest messages that fit.
        for role, text in items:

            if y > (
                self.height - 80
            ):
                break

            if role == "USER":

                role_color = (
                    0,
                    220,
                    255,
                )

            else:

                role_color = (
                    0,
                    255,
                    120,
                )

            cv2.putText(
                canvas,
                role,
                (
                    35,
                    y,
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.74,
                role_color,
                2,
                cv2.LINE_AA,
            )

            y += 31

            y = self.draw_text_block(
                canvas,
                text,
                55,
                y,
                max_chars=78,
                font_scale=0.68,
                thickness=2,
                line_height=29,
            )

            y += 23

        # -----------------------------------------------------
        # FOOTER
        # -----------------------------------------------------

        cv2.putText(
            canvas,
            "Voice input: Whisper  |  Vision: Qwen3-VL  |  Tracking: SAM",
            (
                30,
                self.height - 25,
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (
                160,
                160,
                160,
            ),
            1,
            cv2.LINE_AA,
        )

        cv2.imshow(
            "Robot Assistant",
            canvas,
        )

        cv2.waitKey(1)

    # =========================================================
    # CLEANUP
    # =========================================================

    def destroy_node(self):

        cv2.destroyAllWindows()

        super().destroy_node()


def main(args=None):

    rclpy.init(
        args=args
    )

    node = AssistantPanel()

    try:

        rclpy.spin(
            node
        )

    except KeyboardInterrupt:

        pass

    finally:

        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()

