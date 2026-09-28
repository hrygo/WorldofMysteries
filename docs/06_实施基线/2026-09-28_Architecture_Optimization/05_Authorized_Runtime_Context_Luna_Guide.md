# AO-05 动态授权上下文接线 — Luna 实施方案

> 日期：2026-09-28；原始源码基准：`ca68d485a15bacf46ade5e703abde00598ec5251`。
> 状态：待实施；硬依赖 AO-04 场景端口。推荐在 AO-03 后实施，冻结 post-COMMIT job 来源已具备。
> 本轮不声称已发现知识泄漏；问题是 live 主路径尚未消费完整动态授权机制。新增模块与表均为拟新增，验收未执行。

# 1. 问题结论

交付“真实解释、行动提案与叙事调用由服务端当前快照和授权证据驱动”。逐步替换仅由 bootstrap 生成的静态 `_SceneBrief`，让已提交知识和关系变化能够进入下一轮，并阻止未授权、跨世界线或过期证据进入调用。

不建设全量 RAG、向量库或 AgentScope Agent；授权读链本身是独立可验收交付。

# 2. 当前实现与根因

| 现有路径 / 符号 | 已有能力/缺口 | 处置 |
|---|---|---|
| `engine/ai/live_turn_workers.py`：`_SceneBrief` / `_StructuredWorker` | live prompt 主要来自 bootstrap 场景摘要与原话 | 改为消费类型化授权 PromptPlan |
| `engine/application/gameplay_context.py`：`GameplayContextCoordinator` | eligibility 在 facet 检索前，统一 snapshot 与 authorize | 复用并提供实际读端口 |
| `engine/application/context_compiler.py`：`CacheAwareContextCompiler` | 检查 grants、consumer、时间、修订、世界线 | 原样保留，不绕过 |
| `engine/application/context_plan.py`：`Evidence` / `AuthorizationView` | 包含来源、可见性和完整内容指纹 | 唯一内部 IR |
| `engine/ai/gameplay_cache.py` / `gateway.py` | 通用网关要求真实/认证上界 token counter | 不用字符数假装 token 数强行接入 |
| `engine/ai/openai_compatible.py` | 明确不承担授权或伪造 token 计数 | 保留传输职责 |
| `engine/infrastructure/story_session_repository.py` | 保存逐 turn character/relationship/knowledge 变更 | 用于当前场景快照物化，不把候选日志直接当已知事实 |
| `engine/application/episode_memory_recall.py` | 已有授权记忆召回服务接口 | 复用其约束，先提供有限已提交 Episode 读取 |

根因是组件存在但运行装配未贯通。把更多数据库字段直接拼进 prompt 会扩大边界风险，不构成授权上下文实现。

# 3. 目标行为

- 一次模型调用的世界、角色、故事、知识、记忆证据来自同一不可变读快照。
- Domain-owned 授权服务先签发 eligibility，读取端不能自行给所有结果授权。
- 角色提案只能见角色已知证据；玩家叙事只见可披露的已提交结果。
- 新知识经过提交后能进入下一轮；未提交候选、隐藏事实和无关角色记忆被排除。
- 模型 await 后重新验证修订/授权；失效则拒绝候选，保持输入为待处理，不提交旧推理。
- 恢复旧 turn 的叙事使用其提交时绑定来源；不得把最新会话秘密补进历史叙述。

# 4. 推荐解决方案

拟新增：

- `engine/infrastructure/gameplay_context_repository.py`：在一次 SQLite read transaction 中物化所需可信快照。
- `engine/application/runtime_context_ports.py`：适配既有 snapshot/facet/profile ports。
- `engine/domain/context_visibility.py`：纯可见性策略，输入可信事实与调用身份，输出 eligible source IDs/授权结果；不 import DB 或 AI。
- `engine/ai/authorized_live_execution.py`：复用 coordinator、compiler 与 renderer，执行已有结构化调用。
- `engine/infrastructure/turn_context_repository.py`：保存最小上下文绑定。
- 下一空闲 `NNN_world_turn_context_bindings.sql`：拟新增 `turn_context_bindings`。

本阶段默认继续 `OpenAICompatibleChatTransport` 执行，但强制先 compile 已授权 PromptPlan，并在模型返回后重新 authorize。使用现有 renderer 生成受控消息，再经已有 wire 构造发送；保留有界 output、timeout、最大回复字节和一次 schema repair。不得同时走直接 `_SceneBrief` 拼接分支。

不接 `GameplayAIGateway` 的理由是当前生产 provider 尚未证明满足其 token counter 契约。保留它的严格契约和测试，不降低为字符估算。未来取得真实 counter 后可替换执行端，不重写授权层。

# 5. 详细实施步骤

1. 在 `test_gameplay_context.py` 与拟新增 live 集成测试建立知识变化/隐藏证据/过期修订用例。
2. repository 使用同一只读连接事务读取 world_meta、session/bootstrap、对应 committed deltas、已提交领域变更和 Episode memory；一次返回不可变 snapshot，禁止各 facet 分别读最新值。
3. 物化当前场景角色状态：从可信 bootstrap 起按 committed revision 顺序应用已有纯 reducer 与经验证的持久变更；没有确定性 materializer 的字段不注入，不能推断出“角色已知”。
4. 可见性策略检查 owner/session/subject/worldline、提交 revision、可用 tick 与 disclosure；eligibility 在 candidate collection 前产生，authorize 对完整 fingerprint 再确认。
5. 按当前实际三类调用建立最小 WorkerProfile 与 Gameplay recipe 映射：advice_interpreter、character_reasoner、narrative_compiler。其他 mode 不接入。
6. LiveAdviceInterpreter / LiveActionIntentProposer 改为请求授权执行服务，不读取任意 bootstrap 字段拼 prompt；scenario 仍提供允许动作和 DomainValidationContext。
7. 叙事 source 绑定已提交 turn 的 delta 与 public disclosure，不将玩家原话中的主张提升为已提交事实。
8. 解释持久化与 context binding 原子关联；提案采用该输入冻结上下文，同样验证 freshness。更新 DB authorizer 只允许专用绑定表，AI 不获得 write port。
9. Runtime 注入 ports、profile、可见性策略和 transport；用受控模型捕获真实发出的 request body 验证边界。

# 6. 关键实现说明

## 6.1 修订与来源语义

`ContextSnapshot.world_revision` 使用当前存储 `world_meta.revision`，不能用 bootstrap 的 Domain world base revision 103 替代。内容源自己的 revision 单独放 Evidence.source_revision；两种 revision 不混作 CAS。

SQLite 读事务只覆盖物化读取，完成后关闭；模型调用和外部 await 不持有该读事务。facet ports 消费同一份不可变物化快照，再进行授权筛选；不借并发 `load` 为同一次调用打开多个“最新”连接。

当前 bounded scene 的 world_tick 由场景可信时钟 adapter 给出。可使用本场景已提交 turn 序数作为**场景内可用序**，且所有该源 evidence 采用同一序；不可将该序宣称为全局世界时间，跨场景/世界线源必须提供明确转换，否则拒绝加入。运行时间戳不能充当世界 tick。

祖先世界线只按已有明确 lineage 和分叉 revision 限制放行。没有可验证 lineage 时不返回祖先证据；不在本包创建世界线。

最小 binding 表：

```text
turn_id, stage, context_revision PRIMARY KEY
input_turn_id, source_store_revision, source_story_revision
policy_revision, content_digest, lineage_digest
manifest_json: ordered [{source_id, source_revision, fingerprint}]
manifest_digest
```

stage 为 interpretation|action|narrative。`context_revision` 为由服务端 canonical manifest 推导的摘要，不由模型输入。manifest 内不存原始证据正文和凭据。解释记录引用对应 binding；在现有解释写事务中保存绑定和结果，失败整体回滚。ActionIntent 和最终 commit 验证引用同一授权来源集合。

不自动用新上下文覆盖已有解释：若其绑定过期，报告 `revision_conflict` / `context_stale` 内部原因并通过现有公开错误映射；保留待处理输入。取消/重新提交走现有显式 turn control 的授权路径，不为求继续偷偷改 frozen revision。

## 6.2 语义边界

- `task_json` 中玩家原话是未信任意图，不属于 grants，也不是已提交 Evidence。
- 当前角色与玩家披露是两种 consumer scope；叙事者不可因为是“旁白”就获得全部 Canon。
- `eligibility` 票据由应用持有的 Domain 策略签发，不由模型/IPC 创建，不按“对象里已有字段”授予权限。
- repair 使用同一个授权快照；过期时不在 repair 中偷偷扩容或切快照。
- `PromptRenderer` 所需 secret 由 runtime 内存生成/注入，不写库、日志或方案示例；不引入新的外部凭据管理系统。
- 上下文超界先确定性限量/拒绝；没有确切 token 能力不报告精确 token 预算保证。

# 7. 测试方案

| 文件 | 用例 |
|---|---|
| `engine/tests/test_gameplay_context.py` | eligibility 先于 load、同 snapshot、grants 不能扩大 |
| `engine/tests/test_context_compiler.py` | 原跨世界线/隐藏/未来 evidence 拒绝保持 |
| `engine/tests/test_runtime_context_repository.py`（拟新增） | 并发写期间读快照一致；commit 前后知识可见性变化 |
| `engine/tests/test_authorized_live_execution.py`（拟新增） | 捕获实际 request body；未知角色证据不出现；repair 同快照 |
| `engine/tests/test_turn_context_repository.py`（拟新增） | 解释与 binding 原子写、冲突拒绝、writer 权限 |
| `engine/tests/test_story_runtime.py` | live 必经授权服务，模拟模型 await 时推进 revision，旧候选不能提交 |
| `engine/tests/test_ai_gateway.py` | 不放宽 token counter 的严格要求 |

关键例：角色 A 学到 proposition P 后下一轮 request 含 P；角色 B 同时同世界但未知 P 时不含 P；仅有未提交 knowledge candidate 时两者都不能凭候选获知 P。

# 8. 验收标准

工作区根目录；未执行：

```bash
python3 scripts/gate_profile.py check
python3 scripts/gate_profile.py run --profile FULL_P0 --cwd . --log-dir .hacf/logs/ao-05
```

- [ ] 已提交的新知识影响下一轮 live request；隐藏、其他角色及未提交候选不进入。
- [ ] 请求前后修订失效均阻止旧候选提交，不改变 frozen identity。
- [ ] 单次 context 的所有 facet 来自同一 SQLite 快照。
- [ ] 旧 turn 叙事恢复不读取未来事实。
- [ ] 解释与 binding 同事务，权限测试通过，迁移保留旧记录。
- [ ] 不报告伪造 token 精确值；没有为接网关放宽其契约。
- [ ] FULL_P0 和 wire-capture 用例通过；真实模型质量另记，不拿 mock 代替。

# 9. 风险与注意事项

需 `contracts` 以外的内部模型和 world migration 评审；若最终确需公开新错误码，则同步 Schema/Swift，不能只抛字符串。旧解释缺 binding 时只读恢复既有 committed 结果；pending 旧解释不得自动当已授权，以 `legacy_context_unbound` 阻止执行并提供明确处理信息。

回退遵循迁移备份与前向修复原则；不删除绑定表，不用新模型重解释已提交输入。此包复用现有 Episode recall 能力，但不构建 FTS/vector，不增加全世界后台模拟。

授权正确性依赖明确的状态 materializer，若某类领域候选尚无可证明应用语义，第一版只支持有确定语义的 evidence，不能把缺口用 prompt 补齐；测试必须至少覆盖既有 Golden 已提交知识变更。

# 10. Luna 执行清单

- [ ] AO-04 接口已确定，核对内容/修订和现有知识持久字段。
- [ ] 建立授权请求捕获回归，明确读快照与可见性策略。
- [ ] 实现 repository、materializer、ports 与 Domain 策略。
- [ ] live 三类调用接入 compile/reauthorize，移除主路径直接拼接。
- [ ] binding migration、原子写和旧 pending 处理完成。
- [ ] 验证跨角色、跨世界线、并发修订及历史叙事隔离。
- [ ] 完成 FULL_P0、凭单与未覆盖 evidence/真实模型质量说明。
