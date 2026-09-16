# Golden 001 Executable Test Spec v1.0

> **场景**：《不存在的预约》  
> **用途**：工程启动阶段唯一端到端回归夹具。

## 1. 固定执行

初始人物知识来自 `knowledge/*.json`，不嵌入 Character State。


StorySession：

```text
session_id = session_golden_001
initial_story_revision = 0
base_world_revision = 103
base_character_revision = 27
```

5 个 Turn 依次执行，Story revision 每次成功 Commit 后 +1。

## 2. Mock 边界

Mock：

- Advice Interpreter：使用 `04_Golden_Scenarios/golden_001/turns/*_advice.json`。
- Character Reasoner：`mock/*_action_intent.json`。
- Story Director：`mock/*_beat_plan.json`。
- Narrative Compiler：`mock/*_narrative_block.json`。

真实代码：

- Session Orchestrator；
- Outcome Resolver；
- Validators；
- Revision；
- Idempotency；
- SQLite transaction；
- Memory / Knowledge writeback；
- Outbox；
- Episode Finalization；
- Restart Recovery。

因此 Mock Golden 测试的是 Engine，而不是 LLM 文学能力。

## 3. Turn Commit 断言

`expected/*_committed_state.json` 是每轮事实级断言。

### Turn 1
- revision=1；
- doctor pause clue；
- suspicion=0；
- Secret 全 hidden。

### Turn 2
- revision=2；
- appointment / removed page clues；
- suspicion=1；
- Secret 01/02 = suspected。

### Turn 3
- revision=3；
- basement powder；
- pipe sound 不代表有人；
- Secret 03 仅 suspected；
- Secret 04 hidden。

### Turn 4
- revision=4；
- Jonathan note；
- suspicion=2；
- Secret 01/02 revealed；
- Secret 03 partial；
- Secret 04 hidden。

### Turn 5
- revision=5；
- closure requested；
- 不新增 major conflict；
- secrets 不进一步越界揭示。

## 4. Episode Finalization

预期：
- Episode title = 不存在的预约；
- ending = partial_truth；
- Secret 04 hidden；
- unresolved = Jonathan location / occult group identity；
- Character episode memory 写入；
- 无重大 emotional memory；
- relationship evidence 写入；
- private occult evidence world event 写入；
- public observation 不泄露隐藏组织。

## 5. Restart

Finalization 后关闭 Engine，再打开：

必须断言：
- world revision 持久；
- Character Memory 存在；
- Character Knowledge 存在；
- Relationship State 一致；
- Episode 可读取；
- Story Book 使用历史 NarrativeBlock；
- Context Compiler 可召回 Episode Memory；
- Hidden Truth authorization 仍正确。

## 6. Failure Checkpoints

至少在以下位置 kill Engine：

```text
after advice
after action intent
after resolver before commit
immediately after commit
after beat plan
after narrative
during finalization transaction
after finalization commit before projection
```

恢复规则遵循 Runtime Orchestration v1.0。

## 7. PASS

- G001–G012；
- 5 个 expected committed state；
- Episode expected fixture；
- restart；
- idempotent replay；
- failure checkpoints；
- knowledge leak = 0。
