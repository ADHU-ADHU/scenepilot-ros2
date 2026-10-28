# Repeatable experiments

The evaluator is independent of control. It subscribes to `/models/<backend>/result`, emits `/evaluation/metrics` and appends JSONL files in the configured data directory. A session UUID prevents metrics from different coordinator restarts being combined as one trajectory. Generation, camera, target and backend separate temporal state. Backward ROS time jumps invalidate old work and reset frame buffers.

| Measurement | Meaning | Limitation |
|---|---|---|
| `inference_ms` | Backend dispatch wall time, including lazy model load and preprocessing | Not pure CUDA kernel latency; first/cold request is different from warm requests |
| `request_ms` | Queue/resource wait, HTTP exchange and backend work | Does not include ROS time spent before the request was dispatched |
| `frame_age_ms` | RGB acquisition to coordinator completion, in ROS clock time | Requires clock synchronization on real multi-host data; under bag playback it measures simulation-time age, not physical wall latency |
| `processing_rate_hz` | Observer wall-time result rate | Includes transport/scheduling; observer delivery jitter affects it |
| `source_rate_hz` | Rate implied by consecutive processed source timestamps | This is the sampled source rate, not camera capture FPS |
| mask IoU proxy | Overlap of consecutive highest-confidence masks | Not IoU against ground truth; camera/target motion and instance changes reduce it |
| loss/reacquisition events | Transition between detected and not detected masks | No persistent identity guarantee; missing input/failed inference is reported as an error, not falsely counted as target loss |
| depth MAD / delta / valid fraction | Within-mask spread, between-frame depth change, valid depth coverage | Scene geometry, movement and sensor noise affect these; not range accuracy |

Accuracy evaluation needs labelled ground truth, instance associations and timing alignment. Segmentation IoU/Dice require reference masks; IDF1/HOTA require persistent track identities and annotations; depth/3D errors require reference distances/poses. These accuracy metrics are **not implemented or claimed**. Confidence values from different models are not calibrated probabilities and should not be compared as equivalent scores.

## Record real input

Use one source of camera inputs at a time. Start the camera driver and record input topics (adjust to configured names):

```bash
bash scripts/ros_exec.sh ros2 bag record -o /data/bags/scene01 \
  /camera/front/image_raw /camera/rear/image_raw \
  /camera/front/depth/aligned /camera/rear/depth/aligned \
  /camera/front/camera_info /camera/rear/camera_info \
  /assistant/query /speech/transcript /tf /tf_static
```

Record either typed or voice inputs intentionally; replaying duplicated equivalent queries produces duplicated commands. Do not replay recorded `/sam/*`, annotated outputs or old evaluator results as new control inputs. The coordinator supports both input modalities; a particular experiment should specify which is authoritative.

## Replay

Stop live cameras and speech. Set `USE_SIM_TIME=true` in `.env` and recreate `system` and `evaluator`. Model containers stay on wall time for duration measurements. Check topic types and duration with `ros2 bag info` before playback.

```bash
docker compose up -d --force-recreate system evaluator
bash scripts/ros_exec.sh ros2 bag play /data/bags/scene01 --clock --rate 0.5 \
  --qos-profile-overrides-path /config/bag-qos.yaml
```

Choose a fixed playback rate that gives the tested models enough time for the intended experiment, and record the rate. The runtime intentionally samples latest frames and drops work when busy; different model speeds may process different frames. For paired quality comparisons join records by **source timestamp + frame ID/camera + target + generation**, and report unmatched samples rather than treating them as equivalent. For comparisons across separate runs, generations can differ; align by a predefined query timeline/selection segment and input timestamp. Same-frame shadows improve comparison coverage but do not make scheduling costs identical. Cold/warm runs must be separate. Set each model's seed/options in YAML, retain the exact YAML and prompt, record model digests/checkpoint SHA256 and image digests. GPU kernels and runtime scheduling may still be nondeterministic.

The evaluator writes a new file on restart. Restart the coordinator and evaluator between independent runs to reset history and masks. A bag loop's backward clock jump is also handled, but a fresh session is clearer for analysis. Use a unique `ROS_DOMAIN_ID` so unrelated experiments cannot publish into the run.

## Synthetic fixture

The fixture generator creates front/rear RGB, aligned 2 m depth, calibration and timed text commands. Frames 20–24 omit the red target to exercise loss/reacquisition. It contains no learned-model ground truth claim.

```bash
bash scripts/ros_exec.sh python3 /ws/scripts/create_test_bag.py /data/bags/synthetic_rgbd
bash scripts/ros_exec.sh ros2 bag info /data/bags/synthetic_rgbd
```

Use `config/mock.yaml` with its four CPU backend adapters to replay this fixture. For a complete standalone HTTP + Jazzy pub/sub test, no camera/model downloads are needed:

```bash
docker compose -f compose.mock.yaml build
docker compose -f compose.mock.yaml run --rm smoke
```

The mock Compose file is standalone; stop the real stack first because their adapter ports overlap. It runs actual ROS subscriptions/services and HTTP adapters in one container, using deterministic CPU fixtures. It does not validate network discovery between separate containers; that is a separate real Compose gate.

## Summarize

```bash
python3 scripts/summarize_metrics.py data/evaluation/metrics-*.jsonl --output data/summary.json
```

Summaries are grouped by session, backend and camera. Inspect individual generations and matching frames before drawing model-quality conclusions. The records also provide latency/resource-switch inputs for a later metaheuristic optimizer; no automatic optimization policy is enabled.
