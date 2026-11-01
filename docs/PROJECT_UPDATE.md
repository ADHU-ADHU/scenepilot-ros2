# Project update · ongoing master's thesis

**Updated 2 November 2026**

ScenePilot started as a ROS 2 project connecting natural-language requests to visual question answering and semantic target segmentation. That working perception prototype is now the foundation for my ongoing master's thesis on **network- and latency-aware robot perception**.

## Research direction

A robot's perception pipeline depends on both communication and computation. Video that arrives late, or an AI processing choice that takes too long, can make otherwise useful visual information less useful to the robot.

The thesis investigates how **video transport settings and AI processing choices affect end-to-end latency and perception performance**, and how the system can adapt as network conditions change. The communication work involves **SCReAM congestion control and L4S**. A **Husky mobile robot** is planned as the physical platform for experiments.

Current work focuses on characterizing communication–AI trade-offs, exploring runtime adaptation, and preparing the system for robot experiments. This is an overview of work in progress; it does not report completed Husky integration or thesis evaluation results.

## Public prototype and thesis scope

| Part | Public status |
| --- | --- |
| Language-guided perception prototype | Source and recorded ROS 2 Jazzy demos in this repository: Qwen3-VL visual questions/target selection and SAM 3 segmentation |
| SCReAM transport reference | [Upstream open-source implementation by Ericsson Research](https://github.com/EricssonResearch/scream) |
| L4S background | [Public architecture specification, RFC 9330](https://www.rfc-editor.org/rfc/rfc9330.html) |
| Thesis extension and Husky experiments | Ongoing; thesis-specific methods, implementation details, experimental configurations and unpublished results are not released here |

SCReAM is an upstream transport component, rather than a claim that the wider thesis system is open source. L4S concerns low network queuing delay; its use alone does not establish an end-to-end perception-latency improvement. The thesis investigates the complete communication and processing trade-off.

The videos show the earlier public perception workflow. They are not demonstrations of a completed SCReAM/L4S-enabled Husky deployment. The existing [capability and validation status](STATUS.md) continues to describe what has actually been implemented and checked in this public codebase.

[Back to ScenePilot](../README.md) · [Silent demo and original recordings](demos/README.md)

