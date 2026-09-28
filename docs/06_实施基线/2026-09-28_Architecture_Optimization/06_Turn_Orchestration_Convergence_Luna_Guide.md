# AO-06 回合编排与装配收敛 — Luna 实施方案

> 日期：2026-09-28；原始源码基准：`ca68d485a15bacf46ade5e703abde00598ec5251`。
> 状态：待实施；硬依赖 AO-03、AO-04、AO-05。该包以依赖完成后的实际接口为基准，不反向重建旧工厂。
> 本包为行为保持重构，新增类/文件均为拟新增。没有执行代码、ADR 决策变更或测试。

# 1. 问题结论

交付一个明确的回合用例编排者，集中依赖装配并让模型执行路径与规范说明一致。删除已被替代的内部装配分支，不能只增加一层 wrapper 而保留两套逻辑。

不把接入 AgentScope SDK 作为本次完成条件；其规范地位通过实现状态说明和独立 ADR 提案处理，不未经评审更改既有 ADR 决定。

# 2. 当前实现与根因

| 现有文件 / 符号 | 当前行为 | 目标 |
|---|---|---|
| `engine/application/story_session_facade.py`：`_submit_turn` | 查重、读状态、构造服务、模型、Resolver、commit、表达集于一处 | 保留入口/投影，委托唯一回合编排者 |
| `engine/application/session_orchestrator.py` | 只有 prepare_ai_context 协议，不是完整回合 orchestrator | 明确职责，不再把它当已完成主干 |
| `engine/infrastructure/story_runtime.py` | 构造具体工厂与持久服务 | 唯一 composition root，生命周期统一 |
| `engine/ai/live_turn_workers.py` | 创建 transport 并有独立结构化执行路径 | 依赖注入；以 AO-05 授权执行为唯一 live 入口 |
| `engine/ai/agentscope_adapter.py` | executor seam，无真实 SDK 创建/绑定 | 保留清晰边界，不宣称生产 AgentScope 已接入 |
| `engine/ai/gateway.py` | PreparedTransport 与严格预算 | 复用已有类型，不新增等价 transport interface |

深层原因：接口名、文档中的目标架构和实际 composition root 对“谁编排一轮”表达不一致，后续增加场景/恢复时容易产生多入口。

# 3. 目标行为

- 只有一个 `TurnOrchestrator.execute` 拥有 pre-COMMIT 回合顺序和会话并发边界。
- Facade 负责公开命令规范化、调用入口与公开结果投影，不构造 Resolver/Worker。
- 所有具体 SQLite、模型 transport、场景 adapter、任务 worker 的创建只在基础设施装配层。
- 业务层只依赖 port；Domain 不知道模型/SQLite；AI 不知道提交端口。
- 关闭顺序可靠且一次：停止后续任务领取 → 结束/取消执行 → 关闭模型连接 → 关闭数据库。
- 重构不改变 wire、数据库版本、领域结果、幂等语义、任务状态或缓存预算约束。

# 4. 推荐解决方案

拟新增 `engine/application/turn_orchestrator.py`：

```text
TurnOrchestrator(
  sessions: StorySessionQueryPort,
  intake: DurableTurnIntakePort,
  interpretation: PlayerAdviceInterpretationService,
  actions: AdviceActionIntentService,
  commit: AdviceCommitService,
  scenario: ScenarioPolicyPort,
  context: AO-05 authorized execution ports,
  work: AO-03 durable work registration/query port
)
execute(command, submission_policy) -> CommittedTurnResult
```

这是意图级签名，具体已存在 port 名称按前置包最终产物复用；禁止建立名字不同功能相同的第二接口。`CommittedTurnResult` 为内部结果，只引用 commit receipt 与可信 session，不嵌入未授权 world snapshot。

原 `session_orchestrator.py` 的上下文协议若仍被其他模块引用，作为 read-only context port 保留并更正文档；若确认无调用且已被现有 `GameplayContextCoordinator` port 覆盖，列入本包拟删除清单并在评审时确认，不静默删除公共接口。

保持 `PreparedTransport` 为执行边界。实际 OpenAI-compatible transport 继续由 runtime 创建；已获认证 token counter 时才允许启用通用缓存网关，否则继续 AO-05 的受限授权执行路径。两条路径共享授权入口和明确 capability，不在业务代码内按 provider 名称分叉。

# 5. 详细实施步骤

1. 保存行为特征测试：固定/live、收到重复 input、过期修订、模型失败、commit 后 job 恢复及 legacy/v2 回执。
2. 新增 TurnOrchestrator，将现有 `_submit_turn` 的领域顺序整体搬迁，先保持行为不变；facade 调用它。
3. 在 runtime 构造解释、行动、commit 服务并注入；禁止 orchestrator 内部 new 具体模型或 DB repository。
4. 会话锁只在 orchestrator 维护一份；移除 facade 同步重复锁，防止重入死锁。保留 AO-03 commit 后释放锁语义。
5. 把 provider transport 及 model workers 生命周期纳入 runtime；异常构造时按逆序释放已创建对象，重复 close 幂等。
6. 以 port 明确依赖替代 `object` 与 `type: ignore[attr-defined]` 涉及的业务调用；不全仓机械清理类型。
7. 清理被搬迁后确实冗余的私有构造分支，检查调用方并保持所有公开 handler 名称/shape。
8. 更新相关架构文档的“当前实现”说明，明确 AgentScope SDK 当前状态。若提议改变 ADR-003 的目标，新增拟议 ADR，状态 `PROPOSED`，由架构评审决定；本包不要求先批准 SDK 迁移才能交付重构。

# 6. 关键实现说明

执行顺序保持：

```text
validate command
acquire session admission
lookup durable input
  committed -> return stored result
  cancelled -> reject
  received/new -> freeze or reuse input
scenario + authorized context -> interpret -> action candidate
Resolver + Validators -> domain commit + durable work intents
release admission
return committed result
```

Orchestrator 不负责 TTS、播放或同步等待后续任务。Legacy 同步等待在 handler/兼容适配层调用 AO-03 工作观察口，并在 session lock 外进行。不要将 App 的 method/capability 判断搬入 Domain。

冻结输入、已保存解释与 context binding 是前置包事实源；搬迁不能造成 interpret 调用次数增加。已提交重试也不能调用 scenario 的可变最新配置重算结果。

生命周期测试通过可计数 fake transport 证明 open/close 配对；不能仅凭 `aclose` 方法存在就宣称无泄漏。取消中保留 domain commit 的既有屏蔽/恢复语义，不能为赶快关闭而撤销已受理 SQLite writer 操作。

对 AgentScope 的决定：本包记录“当前生产 transport 主路径”的事实，保留既有目标 ADR。后续 SDK 接入应另交付固定版本 wire-capture、工具边界与运行内存隔离验收；不加无能力收益的 pass-through adapter。

# 7. 测试方案

| 文件 | 验证内容 |
|---|---|
| `engine/tests/test_turn_orchestrator.py`（拟新增） | 顺序、重复输入零模型调用、单锁、候选拒绝、失败无 commit |
| `engine/tests/test_story_session_facade.py` | 保持公开投影与旧方法结果，服务不构造具体基础设施 |
| `engine/tests/test_story_runtime.py` | 唯一装配、配置组合、部分构造失败释放、重复 close |
| AO-03 job / AO-05 authorized execution tests | 重构后所有恢复与授权行为不变 |
| `engine/tests/test_golden_five_turn_application.py` | Golden 完整 oracle 不变 |
| `engine/tests/test_ai_gateway.py` | transport / budget / token counter 契约不放宽 |
| `engine/tests/test_app_engine_session.py` | v1/v2 真实 App-Engine 通路和故障边界保持 |

无需新增 UI 布局测试；无 UI 语义变更。真实模型测试只确认装配没有误改，默认确定性门禁不能冒充该实测。

# 8. 验收标准

工作区根目录；未执行：

```bash
python3 scripts/gate_profile.py check
python3 scripts/gate_profile.py run --profile FULL_P0 --cwd . --log-dir .hacf/logs/ao-06
```

- [ ] 唯一 pre-COMMIT 编排者、唯一会话锁拥有者、唯一 concrete composition root。
- [ ] Facade 无 service/Resolver/transport 的运行时构造。
- [ ] 领域提交、任务、授权、重复请求与旧接口行为特征全部保持。
- [ ] 模型连接、worker、数据库关闭顺序及部分失败释放有测试。
- [ ] 不新增数据库版本、wire 方法或产品功能。
- [ ] AgentScope 实现与目标文档不再混称；无未经批准的 ADR 状态变更。
- [ ] FULL_P0 和所有前置回归通过。

# 9. 风险与注意事项

应最后执行，避免前置包同时搬迁同一方法。每个逻辑块先迁移再删旧私有实现，禁止复制成两条可运行链。对已被外部依赖的 public protocol 不能以“清理”名义删除。

无数据库迁移，代码回退不改变存档；但必须连同本包依赖装配变更整体回退，不能让新 facade 与旧 constructor 混用。

不引入微服务、依赖注入框架、通用 agent 编排 DSL，不迁移模型 SDK、不修改并发上限、不增加缓存层。当前无性能基准，不能宣称重构带来具体延迟收益。

# 10. Luna 执行清单

- [ ] 核对所有前置包已交付，冻结行为矩阵与 SHA。
- [ ] 建立 orchestrator 特征测试并搬迁唯一执行顺序。
- [ ] runtime 集中构造，facade 只保留入口与投影。
- [ ] 单锁、关闭/取消/失败释放和重复请求全部验证。
- [ ] 清理已替代的私有分支，核实 public protocol 使用者。
- [ ] 更新实现状态文档；ADR 目标变更只提交提案。
- [ ] FULL_P0、前置回归与凭单完成，未实测项如实记录。
