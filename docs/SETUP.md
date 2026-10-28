# Setup and execution

## Environment

The ROS image uses Ubuntu 24.04, ROS 2 Jazzy and Python 3.12. The SAM image isolates its PyTorch/CUDA dependencies from ROS. The default stack uses Linux host networking and an NVIDIA GPU exposed through Docker. Follow the official [Docker Compose GPU setup](https://docs.docker.com/compose/how-tos/gpu-support/) for host prerequisites.

The supplied recipe installs PyTorch 2.10 / torchvision 0.25 with CUDA 12.8 wheels; verify host-driver compatibility before a learned-model run. CPU unit tests and deterministic mock adapters do not need a GPU. The working deployment used Ollama 0.40.9, which is the example image tag in this repository. Image tags and package repositories remain mutable; record final image digests when reproducing experiments.

```bash
cp .env.example .env
mkdir -p models data artifacts
```

Edit `.env` to set `SAM_CHECKPOINT` to a real file, or place the checkpoint at `models/sam3.pt`. Obtain checkpoint access through the [SAM 3 upstream project](https://github.com/facebookresearch/sam3) under its terms. The repository contains source, not model weights; the SAM service mounts the checkpoint read-only and does not download it implicitly.

The default settings are `ROS_DOMAIN_ID=42`, `rmw_cyclonedds_cpp`, localhost discovery, front `/dev/video0`, rear `/dev/video2`, and GPU 0. Change device paths to match the host. `.env` and runtime/model directories are excluded from Git.

## Build and start

```bash
bash scripts/preflight.sh
docker compose config --quiet
docker compose build
docker compose up -d ollama
docker compose exec ollama ollama pull qwen3-vl:4b-instruct-q4_K_M
docker compose up -d vlm4 vlm2 sam
```

To select the 2B alternative later, first download it:

```bash
docker compose exec ollama ollama pull qwen3-vl:2b-instruct-q4_K_M
```

`vlm2`, `vlm4` and `sam` must all be running because the serial resource group requests unload acknowledgements from every member. An alternative model may remain unpulled while unused; selecting it requires its weights. Ollama persists downloaded models in the `ollama-cache` volume.

With host NumPy, OpenCV and PyYAML available, verify readiness before starting coordination:

```bash
python3 scripts/verify_backend.py qwen4
python3 scripts/verify_backend.py sam3
docker compose up -d system evaluator
docker compose logs -f system evaluator vlm4 sam
```

Readiness checks verify capability/configuration, not accuracy. `verify_backend.py qwen4 --front /path/to/image.jpg` optionally exercises real image inference. Run direct probes while coordination is stopped, since they bypass its GPU lease.

The default endpoints are loopback ports 11435 (Ollama), 18081/18082 (VLM adapters) and 18083 (SAM). APIs are internal to this local deployment. `PLATFORM_CONFIG` selects the coordinator/evaluator YAML; backend service commands explicitly load `config/platform.yaml`. Update both when introducing a different learned-backend configuration.

## Supply camera images

For one V4L2 camera, set `FRONT_DEVICE` in `.env` and start the single-camera profile:

```bash
docker compose --profile single-camera up -d front_camera
```

This profile publishes the front view at 640 × 480 with a requested 10 FPS. It exposes only the front device and does not require a rear camera. For two local cameras, stop `front_camera`, set both device paths in `.env` and use:

```bash
docker compose --profile cameras up -d cameras
```

An existing ROS camera driver can supply the configured topics instead. Run one publisher per camera topic. Remote publishers need compatible ROS discovery/network settings; the default only discovers local participants.

## Text commands and visualization

`scripts/ros_exec.sh` explicitly sources Jazzy and the built workspace inside the existing `system` container before running a command:

```bash
bash scripts/ros_exec.sh ros2 run scene_user text_interface
```

Enter a request such as `Track the phone in the front camera.` or `What is the person holding?`. To inspect outputs from another terminal:

```bash
bash scripts/ros_exec.sh ros2 topic echo /assistant/reply
bash scripts/ros_exec.sh ros2 topic echo /perception/status
```

For host RViz, source Jazzy and match the ROS environment:

```bash
source /opt/ros/jazzy/setup.bash
export ROS_DOMAIN_ID=42
export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp
export ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
rviz2
```

Install the appropriate Jazzy RViz package if it is not present. Add an **Image** display for `/tracking/image`, with **Best Effort** reliability. Source image timestamps and optical frame IDs are preserved. The container image itself does not include a desktop RViz session.

## Backend and target control

```bash
bash scripts/ros_exec.sh ros2 service call /perception/switch_backend \
  perception_interfaces/srv/SwitchBackend '{kind: vlm, backend: qwen2}'

bash scripts/ros_exec.sh ros2 service call /perception/select_target \
  perception_interfaces/srv/SelectTarget \
  '{camera: front, target: "phone", stop: false}'

bash scripts/ros_exec.sh ros2 service call /perception/select_target \
  perception_interfaces/srv/SelectTarget \
  '{camera: front, target: "", stop: true}'
```

A switch accepts a backend route; actual model readiness is checked when it is used. Errors appear on `/perception/events`. Query, manual-selection, stop and switching events invalidate stale work. The default serial GPU group unloads one model before loading another; this adds cold-load delays and can pause segmentation during VLM questions. `inference_hz: 5.0` is a requested scheduling limit, not a measured 5 FPS guarantee.

## Optional speech and depth

```bash
docker compose --profile speech build speech
docker compose --profile speech run --rm speech
```

Speech uses Whisper CPU/int8 with Enter-to-record input and `/dev/snd` access. The default `small.en` may need model download/cache preparation; a local model can be selected through `WHISPER_MODEL`. Microphone operation is hardware-dependent.

Depth is disabled in the default learned-model configuration. Enable it only with registered, rectified depth, matching calibration, timestamps and optical frames. See the [depth contract](ARCHITECTURE.md#depth-contract). Synthetic depth checks do not establish physical range accuracy.

## CPU tests and source build

Run `python -m pytest -q tests` in a virtual environment containing `docker/requirements-api.txt` and pytest. The standalone mock container uses deterministic CPU backends:

```bash
docker compose -f compose.mock.yaml build
docker compose -f compose.mock.yaml run --rm smoke
```

Stop this project's real stack before that test because the adapter ports overlap. The smoke test exercises ROS and HTTP in one container; it does not establish cross-container DDS behavior or learned-model performance.

For a local Jazzy source build in a clean shell:

```bash
source /opt/ros/jazzy/setup.bash
colcon build --base-paths src --executor sequential --cmake-args -DBUILD_TESTING=OFF
source install/setup.bash
ROS_LOG_DIR=/tmp/scenepilot-ros-logs \
  EVALUATION_DIR="$PWD/artifacts/evaluation" \
  python3 scripts/ros_smoke.py --in-process-backends
```

## Recovery

Inspect `docker compose ps` and logs before retrying a failed query. A crashed process uses `restart: unless-stopped`; an unhealthy-but-running server may need `docker compose restart sam` or the affected adapter. HTTP timeouts do not cancel server inference, so the scheduler keeps its GPU lease until an unload acknowledgement resolves residency. Do not start a second coordinator on the same managed GPU.

Rebuild the affected image after source edits. Config/prompts are mounted read-only and reload when the affected service restarts. Use `docker compose down` to stop the project; model volumes persist unless explicitly removed.
