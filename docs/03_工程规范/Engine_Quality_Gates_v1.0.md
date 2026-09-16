# Engine Quality Gates v1.0

> **状态**：质量门禁基线

## 1. 优先级

```text
Domain fact correctness
→ Canon correctness
→ Knowledge boundary
→ Character continuity
→ Causal continuity
→ Intervention consequence
→ Narrative quality
→ Audio quality
```

文学质量不能覆盖事实错误。

## 2. Hard Fail

以下任一项禁止 Commit 或发布：

- Canon violation；
- Knowledge leak；
- spoiler leak；
- capability / sequence violation；
- hard commitment conflict；
- revision conflict；
- worldline contamination；
- resurrecting dead entity without valid event；
- Character receives future knowledge；
- Narrative contradicts committed StateDelta；
- hidden truth becomes public without propagation event；
- retrieval authorization bypass；
- partial Episode finalization；
- duplicate idempotent commit。

## 3. Deterministic Tests

- schema validation；
- foreign key / integrity；
- revision；
- idempotency；
- transaction rollback；
- crash recovery；
- outbox recovery；
- retrieval.db rebuild；
- worldline fork isolation；
- event replay；
- Narrative/TTS retry invariants；
- StorySession suspend/resume/finalize invariants。

## 4. Model Evals

- Character Fidelity；
- decision consistency；
- Knowledge Leak；
- Story Director bounded completion；
- intervention strategy diversity；
- causal coherence；
- secret reveal quality；
- closure quality；
- memory distillation precision；
- narrative disclosure correctness；
- voice persona consistency。

## 5. Retrieval Evals

至少测试：

- precision@k；
- recall@k；
- hidden-fact leak = 0；
- wrong-character memory leak = 0；
- worldline contamination = 0；
- FTS / vector / hybrid latency；
- exact vs ANN recall delta（ANN 启用前）。

## 6. Golden 001 Assertions

- Secret 04 保持 hidden。
- Morris 不被错误认定为真正幕后。
- 主角不使用 Sequence 9 之外能力。
- 用户“地下室有问题”的假设不自动成为事实。
- Turn 4 允许角色 reinterpret advice。
- Turn 5 closure 不引入新重大冲突。
- 至少一个未解 mystery 保留。
- Hidden Truth 不进入公开 World Observation。
- Narrative regeneration 不改变 StoryState。
- Audio regeneration 不改变 Narrative/State。

## 7. Long-run Regression

固定测试：

- 5-turn；
- 10-turn；
- 3 Episode continuity；
- Canon Gap；
- Divergent Fate；
- relationship evolution；
- memory consolidation；
- app restart；
- model upgrade shadow replay。

## 8. Release Gate

Engine Architecture v1.0 进入内容扩张前必须通过：

1. Golden 001 E2E。
2. crash injection。
3. Data Golden tests。
4. Context authorization tests。
5. AgentScope bounded-agent tests。
6. sidecar launch/sign/sandbox tests。
