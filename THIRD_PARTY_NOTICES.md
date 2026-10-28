# Third-party components

ScenePilot integrates separate upstream model runtimes and libraries. Their licenses and checkpoint access terms remain applicable.

| Component | Role | Source / notice |
| --- | --- | --- |
| ROS 2 Jazzy | Robotics communication, node lifecycle, messages and tools | [ROS 2](https://docs.ros.org/en/jazzy/) |
| Qwen3-VL | Visual reasoning and target/camera selection | [Model catalog](https://ollama.com/library/qwen3-vl) |
| Ollama | Local Qwen model serving | [Ollama](https://github.com/ollama/ollama) |
| Meta SAM 3 | Text-prompted segmentation | [Upstream repository](https://github.com/facebookresearch/sam3), [included SAM License](vendor/SAM-LICENSE) |
| PyTorch, OpenCV, NumPy and supporting packages | Model inference and image processing | Versions are listed in the Docker recipes and requirements files |
| faster-whisper | Optional speech input | [Upstream repository](https://github.com/SYSTRAN/faster-whisper) |

`vendor/sam3-source.tar.gz` is the supplied source-only snapshot of Meta SAM 3. It includes its upstream `LICENSE`; the same text is also available as `vendor/SAM-LICENSE`. Its commit and archive checksum are recorded in [vendor/PROVENANCE.json](vendor/PROVENANCE.json). The SAM software and model contributions belong to Meta and their respective contributors. No SAM or Qwen checkpoint is redistributed here.

Package-level license declarations are retained in their manifests. Publication of this repository does not replace those declarations or grant rights to third-party weights.
