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

## Voice-First Runtime 接续

语音运行时已经进入分阶段实施，接手 W-V01/W-V02/W-V03 前先读：

- [Voice-First Runtime 接续指南](Voice_First_Handoff_2026-09-19.md) — 当前 main / PR 状态、已验证证据、未放行项、SpeechRail 接线触发条件与下一团队开工顺序；
- [Voice-First 实施方案](Voice_First_Implementation_Plan_v2.0.md) — W-V00–W-V10 任务边界；
- [Voice-First 验收矩阵](Voice_First_Acceptance_v2.0.md) — 软件、服务、设备和发布证据。

接续指南是**当前执行快照**；架构意图仍以 `docs/03_工程规范/voice/` 下的设计为准，最终能力事实以 main 代码、受保护 contracts 和成功门禁为准。

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
