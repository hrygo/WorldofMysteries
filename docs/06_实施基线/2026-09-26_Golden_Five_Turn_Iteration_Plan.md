# 下一迭代：Golden 五轮与持久结算

> 规划日期：2026-09-26。
> 本地核实基准：`main@5b08c807bd7281cb37c637c58271f2fffc633d31`；规划前工作区干净。
> 状态：迭代范围建议与任务分解，未启动实施、创建胶囊或执行验收。
> 上位计划：[Persistent World Alpha](Persistent_World_Alpha_Plan_v1.0.md) 的 B 阶段。

## 1. 迭代目标与基线

**用户在 App 完成《不存在的预约》固定五轮，形成 Episode，退出并重开后能阅读原有经历；人物记忆、知识、关系与世界变化保持一致，并能进入后续已授权上下文。**

本地 Git 已包含 #204 合入提交。前一轮交付可信开场、真实首轮 COMMIT、公开投影、App 接线与双进程恢复；详见[前轮实施与证据](2026-09-26_Trusted_Session_App_First_Turn_Luna_Guide.md#11-执行结果回填2026-09-26)。其中测试通过属于历史绑定提交的证据，本次规划没有重跑门禁。

[PROJECT_STATE.json](../PROJECT_STATE.json) 在本计划草拟时仍记录 #204 未合入，且 `critical_path.target_deliverables` 混有已完成的首轮任务。T0 按 GitHub PR 与 main 实际合入记录修正状态、执行基准和剩余工作；M1、M2 或 M5 不因首轮证据而标记完成，历史门禁证据继续绑定原 SHA。

本次为既有 B 阶段的范围规划，不是逐函数实现指南。代码缺口与复用点须在任务切片时核对当前源码；下文目录表示责任边界，不表示其中所有文件都要修改。

## 2.1 当前实现基线（2026-09-27 源码核对）

以下结论来自本地 `main@5b08c807bd7281cb37c637c58271f2fffc633d31` 的源码与测试目录检索：

| 位置 | 当前行为 | 对本轮的直接影响 |
|---|---|---|
| `engine/application/story_session_facade.py`：`StorySessionFacade._validate_new` | 新提交仅接受 `turn=0` 且 `revision=0`；固定模式使用开场 advice / proposer | 第 2–5 轮需要逐轮可信模型输出选择、版本绑定和恢复语义，不能只删 turn 限制 |
| `engine/application/story_turn_commit.py`：`StoryTurnCommitService._validate` | 明确拒绝 `character_deltas`、`relationship_deltas`、`knowledge_candidates`、`world_event_candidates` | Story commit 扩展须有确定性领域校验和权威写入；不得把 overlays 忽略掉 |
| `engine/domain/story_state_reducer.py`：`apply_story_delta` | 只更新 StoryState；`local_state_patches` 被拒绝 | 角色与世界状态变化应由领域 reducers 独立建模，不把无类型 patch 塞入 StoryState |
| `engine/domain/resolver.py` | 确定性 OutcomeResolver 的实际模块路径 | Domain 任务应沿用现有 resolver 与 typed contracts，而非另造 resolver |
| `engine/infrastructure/migrations/001_world.sql`、`002_world_story_sessions.sql`、`004_world_narrative_blocks.sql`、`008_world_turn_intake.sql`–`010_world_story_bootstrap.sql` | 现有权威表覆盖 commit/event/outbox、story session/delta/turn、NarrativeBlock、intake/advice、bootstrap；检索未发现 Episode、角色记忆/知识及关系投影的 world 持久化表 | T3 要先按现有 schema 与 aggregate 边界设计迁移及 repositories；migration 必须单独授予 AGT-DATA 精确路径 |
| `engine/tests/test_golden_turn1_durable.py` | 覆盖真实首轮、重开与幂等 | 只能作为首轮回归；不能作为五轮或 Finalization 通过证据 |
| `fixtures/golden_001/turns/*_expected.json`、`fixtures/golden_001/expected_episode.json` 与 `docs/07_工程启动/golden_001_runtime/expected_episode.json` | 提供五轮事实和 Episode 期望；两份 Episode JSON 当前内容相同 | 验收必须独立读取期望并比较真实提交结果；先确定唯一测试读取路径，避免维护第二份 Canon 内容事实 |
| `docs/07_工程启动/golden_001_runtime/README.md`、`assertions.yaml`、`mock/` | 已定义五轮 Mock 边界、G001–G012、Finalization、Restart 与八个终止点 | T1 补齐可执行覆盖矩阵，不重写既有规格，不把 fixture 存在或脚手架测试当作回归通过 |

代码图谱 MCP 在本轮未能通过工具发现取得，因此本表是定向源码核对，不声称穷尽调用链。实现每个领域接口前仍须补读真实调用方与持久化边界。

## 2. 范围与关键决策

| 纳入本轮 | 完成边界 |
|---|---|
| Golden 所需跨领域结算 | Story、World、Character、Knowledge、Memory、Relationship 与事件写回的必要子集；不泛化成全部领域功能 |
| 固定五轮编排 | 沿用真实 intake、Proposal、Resolver、Validator、事务与恢复路径；开放第 2–5 轮并保留第 1 轮证据 |
| COMMIT 后的表达 | 固定 BeatPlan / NarrativeBlock 经合法路径持久化；失败或重生成不改已提交事实 |
| Episode Finalization | Episode、记忆、知识、关系证据和 WorldEvent 原子结算；重复触发不重复写入 |
| 重启、回访与投影重建 | 历史 Episode / Narrative 可读；记忆可在授权后召回；测试存档的 retrieval 投影可重建 |
| App 最小完整路径 | 五轮提交、pending 恢复、结算状态、历史阅读与退出返回；明确标识固定工程模式 |
| 真实运行验收 | 独立 Engine 与生产 Swift 链路、八个故障点、绑定最终 SHA 的 GUI 观察记录 |

本轮不纳入：真实 LLM 质量、自由文本场景、真实 TTS 播放、新美术批次、任意场景生成、多世界线功能、公开发行或全量 NPC 模拟。G010 的音频重生成不改事实约束仍需验证，真实音频质量另行验收。

选择完整 B 阶段作为迭代边界，并设两个中间检查点。仅把首轮限制改为五轮，会遗漏世界记忆和结算；同时接真实模型与语音，会使确定性故障更难定位。

固定输出边界遵循 [Golden Runtime](../07_工程启动/golden_001_runtime/README.md)：Advice Interpreter、Character Reasoner、Story Director、Narrative Compiler 的模型输出可固定，其余运行链必须真实。`expected` 仅供断言，不能作为运行结果来源或随包执行资料。

## 3. 任务分解与依赖

以下为按依赖拟定的任务 ID。`B-SCOPE-CONTRACT` 已按 AGT-ARB 胶囊在隔离分支 `codex/b-scope-contract` 开始；其余任务须在前置接口与实际目标基线明确后再 pack。角色表示职责，不表示已启动代理。

| 顺序 / 任务 | 责任与主要范围 | 前置 | 可独立评审的交付物 |
|---|---|---|---|
| T0 `B-SCOPE-CONTRACT` | AGT-ARB：`docs/`、必要的 `contracts/` | 当前主线 | 逐轮事实与写入归属矩阵、revision/CAS 语义、Finalization 与回放契约、旧会话版本策略；纠正状态文件 |
| T1 `B-GOLDEN-ASSERTIONS` | AGT-QA：`fixtures/`、`engine/tests/` | T0 | G001–G012、五轮 expected、Episode expected 与八个故障点的追踪矩阵及测试入口；未实现部分明确失败，不以 skip 计为通过 |
| T2 `B-DOMAIN-SETTLEMENT` | AGT-DOM：`engine/domain/` 与对应测试 | T0、T1 的断言定义 | Golden 所需纯领域 reducer / validator；逐轮合法 delta、知识来源及角色自主性约束；拒绝非法 overlay |
| T3 `B-DURABLE-SETTLEMENT` | AGT-DATA：`engine/infrastructure/` 与对应测试；迁移精确扩权 | T0、T2 的接口 | 领域写回、幂等、CAS、事务事件与 Outbox；迁移保留旧存档；故障无部分写入 |
| T4 `B-FIVE-TURN-APPLICATION` | AGT-AI：`engine/application/`、固定模型适配；runtime 接线由 AGT-DATA 承担 | T2、T3 | 第 1–5 轮真实编排、COMMIT 后表达、Finalization 用例；输入重放与 pending 续跑保持现有语义 |
| T5 `B-MEMORY-RETURN` | AGT-DATA：权威读取与投影；AGT-AI：授权上下文组装，分开写域 | T3、T4 | 重启后的 Episode、Memory、Knowledge、Relationship 读取；Outbox 重放及 retrieval 重建；授权回访证据 |
| T6 `B-APP-FIVE-TURN` | AGT-MAC：App 与 Swift 测试；内容构建由 AGT-ARB 单独负责 | T0 可准备 DTO；联合验证依赖 T4、T5 | 连续五轮、结算与历史回放 UI；journal 与旧回调隔离；随包五轮内容不依赖源码目录 |
| T7 `B-GOLDEN-ACCEPTANCE` | AGT-QA：跨进程与故障测试；AGT-ARB：证据与状态收口 | T1–T6 | 同一最终源码版本的五轮、结算、重启、重建、GUI 与适用门禁证据 |

执行顺序：`T0 → T1/T2 → T3 → T4 → T5 → T6 联调 → T7`。T1 的断言准备可与 T2 配合推进；T6 可在契约冻结后准备客户端。实际并行需独立胶囊、工作区和明确文件 ownership，共用文件只设一个写入负责人。

任务开始前按当前实现缩减工作量：已有数据库管理、Outbox、Narrative repository、Context Compiler、App journal 等实现优先复用，不能因任务名称而另建第二套机制。

## 4. 三个检查点

### A：五轮事实成立

- 固定五轮运行真实裁决与事务，Story revision 依次为 1–5。
- 每轮与独立 expected 对比；第 4 轮体现 reinterpret，第 5 轮 closure 不增加重大冲突。
- Secret 04 始终 hidden；地下室声响不自动推导为有人；玩家猜测不成为事实。
- 同 key 重试不重复提交；同 key 改正文拒绝；不同 key 并发由 revision/CAS 裁决。
- World / Character 的领域 revision 与 SQLite store revision 分别校验，不能混为一个计数器。

### B：经历留下持久结果

- Episode ending 为 `partial_truth`，未解之谜保留。
- Episode、人物 episode memory、knowledge、关系证据与 world event 的 Finalization 全部成功或全部回滚。
- 公共观察不暴露隐藏组织；不产生规范未要求的重大 emotional memory。
- 关闭重开后读取原有记录；Story Book 不重新调用 Resolver 或重新生成历史文本。
- 删除隔离测试存档的 retrieval 投影后，从权威源幂等重建；授权结果一致。
- Context Compiler 能召回已授权 Episode Memory，同时拒绝未知隐藏事实。

### C：App 与故障恢复成立

- App 可完成开始、五轮提交、结算、退出和返回，保留未知结果与 pending 的明确状态。
- 第 5 轮后明确结束固定验证；不默许第 6 轮或任意文本输入。
- 逐项覆盖八个 Engine 终止检查点：
  1. after advice；
  2. after action intent；
  3. after resolver before commit；
  4. immediately after commit；
  5. after beat plan；
  6. after narrative；
  7. during finalization transaction；
  8. after finalization commit before projection。
- 每个故障测试同时核对进程恢复和磁盘事实，证明零重复提交、零部分结算；不能仅断言“无异常”。
- Narrative / audio 重生成不得反向更改 StoryState；G010 使用现有可控音频链验证事实不变，不冒充真实 TTS 验收。
- GUI 观察记录与跨进程结果绑定同一最终 SHA；观察不能由源码检查或截图单独替代。

## 5. 兼容与风险处置

1. **旧首轮存档**：T0 必须定义旧 bootstrap / policy version 的处理。继续旧版本只读回放；需要新能力时显式新开工程会话，或提供经验证的迁移。禁止换用新版模板重新解释已提交输入，禁止静默清空旧存档。
2. **结算事务**：跨领域原子性在 `world.db` 内实现；`retrieval.db` 由 Outbox 异步追赶。不能把跨库同步写成功当作原子事务。
3. **表达失败**：区分“事实已保存”和“表达待完成”；后续表达重试复用持久事实，不重复裁决或抽样。
4. **知识泄漏**：IPC、错误、日志、历史回放与检索都纳入检查；UI 继续使用显式 allowlist。
5. **包更新与恢复**：冻结内容版本、规则与输入身份；内容升级不能覆盖旧会话的恢复依据。
6. **范围失控**：优先交付 Golden 必需的领域操作，其他 World/Character 能力继续留在各自里程碑，不宣称“全部领域功能完成”。

## 6. 验收与实施交接

总完成条件：G001–G012、五个 committed-state expected、Episode expected、重启、幂等、八个故障点、投影重建和 App 观察全部有证据，且未验证项单独保留。

- 按 `pack → start → 实施并提交 → verify → 凭单独立提交` 执行；目标为实际最新 `origin/main`，不复用旧迭代凭单。
- contracts、迁移、内容构建或门禁变更按精确路径登记 AGT-ARB 权限。
- 验收执行权威来自 `.hacf/gates/`，本计划不另建测试命令清单。先解析适用档案；组合交付执行相应完整门禁并立凭单。
- 若既有档案未覆盖新增 Golden 测试，需受保护流程更新档案与 registry；不能只修改 CI 步骤标题宣告通过。
- 记录 SHA、平台、会话与回合 identity、领域/store revisions、故障点、恢复结果和日志位置。
- 分别核对 M1、M2、M3、M5 的退出条件后再更新状态；部分能力通过不自动完成整个里程碑。
- 远端提交、合并与发行不包含在本次规划动作中。

建议首先执行 T0 和 T1，把领域写入矩阵、旧存档策略与五轮验收断言落实，再进入业务实现。完成 A 检查点即可演示五轮事实链，完成 B 可演示“世界与人物记得”，全部完成 C 后才宣布本迭代交付。
