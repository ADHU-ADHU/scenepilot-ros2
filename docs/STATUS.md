# Project status and validation

ScenePilot is an active perception project. The author demonstrated the Jazzy container workflow using a real camera, natural-language requests, VLM responses, and SAM segmentation in RViz2. Three synchronized screen-recording views were supplied: terminal, RViz2 and combined. Edited excerpts are included in [demos](demos/README.md).

## Capability status

| Area | Current state |
| --- | --- |
| VLM questions and target selection | Demonstrated with Qwen3-VL 4B; recorded smartphone question/answer |
| SAM 3 segmentation overlays | Demonstrated on person, phone, headphones and glasses |
| Front/rear input routing | Implemented; exercised with synthetic front/rear ROS streams |
| Target changes, stop and stale-response handling | Implemented; covered by CPU tests and synthetic ROS/HTTP workflow |
| Serial GPU lifecycle control | Implemented; model loading/unloading behavior is part of the deployment, without a published VRAM/latency benchmark |
| 2B VLM alternative and model comparisons | Configured interfaces; the smaller model must be downloaded before inference |
| Optional speech input | Included; no fresh microphone validation performed |
| Registered depth and 3D estimates | Implemented and tested on synthetic aligned depth; physical calibration/accuracy remains unvalidated |
| Persistent instance tracking / reidentification | Future work; current output is per-frame prompt segmentation |
| Automatic backend optimization policy | Future work; switching and metric interfaces are implemented |
| Robot movement / autonomous navigation | Outside the implemented perception workflow |
| Kubernetes deployment | Future deployment option; no completed cluster deployment is claimed |

## Fresh publication checks — 25 October 2026

| Check | Result | Scope |
| --- | --- | --- |
| Existing unit tests | **18 passed** | Contracts, adapter behavior, response identity, switching, GPU resource logic, recovery, depth and quality-state handling |
| Clean ROS 2 Jazzy build | **7 packages built** | Rebuilt from source with the public package names; no previous build/install artifacts reused |
| In-process ROS smoke | **Passed, 6 checks** | Actual ROS pub/sub/services with deterministic CPU backend dispatch |
| HTTP + ROS smoke | **Passed, 6 checks** | Loopback HTTP adapters and actual Jazzy messages/services; isolated ports/domain |
| Static checks | **Passed** | Python syntax, YAML, package XML, shell syntax and local documentation links |
| Runtime source comparison | **Passed** | 19 runtime Python files compared to supplied source; differences limited to package identifiers and the interface banner |

Both synthetic smoke runs exercised front/rear selection, metadata preservation, in-flight backend switching, independent comparison outputs, RGB-only operation, injected backend failure/recovery and atomic stop. Each short run observed nine tracking results, 22 annotated frames and 18 metric/event records. Counts depend on asynchronous scheduling and are functional-test evidence, not performance targets.

Machine-readable results are in [validation/publication-checks.json](validation/publication-checks.json). The supplied videos and the author's successful deployment reports provide learned-model demo evidence. The fresh checks above used deterministic CPU fixtures and did not rerun Docker image builds, CUDA inference, physical cameras, microphone input or GUI visualization.

## Interpretation and remaining work

The VLM chooses a semantic target; SAM returns masks for each processed image. The highest-confidence mask drives quality/depth summaries. There is no stable track identity across frames, and multiple matching objects can change which mask is selected. Evaluation currently records latency and consistency proxies, not labelled accuracy.

The GPU group defaults to serial operation, with explicit unload acknowledgement before admitting another model. This trades memory residency for reload latency. A new VLM question can interrupt segmentation; configured scheduling frequency should not be interpreted as measured throughput.

Next validation steps are sustained real-camera runs, measured cold/warm model latency and memory, physical depth calibration, labelled evaluation, and comparison of backend configurations on equivalent recorded inputs.
