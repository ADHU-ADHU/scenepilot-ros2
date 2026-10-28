# Publication source notes

This repository was prepared from the existing ROS 2 Jazzy container platform. The working source folder and original screen recordings were preserved separately.

Publication changes are limited to presentation and portability:

- Four camera, user-interface, speech and command-interface packages use the public `scene_*` names, with matching imports, launch files and entry points.
- The terminal banner and package descriptions use ScenePilot naming.
- Compose projects/images use neutral ScenePilot names. The Ollama example tag is 0.40.9, matching the reported working deployment.
- Setup, architecture, validation status, evaluation instructions and demo navigation are documented for a new checkout.
- `scripts/ros_exec.sh` sources Jazzy and the installed workspace before running commands through `docker compose exec`.
- A single-camera Compose profile exposes only the front device, without requiring a second camera.

The model adapters, coordinator, scheduling, segmentation, depth and evaluation logic were preserved. A comparison of 19 runtime Python files found only the intended package-identifier/banner substitutions. Existing tests were rerun and all seven ROS packages were rebuilt with the public names.

The [source manifest](source-manifest.json) records input and publication checksums for copied source/configuration files. The SAM snapshot has separate [upstream provenance](../vendor/PROVENANCE.json); demo edits have a [media manifest](demos/media-manifest.json).

Build/install trees, private environment files, model checkpoints, runtime bags, personal infrastructure notes and historical generated logs are excluded. New validation results distinguish CPU test evidence from the supplied learned-model recordings.
