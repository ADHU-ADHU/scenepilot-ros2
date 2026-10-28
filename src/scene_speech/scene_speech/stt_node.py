import threading

import numpy as np
import rclpy
import sounddevice as sd

from faster_whisper import WhisperModel
from rclpy.node import Node
from std_msgs.msg import String


SAMPLE_RATE = 16000


class SpeechNode(Node):

    def __init__(self):
        super().__init__("speech_node")

        self.declare_parameter(
            "model",
            "small.en",
        )

        model_name = self.get_parameter(
            "model"
        ).value

        self.publisher = self.create_publisher(
            String,
            "/speech/transcript",
            10,
        )

        self.get_logger().info(
            f"Loading Whisper model: {model_name}"
        )

        # CPU first because SAM + Qwen use the GPU.
        self.model = WhisperModel(
            model_name,
            device="cpu",
            compute_type="int8",
        )

        self.frames = []
        self.recording = False

        self.get_logger().info(
            "Whisper ready"
        )

        thread = threading.Thread(
            target=self.input_loop,
            daemon=True,
        )

        thread.start()

    def audio_callback(
        self,
        indata,
        frames,
        time_info,
        status,
    ):

        if status:
            self.get_logger().warning(
                str(status)
            )

        if self.recording:
            self.frames.append(
                indata.copy()
            )

    def input_loop(self):

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=self.audio_callback,
        ):

            while rclpy.ok():

                input(
                    "\nPress ENTER to start speaking..."
                )

                self.frames = []
                self.recording = True

                print(
                    "Listening... "
                    "Press ENTER when finished."
                )

                input()

                self.recording = False

                if not self.frames:
                    print("No audio received.")
                    continue

                audio = np.concatenate(
                    self.frames,
                    axis=0,
                ).flatten()

                print("Transcribing...")

                segments, _ = (
                    self.model.transcribe(
                        audio,
                        language="en",
                        vad_filter=True,
                    )
                )

                text = " ".join(
                    segment.text.strip()
                    for segment in segments
                ).strip()

                if not text:
                    print(
                        "No speech detected."
                    )
                    continue

                print(
                    f'You said: "{text}"'
                )

                msg = String()
                msg.data = text

                self.publisher.publish(msg)

                self.get_logger().info(
                    f'Published /speech/transcript: "{text}"'
                )


def main(args=None):

    rclpy.init(args=args)

    node = SpeechNode()

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
