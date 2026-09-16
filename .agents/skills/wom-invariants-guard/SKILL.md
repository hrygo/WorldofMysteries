---
name: wom-invariants-guard
description: >-
  《诡秘世界》15 项不可违背核心不变量 (Invariants) 守卫与架构适应度审计技能。提供逐项不变量的判定标准、反模式排查指南
  以及 scripts/check_architecture_fitness.py 静态 AST 检查机制。
---

# 《诡秘世界》15 项核心不变量审计与守卫技能 (wom-invariants-guard)

在《诡秘世界》中，15 条不变量是系统的“最高宪法”。任何代码实现、Agent 提示词设计或重构提案，一旦违反不变量，直接判定为架构事故。

---

## 1. 15 项不变量判定准则与反模式清单

### #1 世界先于故事 (World Precedes Story)
- **判定准则**：世界状态独立于单次故事，不因单次故事会话结束而重置。
- **反模式 (Violation)**：在 Story 结束时直接把 `WorldSnapshot` 重置为初始种子状态。
- **正例实现**：通过快照序列与增量 Delta 持久化世界演化。

### #2 角色先于剧情 (Character Precedes Plot)
- **判定准则**：角色具有稳定的身份、特质与长期目标，不随单次模型调用重新生成。
- **反模式 (Violation)**：在对话 Prompt 中要求 LLM “重新构想克莱恩的性格背景”。
- **正例实现**：角色属性由 Domain Database 的不可变锚点和信念历史决定。

### #3 Canon 约束历史 (Canon Bounds History)
- **判定准则**：Canon 既定历史不可篡改，开放未来不锁死。
- **反模式 (Violation)**：允许修改原著中已确立的历史事件或锚定事实。

### #4 Advice ≠ Command (建议不等于命令)
- **判定准则**：玩家的干预仅作为意图建议，角色依据自身动机拥有裁决阻断权。
- **反模式 (Violation)**：把玩家输入的 `PlayerAdvice` 直接当成角色一定会执行的行为。
- **正例实现**：角色 Reasoner 评估建议后可能“拒绝”、“顺从”或“曲解执行”。

### #5 AI 仅产出 Proposal，Domain Engine 负责 Commit
- **判定准则**：LLM / Agent 绝对严禁直接写入领域数据库。
- **反模式 (Violation)**：在 AgentScope 绑定的工具函数中直接调用 `db.execute("INSERT ...")`。
- **正例实现**：AI 仅输出强类型 `Proposal`，由确定性 `OutcomeResolver` 校验后执行领域提交。

### #6 零知识越界 (Zero Knowledge Leak)
- **判定准则**：`Character Reasoner` 严禁接收超出该角色已知边界与当前视界的信息。
- **反模式 (Violation)**：克莱恩是序列 9 占卜家时，Prompt 中直接注入序列 0 真神或远古太阳神的秘密。
- **正例实现**：`ContextCompiler` 在向量检索前根据角色权限层级执行硬过滤。

### #7 语义授权先行 (Semantic Authorization Precedes Execution)
- **判定准则**：上下文编译器裁决“有资格获知什么”，AI 仅负责消费授权上下文。
- **反模式 (Violation)**：允许 Agent 自由发起全局向量检索召回未授权 Canon 数据。

### #8 领域记忆与 Agent 记忆彻底分离
- **判定准则**：AgentScope 运行时内存仅作为单次会话执行辅助，事实源唯一归属于 SQLite。
- **反模式 (Violation)**：依赖 AgentScope Memory 的持久化作为角色长期关系事实源。

### #9 提交即命运 (Commit is Fate)
- **判定准则**：`Narrative Compiler` 与 `Audio / Voice Engine` 严格位于 `COMMIT` 之后。
- **反模式 (Violation)**：因 TTS 报错或 UI 崩溃而反向 Rollback 已经提交的世界状态。

### #10 用户世界绝不污染 Canon
- **判定准则**：`user_world` 写入独立的 `world.db`，物理上严禁反写 `canon.db`。
- **反模式 (Violation)**：在同一个 SQLite 数据库中混合存储 Canon 与用户动态演化数据。

### #11 权威持久与可重建分离
- **判定准则**：`world.db` 承担权威强事务；`retrieval.db` 仅为异步投影，删除后必须可 100% 幂等重建。
- **反模式 (Violation)**：把无法从 `world.db` 重新生成的元数据直接写入 `retrieval.db`。

### #12 App 进程不直连数据库
- **判定准则**：SwiftUI App 仅通过类型化 UDS IPC 与 Local Engine 交互，不直接读写 SQLite。
- **反模式 (Violation)**：在 macOS App 的 Swift 代码中 import `SQLite3` 或 `GRDB` 读取 `world.db`。

### #13 无全量后台模拟 (No Full Background Simulation)
- **判定准则**：不运行全量 MMO 式 NPC 自主轮询模拟，采用事件驱动与局部活跃窗口。
- **反模式 (Violation)**：后台常驻死循环每隔 100ms 轮询更新全鲁恩王国上万名 NPC 的坐标与数值。

### #14 世界时钟叙事推进 (Narrative Time Progression)
- **判定准则**：世界时间由叙事与回合事件推进，不直接硬绑定现实物理时钟。

### #15 显式世界线分叉 (Explicit Worldline Branching)
- **判定准则**：重大分岐必须显式登记 Worldline ID，禁止静默状态污染。

---

## 2. 自动化架构适应度检查工具

在提交任何代码前，必须执行：
```bash
rtk python3 scripts/check_architecture_fitness.py
```
该工具通过 AST 静态扫描以下硬指标：
1. `engine/domain/` 零外部 AI/DB 驱动导入；
2. `macos-app/` 零直接 SQLite 依赖；
3. `engine/ai/` 零直接 SQL 写事务；
4. `contracts/schemas/` 全部 28 个 Schema 格式无误。
