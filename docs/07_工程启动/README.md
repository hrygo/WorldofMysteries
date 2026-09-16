# 工程启动基线 v1.0

该目录定义设计基线进入工程实现之前的最终准备要求。

## P0 — Engineering GO

执行并通过：

1. `Local_Engine_Packaging_Spike_v1.0.md`
2. `IPC_Protocol_v1.0.md`
3. `Data_Kernel_Spike_v1.0.md`
4. `AgentScope_Spike_v1.0.md`
5. `golden_001_runtime/`
6. `Go_NoGo_Gates_v1.0.yaml`

P0 Gate：

```text
GATE-PACKAGE
GATE-PROTOCOL
GATE-DATA
GATE-AI
GATE-GOLDEN-MOCK
```

全部 PASS 后进入大规模领域功能并行开发。

## P1 — Release Readiness

- `Security_Privacy_Baseline_v1.0.md`
- `Content_Provenance_Release_Gate_v1.0.md`
- `Repository_CI_Baseline_v1.0.md`
- Voice / real-model E2E gates

## Machine-readable

- `Engineering_Tasks_v1.0.yaml`
- `Go_NoGo_Gates_v1.0.yaml`
- `protocol/engine_ipc.schema.json`

## Golden Runtime

`golden_001_runtime/` 提供：

- 固定 World / Character / Seed；
- 5 个 Mock ActionIntent；
- 5 个 Mock BeatPlan；
- 5 个 Mock NarrativeBlock；
- 每轮 committed-state expectation；
- Episode expectation；
- failure / restart assertions。

Mock E2E 使用真实 Session Orchestrator、Resolver、Validator、SQLite transaction、Outbox 和 Finalization。
