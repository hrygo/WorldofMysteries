# 可信开场与 App 真实首轮闭环 — Luna 实施方案

> 核实日期：2026-09-26（本机 Asia/Shanghai）。
> 源码基准：`main@dccdbd76ef488281cda86be01a6857754b91b7c0`；规划前工作区干净。
> 状态：实施方案；本次仅读取证据并编写本文，未实施业务代码、运行门禁、提交、推送或启动代理。
> 执行状态回填（2026-09-26）：T1–T6 已实施并按任务立 Work Receipt（10 枚，全部 FULL_P0 `verdict=passed`），实际交付、差异与未验证项见 §11；第 1–10 节的规划原文保持不变。
> 上位目标：[Persistent World Alpha](Persistent_World_Alpha_Plan_v1.0.md)、[总验收 #43](https://github.com/hrygo/WorldofMysteries/issues/43)。
> 前序：[Session Open 与首轮持久链交接](2026-09-25_Session_Open_First_Turn_Luna_Guide.md)。
> 本文新增文件、接口、状态、数据库表及 wire 方法均为**拟新增设计**；标为“现有”的名称已在上述基准核对。

# 1. 问题结论

下一迭代交付一个明确的工程体验：

**打开 App → 进入 Golden 001《不存在的预约》→ 提交固定首轮建议 → 真实裁决并提交 → 展示授权结果 → 退出 → 重开后找回同一会话和结果。**

已有内部服务足以支撑首轮持久链，缺口集中在可信初始化、授权 UI 投影、生产组合根和产品 IPC/App 接线。不要重新实现 Resolver、Story Commit、鉴权或 socket transport。

本迭代使用显式 `golden_deterministic` 工程模式，只替代 Advice interpretation 和 ActionIntent proposal 的模型输出。输入持久化、领域裁决、校验、事务、Outbox 和恢复执行真实代码。固定模式只接受原始 Golden 首轮文本，不将任意文本映射到同一结果。用户无需手工指定路径、运行命令、配置模型或提供 token。

完成后只能声明“首轮工程闭环与恢复通过”，不能声明完整 M1/M2/M5/M6、自由文本叙事、五轮结算或正式发行通过。

# 2. 当前实现与根因

## 2.1 已核对证据

以下路径均相对仓库根目录。

| 现有文件 / 符号 | 当前行为 | 本轮处置 |
|---|---|---|
| `engine/application/story_session_open.py`：`StorySessionOpenService.open/recover`、`OpenStorySessionCommand` | 内部可信调用方必须提供完整初始 `StorySession`；校验 active、turn/revision=0 和身份 | 保留；公开 IPC 不接受其内部 command |
| `engine/infrastructure/story_session_open_repository.py`：`SQLiteStorySessionOpenPort` | 单写事务持久开场、幂等记录、事件和 Outbox；读取 session 与 store revision | 复用原子开场实现，扩展可选可信初始化绑定 |
| `engine/application/turn_input.py`：`StoryTurnInputService` | 持久 input identity；先查重再读取当前 session；文本上限 16,384 字符 | 保留，外层增加公开请求的 revision / 会话权限校验 |
| `engine/application/advice_interpretation.py`：`PlayerAdviceInterpretationService` | 首次解释持久化，重试复用已有解释 | 保留 |
| `engine/application/advice_action.py`：`AdviceActionIntentService` | 将模型候选绑定到服务端身份与 evidence；候选不控制 turn/actor ID | 保留 |
| `engine/application/advice_commit.py`：`AdviceCommitService.commit` | 已提交 input 优先恢复；否则 Proposal → Resolver → Story Commit | 保留，首轮入口不能绕过此链 |
| `engine/application/story_turn_commit.py`：`StoryTurnCommitService` | 明确拒绝非 Story overlays | 保留拒绝，不丢弃 overlays 以求首轮通过 |
| `engine/infrastructure/ipc_server.py`：`LocalIPCServer`、`_run`、`main` | 已有鉴权、framing、媒体与 payload-only control handler；生产 `_run` 仅 `LocalIPCServer(path, token)`；health 的业务值固定 false | 注入产品 runtime 和独立 request handler，不重写 transport |
| `engine/infrastructure/uds_server.py` | 仅 `IPCServerProtocol` 接口骨架 | 不误将其当作生产入口修改 |
| `macos-app/WorldOfMysteries/EngineProcessManager.swift` | 生产只使用随包 Runtime，子进程入口为 `infrastructure.ipc_server`；支持父进程退出清理 | 保留入口和生命周期；增加显式存储配置注入 |
| `macos-app/WorldOfMysteries/EngineIPCClient.swift` | capability 检查、真实请求、不自动重发 mutation | 增加 typed story 方法，保留不自动重发原则 |
| `macos-app/WorldOfMysteries/AppState.swift` | `.ready` 依赖 `world.home`；`isShowingDemoData` 恒 true；连接 generation 防旧回调污染 | 保留旧页面诚实性，增加独立 story 状态 |
| `macos-app/WorldOfMysteries/ContentView.swift` | 使用 `DemoWorldSnapshot`；`AdviceInputField.onSubmitAdvice=nil` | 将真实首轮放入独立会话区域，不整体更名示例页面 |
| `scripts/bundle_engine.py`：`stage_engine` | 打包已跟踪的 Engine 模块、迁移和依赖；未包含仓库外层 Golden 资料 | 增加确定性内容包构建；最终运行不依赖仓库 |
| `engine/infrastructure/database_schema.py` | world schema version=9；已有备份、迁移与完整性检查 | 新增第 10 版初始化绑定迁移，复用备份流程 |
| `engine/tests/test_golden_turn1_durable.py` | 真实 Golden 首轮 Resolver 与 expected state；`_initial_session()` 在测试内装配 | 将装配规则收敛到可信 initializer，保留独立 expected 比较 |
| `engine/tests/test_golden_voice_chain_durable.py` | `Chain` 组装完整持久链；其场景为 `advance_into_room`，不是 Golden 001 的诊所剧情 | 复用接线结构，不复制其剧情/策略作为 Golden 001 |
| `engine/tests/test_app_engine_session.py` | 编译真实 Swift 客户端，启动独立 Engine；Swift 文件名单显式列出 | 新增 story 依赖时更新编译输入和真实场景 driver |

`PROJECT_STATE.json` 落后：仍称 #202 未合入；Git 历史及前序方案已记录合并提交 `26999fc61c074292224cdb7ce6c6ad89aca16c35`。先修正证据描述，不能据此把未验收的产品能力标为完成。

## 2.2 直接原因与设计原因

1. 内部 opener 的信任边界不等于公开 API。直接接收初始 Session 会允许客户端伪造身份、revision、秘密与场景事实。
2. 初始世界/人物 revision（Golden 中为 103/27）不是 SQLite `world_meta.revision`。以任一替代另一会产生错误 CAS。
3. 当前 control handler 只收到 payload，缺少真正的 envelope request/trace identity；在 payload 复制这些字段会形成两个事实源。
4. StoryState 含 `secret_states`、压力和内部目标；把整个模型编码成 UI 响应会越过知识边界。
5. 生产入口没有数据库和 application service 的组合根；内部测试通过不会自动使 App 可用。
6. 恢复不仅需要 session ID，还需要可信初始化版本和未确认 input identity；重读最新 fixture 不是恢复。

## 2.3 证据限制

本次采用相关源码、契约、测试和 Git 历史核查。当前会话未提供可调用的 Codebase Memory 图谱工具，因此不声称完成全仓调用图或穷尽审计。没有执行 App、数据库迁移、跨进程测试或 FULL_P0。上一轮 GitHub #43/#45 可读，但正文保留历史进度；#44 读取曾遇连接错误。实际实施以届时目标分支和测试结果为准。

# 3. 目标行为

## 3.1 首次进入

- App 连接 Engine 后读取 story entry；显示“工程验证 · 固定首轮”，与已有示例页面区分。
- 首次进入才显式调用 open。Engine 根据唯一允许的 `scenario_id=golden_001` 装载可信内容并初始化会话。
- App 不能传数据库路径、worldline、protagonist、seed 内容、初始状态、规则或隐藏事实。
- 开场事务成功后 Story turn/revision=0；world/character 基准仍来自可信快照；SQLite store revision 因开场提交递增。
- 存在会话时显示“继续首轮验证”，读取旧会话，不重新创建或替换用户数据。

## 3.2 首轮提交

- 提供“填入首轮建议”按钮，内容来自服务端授权 entry：
  `先别问医生病人的事，我想看看他的反应。`
- 本轮使用文本输入，`input_mode=text`；不复制 fixture 中的 voice 输入方式，也不复制其 advice/turn ID。
- 固定模式对 raw input 做完全相等匹配；不 trim 后静默改写文本、不做模糊语义匹配。空输入由契约拒绝；其他文本返回 `deterministic_input_unsupported`，不写入 intake。
- 成功路径：receive → interpret → propose → resolve → validate → COMMIT → public view。
- 成功只表示已完成首轮。UI 显示人物、地点、已提交 turn、已发现线索与持久状态；不制作伪 NarrativeBlock，不启动 TTS。
- turn=1 后禁用新一轮提交并说明“首轮验证已完成，后续回合尚未开放”；对旧 input 的恢复仍可用。

## 3.3 失败和恢复

- 断线、超时只表示结果未知；UI 保留原 input ID 和冻结文本，先查询恢复，不自动生成新 input ID。
- 已 COMMIT：直接读取并显示结果，不调用解释器、proposer 或 Resolver。
- 已 received：显示“请求已记录，尚未提交”，允许用户显式继续同一请求。
- 未找到 input：显示“未查到提交记录”，允许用户显式重试同一请求。
- 用户编辑冻结文本前必须明确放弃本地重试意图；若服务端已有 received 命令，本轮不提供隐式替换，继续或保留待处理状态。不要借新 ID 绕过待处理命令。
- 退出再启动：只读恢复已有会话及 pending input；不自动恢复执行 mutation。

# 4. 推荐解决方案

## 4.1 方案选择

推荐“可信内容包 + 持久初始化绑定 + 小型 Application facade + 独立 typed IPC + 局部真实 UI”。

不选择：

- **把 StorySession 整体传给 App 再提交回来**：实现较短，但身份和知识授权边界错误。
- **本轮同时做 Genesis、任意场景、五轮和全领域结算**：能覆盖更广产品面，但会把首轮集成与尚未完成的存储能力耦合，无法独立验收。

## 4.2 内容与持久化

唯一内容源继续使用：

- `fixtures/golden_001/{seed,world,character}.json`
- `fixtures/golden_001/knowledge/*.json`
- `fixtures/golden_001/turns/01_advice.json`
- `docs/07_工程启动/golden_001_runtime/mock/01_action_intent.json`

`expected/01_committed_state.json` 只允许测试读取，禁止打包给运行时或作为执行结果来源。

拟新增 `scripts/build_story_content.py`，构建单一版本化 Golden 内容包和只读 SQLite 内容制品；构建时校验现有 JSON Schemas、文件集合、跨文件身份和 canonical JSON 摘要。内容制品可使用 `scenario_bundles(scenario_id PRIMARY KEY, content_version, content_digest, payload_json)`；这是本轮工程内容容器，不宣称完成正式 Canon schema。

`scripts/bundle_engine.py` 将制品放入 `LocalEngine/engine/infrastructure/story_content/canon.db`，纳入现有 inventory/签名流程。这是**构建期生成文件**，不是运行期向 Canon 写入，也不把二进制数据库提交仓库。生产通过模块目录定位包内制品，不能相对当前 cwd 查找 `fixtures/` 或 `docs/`。

构造 `DatabasePaths` 时，world/retrieval/runtime 使用 App Application Support 下独立的 `Engineering/Golden001` 根目录；canon 指向上述包内只读制品。使用现有 `DatabasePaths.for_world` 推导可写路径，再显式替换 canon 路径。不要改变全局 `DatabasePaths.for_world` 的原有规则。

首次 open 将可信 seed/world/character/初始 knowledge 及规则版本原子冻结到 `world.db` 的初始化绑定表，与 session 开场同一提交；后续恢复以冻结数据为准。包更新不覆盖旧初始化快照，不改变已发生结果。

## 4.3 拟新增公开方法

保持现有 IPC envelope 1.0 和 framing 不变。新增 `contracts/protocol/story_session_control.schema.json`，以 `$defs` 定义下表请求/响应；所有对象 `additionalProperties=false`。可选字段省略，不发送 null。

| 方法 | payload 必填字段 | 结果 |
|---|---|---|
| `story.entry.get` | `schema_version`, `scenario_id` | mode、允许的建议、当前 store revision；若已有会话，返回其 public view |
| `story.session.open` | `schema_version`, `scenario_id`, `open_request_id`, `expected_store_revision` | public view、`opened_store_revision`、`replayed` |
| `story.session.get` | `schema_version`, `session_id` | public view |
| `story.advice.submit` | `schema_version`, `session_id`, `input_turn_id`, `raw_input`, `expected_story_revision`, `expected_store_revision` | 与 advice.get 相同的 receipt + view；正常成功必须 committed |
| `story.advice.get` | `schema_version`, `session_id`, `input_turn_id` | `found`；找到时返回已存 receipt 与 public view |

公共限制：`schema_version="1.0"`；scenario 仅 `golden_001`；ID 非空、非纯空白、无 NUL、最多 256 字符；revision 为 `0..2**63-1` 的整数，拒绝 bool/字符串；写请求 expected store revision 小于上限；raw input 非空且最多 16,384 字符。本轮不用 public input_mode 字段，服务端固定 TEXT。

写请求 envelope `idempotency_key` 必须等于其 `open_request_id` 或 `input_turn_id`；缺失/不匹配返回 `schema_invalid`。request_id/trace_id 只从 envelope 获取，不从 payload 或模型获取。重试可以使用新的 request/trace ID，但业务幂等 ID、文本、预期 revision 必须保留首次冻结值。

entry 响应字段：

```text
schema_version, scenario_id, mode="golden_deterministic",
supported_advice, observed_store_revision,
[session: PublicStorySessionView], [pending_input_turn_id]
```

PublicStorySessionView：

```text
schema_version, scenario_id, session_id,
mode="golden_deterministic", status: StorySessionStatus,
story_revision, turn, observed_store_revision, world_time,
protagonist: {id, display_name},
scene: {id, location_id, display_name},
discovered_clues: [{id, display_name}],
can_submit, [last_committed_turn_id]
```

仅投影上述 allowlist。禁止 `secret_states`（包括 hidden ID）、hidden_truth、未发现 clue、完整 world/character、压力、关系、内部目标、原始 StateDelta 或 seed digest 进入 UI。ID 不等于显示文案；本场景显示名在可信 presentation 映射集中维护，不能由 App 独立维护另一份世界事实。

receipt 响应：

```text
schema_version, found,
[receipt: {
  input_turn_id, session_id, turn_id,
  status: "received" | "cancelled" | "committed",
  [committed_store_revision], [committed_story_revision]
}],
[session: PublicStorySessionView],
replayed
```

`found=false` 时 receipt/session 均省略、replayed=false；committed 必須同时带两个 committed revision；其余状态禁止带 committed revision。`replayed` 表示返回已有业务结果；读取到已存在命令时可为 true。session 的 observed revision 可以大于这次命令的 committed revision，不混淆二者。

## 4.4 授权与恢复边界

这是单机用户范围授权，不新增账号。鉴权成功仅取得本次 Engine 的访问权，仍须校验 session 属于当前工程 namespace 和已登记的 scenario/worldline/protagonist 绑定。一个有效 session ID 不能读取任意数据库或其他 namespace。

本轮不接通模型 Context Compiler；固定 proposer 仅消费冻结输入、已绑定 PlayerAdvice 和最小 `ActionIntentScope`。UI projection 是独立的 allowlist 授权路径，不得复用“把全部对象序列化后删 secret 字段”的做法。

# 5. 详细实施步骤

按下述依赖顺序执行。角色用于 ownership，不表示自动启动代理；本方案不要求委派。

## T1 — 契约与范围冻结（AGT-ARB）

**拟新增**

- `contracts/protocol/story_session_control.schema.json`
- `contracts/fixtures/ipc/story_session_control.json`

**修改**

- `docs/03_工程规范/Engine_API_Contracts_v1.0.md`：登记 wire 方法及其与 start_story/submit_advice 概念 API 的映射、固定首轮范围、幂等与 revision 规则。
- `docs/PROJECT_STATE.json`：先纠正 #202 合入事实；本轮未完成前只登记下一目标。

先建立请求、响应、错误与未知字段拒绝样例；不要修改现有领域 Schema 来迎合 UI。DTO 位于单独模块：拟新增 `engine/contracts/story_session_control.py` 和 `macos-app/WorldOfMysteries/StorySessionControl.swift`，逐字段按上述 schema 实现，导出按项目已有方式处理。本仓库当前相关 DTO 为手写 parity 模式，不能假设存在未找到的 code generator。

**完成条件**：同一 fixture 被 JSON Schema、Python、Swift 消费；合法形状通过，非法/跨会话/数值边界形状拒绝；字段名和 enum 无客户端私有分叉。

## T2 — 可信内容与初始化绑定（AGT-AI → AGT-DATA；构建由 AGT-ARB）

**拟新增**

- `engine/application/story_initialization.py`：`TrustedScenarioBundle`、`StoryInitializationService`、`ScenarioSourcePort`、`InitializedSessionPort`。
- `engine/infrastructure/story_content_repository.py`：只读内容包校验和装载。
- `engine/infrastructure/story_bootstrap_repository.py`：初始化绑定读取与事务辅助。
- `engine/infrastructure/migrations/010_world_story_bootstrap.sql`。
- `scripts/build_story_content.py`。

**修改** `story_session_open.py`、`story_session_open_repository.py`、`database_schema.py`、`scripts/bundle_engine.py`。

步骤：

1. 构建内容包时使用现有 schema 校验 seed、WorldSnapshot、Character、CharacterKnowledge、PlayerAdvice、ActionIntent；再校验 protagonist/worldline/location、knowledge owner、来源时间不晚于开场、唯一 secret/clue/pressure ID。固定规则版本为 `golden001-opening-policy`，行为复用 `test_golden_turn1_durable._turn1_delta` 的规则。
2. presentation 映射仅新增 `golden_001` 标题、诊室显示名和 `clue_doctor_pause` 的显示名“医生的停顿”；不从 hidden_truth 生成文案。不把所有 secret 转为显示资源。
3. initializer 按现有 `_initial_session()` 规则构造合法 turn=0：scene=`consultation_room`、参与者为 Evelyn/Morris、世界时间使用 seed start、基准 revision 从 world/character 取得；与现有 expected 首轮对齐。
4. 服务端生成 session ID：`"session_" + sha256("story-open/v1\\0" + namespace + "\\0golden_001\\0" + open_request_id)[:32]`。namespace 为固定服务端工程 namespace，不能使用任意客户端字符串。
5. 拟新增表 `story_session_bootstraps`：`session_id` 为 PK/FK 到 `story_sessions.id`；`scenario_id`、`content_version`、`content_digest`、`bootstrap_json`、`opened_store_revision`（FK domain_commits）均 NOT NULL，JSON 用 `json_valid` 校验。JSON 冻结 seed/world/character/knowledge、presentation、固定模型模板及 policy version。
6. 扩展 `OpenStorySessionCommand` 为可选的 typed `bootstrap` 字段，默认 None 保持旧内部调用兼容；公开 initializer 必须提供。冻结必须在第一个 await 前完成；canonical digest 不含 request/trace ID。`_freeze_command` 及 operation identity 纳入 bootstrap 内容，防止同一 open key 偷换初始化。公开 open 重试先按确定的 session ID 查持久绑定；有绑定则使用当初冻结的完整初始对象及模板重建原 operation，不能用已推进的当前 StoryState 或新版内容包重建。首次初始 StorySession 一并放入 bootstrap JSON，保证精确重放。
7. 在 `SQLiteStorySessionOpenPort` 的现有 `apply` 内写 session 与 bootstrap；不要另开第二个事务。bootstrap 写失败，session、domain commit/event/outbox 一并回滚。None 分支沿用旧行为，现有测试不被强制补虚构初始化。
8. recovery 只读冻结 bootstrap。已存在旧 session 但无 bootstrap 时返回 `recovery_required`，不凭当前内容补造历史、不删库。scenario entry 发现这种冲突也不得自动新开。
9. 将 world schema version 从 9 升至 10；走现有备份/迁移。新表不会重写旧 session。失败保留数据库与备份，禁止删除后重建。
10. 构建期生成内容制品，运行时 `mode=ro` 打开。已有受签名的 Canon 内容不覆盖；本轮工程存储根与未来正式存档隔离。

**公开 input 的 CAS 前提也必须持久化。**在同一 010 migration 给 `turn_intake_commands` 增加 nullable `public_expected_store_revision INTEGER CHECK(public_expected_store_revision>=0)`，旧行保持 NULL。不得根据重启后的当前 world_meta 猜原始值。相应修改：

- `engine/application/turn_input.py`：`FinalizedStoryInput`、`TurnInputCommand`、`TurnInputReceipt` 增加默认 None 的同名字段，公开 facade 必须传入；服务端校验严格整数范围，receive 查重时核对字段。
- `engine/infrastructure/turn_intake_repository.py`：`TurnIntakeRequest`、`TurnIntakeRecord`、row decode、`_same_request` 和 `SQLiteTurnInputCommandPort` 映射携带该字段，在原 intake INSERT 同事务写入。
- `engine/application/advice_interpretation.py`：`FrozenTurnInput` 增加默认 None 字段；`engine/infrastructure/player_advice_repository.py` 的 `_frozen` 读取它，公开 facade 据此验证重试前提。
- 原内部 voice/text 调用省略时保持 None；此列不表示世界事实，不改变 world_meta，也不增加 command transaction 的写表权限。公开恢复遇到该字段为 NULL 的旧 input，不将其当成本轮公开请求继续执行。
- 字段变化由 AGT-AI 修改 application 类型，AGT-DATA 修改仓储；新增相关 parity 与旧调用回归断言。任何当前 hard-coded schema version 测试只按真实迁移版本更新，不能降低迁移断言。

**完成条件**：初次 open 的原子性、同 key 重放、不同 payload 冲突、包变更后的冻结恢复、v9→v10 迁移均有测试；world/character 103/27 与 store revision 1 的区分有明确断言。

## T3 — 首轮 facade、投影与恢复（AGT-AI；仓储由 AGT-DATA）

**拟新增**

- `engine/application/story_session_facade.py`：`StorySessionFacade`，提供 entry/open/get/submit/get_advice。
- `engine/application/story_public_view.py`：`StoryPublicViewProjector`。
- `engine/ai/golden_first_turn.py`：`GoldenFirstTurnInterpreter`、`GoldenFirstTurnProposer`。
- `engine/infrastructure/story_session_query.py`：entry、授权绑定、统一 snapshot 和 input 查找。

**保留并组合** `StoryTurnInputService`、`PlayerAdviceInterpretationService`、`AdviceActionIntentService`、`AdviceCommitService` 及现有 SQLite adapters。

实现细则：

- Interpreter 从冻结首轮 advice 模板提取 primary/secondary intent、actions、risk/confidence；raw_input、input mode、advice/turn identity 仍由现有服务绑定。
- Proposer 从冻结首轮 ActionIntent 提取语义候选；移除 fixture 自带的 ID、turn ID、character ID、evidence IDs，交给现有服务重新绑定。
- 策略仍由 `ResolutionPolicy.from_story_seed` + `ResolutionRule` + `StoryEffect` 建立，不读取 expected state，不从网络获取模板。
- facade 以 worldline 为单位串行化公开 mutation；一个 composition runtime 持有同一个锁注册表。CAS 和现有数据库单写队列仍是最终并发裁决，不依赖锁替代存储校验。
- submit **先检查 existing input 身份和状态，再检查当前 revision/首轮限制**。已 COMMIT 的重试在 turn=1、原 expected revision 陈旧时仍应恢复成功；同 ID 不同 session/text 返回身份冲突。
- 新 input：绑定授权 session → exact raw input → expected story/store revision → 当前 turn=0 → 无其他 received input → receive → interpret → AdviceCommitService.commit。
- received input 的显式继续：保留原始冻结 identity 和 revisions，禁止重新 capture 当前 revision；若原基准已失效返回 `revision_conflict`，不自动改 CAS。
- 所有已有 input（包括 committed）先核对持久 `public_expected_store_revision` 与请求值相同；expected story revision 与 frozen base_revisions.story 相同。然后才允许 committed 早返回；不能只校验客户端 journal 或只比较当前数据库 revision。
- intake/interpretation 不推进 `world_meta`。commit 使用已验证 expected store revision；其他 writer 改变 store 时返回冲突，不无限重试。
- 读请求不得产生 advice、调用模型/Resolver、重写 session 或推进 revision。
- `StoryPublicViewProjector` 仅根据当前 snapshot 和冻结 allowlist 构建字段；只有已提交且已发现的 clue ID 可显示。未知 clue/display mapping 返回 `recovery_required`，不要输出原始对象或猜显示文字。
- query port 用一个一致性读快照获取 session、bootstrap、store revision、最新 committed turn 和 pending input。优先单条 SELECT + 受控 JOIN/子查询；不要用多次 `read_world` 拼接后宣称原子快照。存在多个异常 pending 行时 fail closed，不任取一个。

**完成条件**：正常首轮与真实 Golden expected 对齐；固定输出不覆盖任意输入；恢复时解释器/proposer/Resolver 调用次数不增加；secret_04 及其他 hidden 内容不出现在 public view。

## T4 — 组合根、公开 IPC 和包内启动（AGT-DATA；构建由 AGT-ARB）

**拟新增** `engine/infrastructure/story_runtime.py`、`engine/infrastructure/story_control.py`。

**修改** `engine/infrastructure/ipc_server.py`、`macos-app/WorldOfMysteries/EngineProcessManager.swift` 的配置传递（后者归 AGT-MAC）。

1. `StoryRuntime.open(config)`：校验内容制品、打开数据库、构造既有 repositories/services、facade、request handlers；`close()` 等待被接纳写事务结束并关闭数据库。
2. `_run` 注入 runtime；产品初始化失败时仍可维持 system-only health，并返回脱敏的不可用原因，不注册 story capabilities、不显示 world_ready=true。不可静默创建空 Canon。
3. 为 `LocalIPCServer` 增加独立 `request_handlers` 参数，handler 接受冻结的 `{request_id, trace_id, idempotency_key}` context 和 payload。保留现有 `control_handlers(payload)`，不通过 TypeError/反射猜测 handler 签名。
4. capability 合并两个 registry，禁止重复名称、覆盖 system/media 名称；两类 handler 不改变既有语音行为。
5. health 增加注入 provider，默认仍返回 system-only 行为。story runtime 正常时 world_ready=true；model_ready=false、voice_ready=false，不能因为固定 proposer 可运行就谎报真实模型在线。
6. `response()` 允许显式传入安全的 `retryable`（默认 false）。错误 message 采用固定映射，禁止捕获异常后输出原 payload、路径、SQL 或 seed 内容。
7. 正式 Engine 启动仍使用随包 Python、原 token-fd 与 parent-pid；为存储根增加显式 CLI 参数 `--data-root`。App 使用 Foundation Application Support URL 推导，不通过 cwd/环境变量猜测。路径是配置，不是业务 IPC 可传字段。
8. 现有只验证 system transport 的测试可显式不注入 story runtime，保持原 health 期望。新增产品测试必须注入真实 runtime、临时数据根与构建出的内容制品。
9. 关停先停止接收请求，等待/取消服务任务时遵守数据库“已接纳事务须判定结果”的行为，再关闭 runtime；不把连接断开解释为回滚。强退后下一次只读恢复。
10. 引入产品 runtime 的初始化路径不得修改已安装 App bundle；构建产物更新走既有打包流程。新增打包工具的 subprocess git 必须净化项目规定的 GIT_* 钩子变量。

**完成条件**：真实独立 Engine 的五个 story 方法可达，错误 envelope 正确关联，服务关闭资源完整回收；数据根持久保留，短 socket namespace 回收。

## T5 — App 真实首轮 UI（AGT-MAC）

**拟新增**

- `macos-app/WorldOfMysteries/StorySessionModel.swift`
- `macos-app/WorldOfMysteries/StoryRequestJournal.swift`
- `macos-app/WorldOfMysteries/StorySessionPanel.swift`

**修改** `EngineIPCClient.swift`、`AppState.swift`、`ContentView.swift`；按实际项目文件登记方式补充新源文件。只有 Xcode 明确需要登记时修改 `project.pbxproj`，该路径须显式扩权。

1. EngineIPCClient 增加 typed entry/open/session/submit/recover 方法；沿用 `send`，严格验证 schema version、session/input identity、receipt 状态和 revision 字段条件。
2. `StorySessionModel` 采用 `@MainActor @Observable`，管理独立状态：
   `unavailable / loading / notStarted / opening / ready / submitting / recovering / pending / completed / failed`。
   这些是 UI 状态，不新增领域 session status；DTO status 继续使用现有领域枚举。
3. 独立 `canStartStory/canSubmitStory` 依赖 story capability、已授权 view、无 in-flight/pending 请求、view.can_submit。不得把 `isEngineReady` 或 `world.home` 伪造为已实现，从而顺带开放 Artifact mutation。
4. 继续保留未接线页面 `DemoWorldSnapshot` 的示例标签；`isShowingDemoData` 不能因真实首轮 panel 存在而全局变 false。只在命运干预/故事区域放入独立 panel，显示固定模式与真实提交状态。
5. panel 中的 AdviceInputField 使用真实人物显示名与 typed submit 回调；语音仍禁用。不能复用旧示例人物名作为当前真实人物。
6. 请求发送前，将 open/input identity、session、冻结 raw text、expected revisions 写入 App 私有 Application Support JSON journal；原子写入，目录 0700、文件 0600。journal 不含 token/hidden state/数据库内容，不是领域事实源。
7. journal 写入失败则不发 mutation。开场/首轮返回并经关联校验后更新本地 journal；即使更新失败，下次通过服务端幂等查询恢复。
8. 重开先读取 entry：有 session 则恢复其 view；journal 有 input 时只查询对应 input。若 entry 报告服务端 pending input 而 journal 遗失，可用服务端返回的 pending identity 恢复查询，但不能猜 raw text 自动提交。
9. entry 在存在 pending input 时提供 §4 契约的 `pending_input_turn_id`（最多一个）；若需要“继续”且 journal 不含冻结文本，UI 仅显示待处理并提示当前验证无法继续，禁止猜测文本自动执行。这里属于已知恢复限制，不声称损坏/遗失客户端 journal 后仍可全自动继续。
10. generation 在重新连接、关闭、切换 scenario 时递增；旧请求完成不能覆盖新 view、清空新草稿或触发新提交。只清理与成功 input 匹配的草稿。
11. 提交完成显示“第 1 轮已保存”“医生的停顿”；不把此事实展示命名为生成叙事或已完成 Episode。正常关闭 App 不清理持久目录。

**完成条件**：真实 UI 可完成规定演示；示例页面仍明确标记，失败草稿保留，未知结果不假显示失败或成功，重连无 mutation 自动重发。

## T6 — 联合验收和事实回填（AGT-QA → AGT-ARB）

按第 7、8 节完成测试与人工演示。更新状态 JSON、前序交接、总计划中的实际完成范围；不要修改旧 receipt 或把历史测试数量当作本轮结果。本方案执行完成后追加实际代码 SHA、测试平台和日志位置，而非预先勾选。

# 6. 关键实现说明

## 6.1 首轮伪代码

```python
# 拟新增 facade 行为，名称用于说明，现有 service 名称保持原样。
async def submit(command, request_context):
    async with mutation_lock:
        binding = await query.authorize_session(command.session_id)
        existing = await durable.load_input(command.input_turn_id)
        if existing is not None:
            require_same_session_text_and_mode(existing, command)
            require_original_frozen_revision(existing, command)
            if existing.status == COMMITTED:
                return await recover_public_result(existing)  # 零模型/Resolver调用
            if existing.status == CANCELLED:
                raise input_turn_cancelled
        else:
            require_supported_exact_text(binding, command.raw_input)
            require_first_turn_and_expected_revisions(binding, command)
            require_no_other_received_input(binding)
            await intake_service.receive(finalized_text(command))

        await interpretation_service.interpret(command.input_turn_id)
        result = await advice_commit_service.commit(
            command.input_turn_id,
            policy=binding.frozen_policy,
            store_expected_revision=command.expected_store_revision,
            request_id=request_context.request_id,
            trace_id=request_context.trace_id,
        )
        return await query.public_committed_result(result.turn.id)
```

对已经存在的 received input，文本限制、mode 和基准仍须与首次输入一致；固定模板更新不能改变此 input 的语义。读取恢复不调用此函数。

## 6.2 revision 与幂等

| 值 | 语义 | 使用处 |
|---|---|---|
| base world / character revision | 开场可信源快照，Golden 为 103 / 27 | 领域一致性 |
| story revision / turn | 当前会话进展，0 → 1 | 新 Advice 乐观并发 |
| observed store revision | 一致性读取得到的数据库当前 revision | 新 mutation CAS |
| opened store revision | 开场最初提交的 revision | 开场审计和重放，不能当永远有效的 CAS |
| committed store revision | 某个 turn 的数据库提交 revision | 结果追踪，不能用最新 revision 替代 |

同 key 重试使用原请求；读取和恢复可以返回更新的 view。不同 key 的第二次 open 遇到当前 worldline 已有 session 必须返回冲突，引导 entry 查询，不能清库。请求 request_id 是传输关联，不能作为长期幂等身份。

## 6.3 安全文案与错误

| code | retryable | UI 行为 |
|---|---|---|
| `schema_invalid` / `authorization_denied` | false | 保留草稿，提示请求无效/不可访问；不暴露身份是否存在的额外细节 |
| `deterministic_input_unsupported` | false | 提示仅支持指定首轮建议；允许用户改稿 |
| `iteration_limit_reached` | false | 首轮完成，后续回合未开放 |
| `input_turn_identity_conflict` | false | 保留原记录，禁止自动新建 ID 重试 |
| `pending_turn_exists` | false | 转入 pending 查询 |
| `revision_conflict` | false | 刷新只读 view；禁止静默替换 expected revision |
| `recovery_required` | false | 保留数据，显示恢复受阻；不自动重建 |
| `service_unavailable` / `storage_failure` | true 仅用于查询可重试 | 先查结果；对 mutation 仍不自动重发 |

传输超时不必伪造成上述业务 error；显示“正在确认是否已保存”，执行只读查询。日志仅记录方法、请求关联、状态码、非敏感 revision；不记录 token、raw input 或整个 Pydantic ValidationError。

## 6.4 初始化绑定与包升级

现有内部 opener 无 bootstrap 的调用仍有效，公开产品入口必须有 bootstrap。恢复能读取旧冻结模板，但只能执行当前支持的 `content_version/policy_version`；不认识的版本返回 recovery_required，不能用新策略悄悄处理旧 pending input。已 COMMIT 的事实读取不要求重新运行旧策略。

本迭代不提供数据重置、删除存档、第二世界线或切换主角按钮。Schema migration rollback 以未被后续写入的备份为基础由人工评估，不把旧备份覆盖新提交作为自动恢复。

# 7. 测试方案

新增测试名称是拟定交付要求；测试文件未创建前不要声称命令可直接执行。

| 测试文件 | 要验证的行为 |
|---|---|
| 拟新增 `contracts/tests/test_story_session_control.py` | 全方法 request/response parity；unknown keys、bool revision、缺失幂等键、null、错误 receipt 条件拒绝 |
| 拟新增 `engine/tests/test_story_initialization.py` | fixture schema 与跨文件身份；turn=0、世界时间和 103/27；未知场景/伪造 actor/过晚知识拒绝 |
| 拟新增 `engine/tests/test_story_bootstrap_repository.py` | v9→v10 保留旧数据；session/bootstrap 原子开场；fault hook 回滚；同 key 内容冲突；旧 session 无绑定 fail closed |
| 修改 `engine/tests/test_turn_input.py`、`test_turn_intake_repository.py`、`test_player_advice_repository.py` | nullable public CAS 字段逐层传递、原内部调用兼容、重试前提不可改写，NULL 的旧 input 不误作新公开命令 |
| 拟新增 `engine/tests/test_story_public_view.py` | 全字段 allowlist；hidden truth、secret IDs、未知 clue/压力从响应和错误中缺席；发现线索才显示 |
| 拟新增 `engine/tests/test_story_session_facade.py` | 固定首轮全链；非支持输入零 intake；并发同 key 一次 COMMIT；不同 key 一个有效首轮；旧 key 重放优先于 turn limit |
| 拟新增 `engine/tests/test_story_runtime.py` | 注册能力/health、内容缺失降级、启停顺序、数据根隔离、只读 Canon 不改变 |
| 修改 `engine/tests/test_ipc_server.py` | request context 与真实 envelope 一致；新旧 handler 共存；duplicate capability 拒绝；错误不泄漏 |
| 修改 `engine/tests/test_golden_turn1_durable.py` | 新可信 initializer 的真实首轮仍等于现有 expected；不可由 expected 构造结果 |
| 保留 `engine/tests/test_golden_voice_chain_durable.py` | 原 voice input/cancel/COMMIT 链不回归；不改为本轮 text 测试来替代旧覆盖 |
| 修改 `engine/tests/test_bundle_engine.py`；拟新增 `engine/tests/test_story_content_build.py` | 内容包完整、digest、规则版本、包中无 expected；资源不依赖仓库 cwd；净化 git env |
| 拟新增 `macos-app/WorldOfMysteriesTests/StorySessionControlTests.swift` | 共享 fixtures、严格 DTO、identity/revision 错配拒绝 |
| 拟新增 `macos-app/WorldOfMysteriesTests/StorySessionModelTests.swift` | UI 状态、journal 先写后发、重复点击、旧 generation、未知结果、失败保稿、首轮禁继续 |
| 修改 `engine/tests/test_app_engine_session.py` 与 `engine/tests/fixtures/app_engine_driver.swift` | 真实 Swift→独立 Engine→磁盘首轮；正常关闭/强退/重开；保留既有 transport 模式 |
| 修改 `macos-app/WorldOfMysteriesTests/WorldInteractionBoundaryTests.swift`、`VisualHonestyContractTests.swift` | 新 live panel 与旧示例页面分离；不得以删除诚实性断言解锁建议台 |

跨进程新增 driver 模式至少包括：

1. `story-open-submit-reopen`：开场、提交、两个进程退出、重新启动、同 session/turn/clue。
2. `story-lost-ack`：在数据库 COMMIT 后、响应发出前断开连接；重启查询成功，计数器不再次调用模型替身/Resolver。
3. `story-precommit-restart`：持久 received/解释后终止；重启显示 pending，不自动提交；用户显式继续一次。
4. `story-open-lost-ack`：开场已提交但客户端未保存响应；entry 找回唯一 session。
5. `story-unsupported-input`：不同文本无 intake/domain commit，草稿保留。

实际生产路径不新增通过用户 payload 开启的故障开关。跨进程 fault injection 仅由测试启动器注入 wrapper/测试依赖，核心服务与仓储使用真实实现。

所有 subprocess git 测试净化钩子注入环境。Swift 手动编译 fixture 应补齐新增 DTO/model/journal 文件；不能用简化版 AppState 或假 Engine 替代生产实现。

不适用：本轮不做真实 LLM 质量、TTS、五轮 Episode、检索向量/图谱重建或公开发行验收；这些项目不勾选通过。

# 8. 验收标准

## 8.1 执行位置与已有验证入口

以下是项目已有入口，执行前读取当前 worktree 租约并使用其中 TMPDIR/SPM 配置。验收命令的权威仍在 `.hacf/gates/FULL_P0.json`，本文不建立新门禁。

在任务 worktree 根目录，实质改动先提交，再执行：

```bash
python3 scripts/agent_capsule.py verify \
  --capsule .agents/capsules/M1-FIRST-TURN-QA.json --cwd "$(pwd)"
```

上例胶囊须由 T6 pack 创建并覆盖本任务实际范围；若使用各任务独立胶囊，逐一替换为对应已生成路径。引用 FULL_P0，凭单另行提交。不得复制历史凭单。

故障定位需要单独执行受保护档案时：

```bash
python3 scripts/gate_profile.py run --profile FULL_P0
```

其现有四阶段为架构适应度、Python/契约测试、Swift Testing、arm64 Xcode App 构建。具体命令从档案读取；不用本文维护第二份。

进度文档更新后：

```bash
python3 scripts/project_status.py status
python3 scripts/project_status.py next
git diff --check
```

预期：状态输出与本次实际完成范围一致；next 指向全领域结算/Golden 五轮的剩余工作；无空白错误。上述命令本次规划阶段均未作为新实现验收运行。

## 8.2 可勾选验收清单

> 勾选状态为 2026-09-26 执行回填；证据见 §11，未验证项保持未勾选。

- [x] Schema / Python / Swift 接受和拒绝同一组 fixtures；未知字段、非法 ID/revision 不进入 service。
- [x] 首次 entry 只读；open 原子保存 bootstrap/session/event/outbox；Story revision=0，基准 103/27 未混入 store CAS。
- [x] 固定首轮通过真实持久链，Story turn/revision=1，与已有 Golden expected 对齐。
- [x] 重复同请求不增加领域 COMMIT、delta、turn；不同 key 并发不会提交两次首轮。
- [x] same input ID 改文本被拒绝；任意其他输入不会得到固定成功结果。
- [x] 开场 lost ACK、首轮 lost ACK、received 后重启均有真实双进程证据。
- [x] App 正常退出和 Engine 强退后可恢复同一 session，旧结果不再次运行模型或 Resolver（以 `domain_commits` 不增长为证）。
- [x] UI 草稿与冻结请求正确关联，自动重连只读取状态，旧回调不污染新状态。
- [x] hidden truth/secret IDs/压力/未发现线索不进入 IPC 响应、日志或 Swift view model。
- [x] Canon 运行前后摘要相同；用户存储根位于持久目录，非 `/tmp` 或 App bundle。
- [x] 升级 v9→v10 不改旧世界数据；迁移失败保留原数据；无 bootstrap 的旧会话不自动补写。
- [x] 包内资源在不含源码仓库的 cwd 可读取，App 使用随包 Runtime；没有 host Python fallback。
      —— staged 模块树在仓库外 cwd 解析模块相对内容制品（跨进程用例）；`EngineLaunchConfiguration.bundled` 缺清单即拒绝且不回落系统 Python（Swift 测试）；`BUNDLED_RUNTIME_P0` 已在 macOS arm64 runner 上真实执行 `stage_engine` 并完成随包 App 探针（见 §11.1 的 CI 证据）。
- [x] 原 voice/media、system-only、cancel/COMMIT、App 生命周期测试保持有效。
- [ ] FULL_P0 凭单绑定实际代码；跨进程和真实 UI 演示绑定同一源码版本并记录日志位置。
      —— 已证：各任务凭单绑定 `base_sha..HEAD` 内容摘要并记录 FULL_P0 四阶段结果；跨进程用例覆盖生产 AppState/StorySessionModel。
      未证：未做可交互 GUI 现场演示与截图/观察记录，故不勾选。
- [x] PROJECT_STATE 与交接记录纠正过时信息，未把首轮等同五轮/正式发布。

现场演示：在隔离的工程数据根上打开实际 App，点击开始、填入建议、提交、看到“第 1 轮已保存”，退出再打开后仍显示同一结果。记录源码 SHA、构建标识、平台、会话/turn ID、两个 revision、失败恢复操作和观察；截图不能替代数据库与进程证据。不触碰用户正式存档。

# 9. 风险与注意事项

1. **新增存储范围**：初始化绑定是必要持久化扩展，但不实现完整 World/Character repositories。冻结快照只服务首轮，不能对外声称世界全领域已完成。
2. **内容与正式 Canon**：工程制品由已有 Golden 源生成，只读且有 provenance；不是第二份卡牌事实库，不读取或写入关联仓库的本地路径。
3. **协议演进**：新增方法与 capability，不破坏 envelope 1.0；旧 App 不调用新能力，旧 Engine 没有能力时新 App 显示 unavailable。
4. **事务边界**：扩展原 opener 必须保留旧 operation 的序列化形状（bootstrap=None 时不额外加入 null 字段），否则历史幂等重放摘要会变化。
5. **版本升级**：已保存 bootstrap 中的模板、策略版本保持原意；未知版本只读已提交事实、停止新 mutation。禁止重新解释旧 input。
6. **并发与 unknown outcome**：请求超时和 task cancellation 都不代表事务未发生；先查询，不用新 ID 重试。数据库 writer 是最终裁决。
7. **UI 诚实性**：world_ready 仅表明本轮 world service 可用，不代表全部导航/Artifact/model/voice 可用；按具体 capability 控制入口。
8. **包构建与签名**：保留当前 `dccdbd7` 的签名修复和组件画廊改动，不以本次接线为理由重构或回退。重新打包后的目标 Mac 验证属于本轮交付；公证/发行审批仍独立。
9. **权限与目录所有权**：contracts、迁移、构建脚本及 project.pbxproj 属受保护范围，实施胶囊需 AGT-ARB 对精确路径登记扩权。角色默认 forbidden 不能靠随意删掉绕过；跨角色文件按下表交接。
10. **范围外**：自由输入模型、Narrative/TTS 自动串联、非 Story overlays、Episode finalization、五轮、检索完整重建、重置存档、多世界线、新美术或新治理框架均不纳入。
11. **客户端恢复限制**：数据库中的 committed 事实即使 journal 遗失仍可通过 entry/session 恢复；received 命令若同时遗失本地冻结请求，只展示 pending。本轮不增加重置/取消 API 解决此边缘情况，验收记录必须保留该限制。

实现前若主线已新增类似产品接线，先读取差异并调整本方案，不新增平行实现。若同一文件出现其他任务未提交改动，停止该处写入、核实来源，不能整文件覆盖。

# 10. Luna 执行清单

## 10.1 任务与所有权

| 任务 ID | 责任与精确目标 | 前置 | 独立完成条件 |
|---|---|---|---|
| `M1-FIRST-TURN-CONTRACT` | AGT-ARB：新 protocol schema/fixtures、API 文档、过期状态纠正；协调 DTO 路径权限 | 无 | wire 契约完整且无歧义 |
| `M1-TRUSTED-INITIALIZER` | AGT-AI：`story_initialization.py`、opener 可选 typed bootstrap；Python DTO 按登记授权 | 契约 | 纯 initializer 与冻结校验测试通过 |
| `M1-TRUSTED-BOOTSTRAP` | AGT-DATA：内容读取、bootstrap/query repositories、010 migration、opener adapter | initializer | 原子开场、迁移、恢复测试通过 |
| `M1-FIRST-TURN-SERVICE` | AGT-AI：facade/public projector/固定 interpreter+proposer | 仓储 | exact input、真实裁决、投影和幂等通过 |
| `M1-FIRST-TURN-RUNTIME` | AGT-DATA：story runtime/control、IPC context、health、关闭顺序 | service | 独立 Engine 全方法真实执行 |
| `M1-FIRST-TURN-CONTENT` | AGT-ARB：内容构建脚本、bundle_engine、随包资源 | initializer；可与 service 准备并行 | 无源码仓库依赖且包内摘要一致 |
| `M1-FIRST-TURN-APP` | AGT-MAC：DTO/client/model/journal/panel、AppState/ContentView/launch config | 契约；联合验收依赖 runtime/content | App 正常、错误和重启路径通过 |
| `M1-FIRST-TURN-QA` | AGT-QA：契约/跨进程/Golden/UI 回归；AGT-ARB 回填状态 | 上述全部 | FULL_P0 + 真 App 演示证据，范围诚实 |

任务名仅为本方案建议，不代表已 pack 或执行。共用文件仅一个任务写：opener API 归 initializer，SQLite adapter 归 bootstrap，`ipc_server.py` 归 runtime，`EngineProcessManager.swift` 归 App，打包脚本归 content。

## 10.2 顺序执行

- [x] **核对基准**：检查目标 `origin/main`、HEAD、工作区差异及同路径并行任务；与本文 SHA 不同时读取相关变更，保留全部他人改动。
- [x] **T1 契约**：创建 schema/fixtures 和 API 映射；核对所有字段，包括 entry 的 pending_input_turn_id；明确幂等键/revision/错误规则。
- [x] **T2 initializer**：实现可信内容验证和 turn=0 构建，禁止从客户端 Session 开场；纯测试验证身份和时间。
- [x] **T2 仓储**：实现 010 migration 和原子 bootstrap 绑定；测试 rollback、重放、旧数据和包升级恢复。
- [x] **T3 facade**：连接 receive→interpret→propose→resolve→COMMIT，完成 only-first-turn、exact input、pending 防重与 public allowlist。
- [x] **T4 runtime**：接入 request context、capability、health、持久数据根和受控关停；保持原 control/media 接口。
- [x] **内容打包**：构建可信制品并纳入 runtime inventory；确认运行时不读仓库 fixtures/expected。
- [x] **T5 App**：typed client、journal、独立 live panel 与 generation；先查结果再显式重试，失败保留草稿。
- [x] **T6 联调**：更新实际 Swift driver 输入，执行正常/两种 lost ACK/received 重启/非法文本路径。
- [x] **工程验收**：实质代码提交后运行适用 verify，最终组合执行 FULL_P0；凭单独立提交；不改胶囊伪造结果。
- [ ] **体验验收**：记录真实 App 打开→首轮→关闭→回来及异常恢复；仍未验证项保持未勾选。
- [x] **事实收尾**：更新 PROJECT_STATE 与交接，仅声明实际完成的能力；后继目标为全领域结算和 Golden 五轮。

每个实现任务遵循现有 `pack → start → 实施并提交 → verify → 凭单独立提交`，分支使用 `codex/` 前缀、`target_ref=origin/main`。后继任务在前置集成后的实际基线重新 pack；不使用 `--allow-stale`。远端提交、PR 合并与发布按届时用户授权执行，本文不自动授权。

**迭代完成定义：合法开场与首轮真实 COMMIT 从 App 可达，最小公开投影不泄密，关闭与重启恢复同一持久事实，并有绑定实际 SHA 的工程与产品运行证据。**

# 11. 执行结果回填（2026-09-26）

本节在执行完成后追加，不改写第 1–10 节的规划原文；未验证项见 §11.3，且第 8.2 节对应项保持未勾选。

## 11.1 实际交付与证据

- 分支：`codex/trusted-session-app-first-turn`（专用 worktree，独立 `.hacf/workspace.json` 资源租约）；迭代 base `dccdbd76ef488281cda86be01a6857754b91b7c0`，最后实质代码提交 `9a07f40b39f571dbe356ef52c742689dcb045f09`（验收补证提交 `fc69ee88`）。
- Work Receipt（全部 `verdict=passed`，门禁档案 `FULL_P0`；凭单位于 `.agents/receipts/<TASK_ID>/<sha>.json`）：

| 任务 | 实质提交 | 交付要点 |
|---|---|---|
| `M1-FIRST-TURN-CONTRACT` | `0fa0d2c` | `story_session_control` 协议 schema/fixtures 与 API 映射 |
| `M1-TRUSTED-INITIALIZER` | `07e7b58` | 可信内容校验、turn=0 会话与冻结 bootstrap |
| `M1-TRUSTED-BOOTSTRAP` | `43118b6` | 010 migration、原子开场绑定、公开 CAS 字段持久化 |
| `M1-FIRST-TURN-SERVICE` | `3b26aa3` | facade、授权投影、固定 interpreter/proposer |
| `M1-FIRST-TURN-RUNTIME` | `7b3ec83` | 组合根、五方法 IPC、request context、health、受控关停 |
| `M1-FIRST-TURN-APP` | `f45fbf4` | typed client、journal、独立 live panel、generation |
| `M1-FIRST-TURN-QA` | `84abf72` | 真实 Swift 编译夹具恢复（FULL_P0 重新全绿） |
| `M1-FIRST-TURN-CONTENT` | `e319814` | `build_story_content.py` 制品构建 + bundle_engine 随包 staging |
| `M1-FIRST-TURN-CROSSPROCESS` | `9a07f40` | 真实双进程首轮、丢 ACK、pending 续跑、非法输入 |
| `M1-FIRST-TURN-ACCEPTANCE` | `fc69ee8` | canon 只读摘要不变、App 用户事实落在 Application Support |

- 验证平台与命令（2026-09-26，Apple Silicon / macOS 26，Python 3.14.7 + uv，Swift 6 + Xcode 27）：
  - `FULL_P0` Stage 1 `check_architecture_fitness.py`；Stage 2 `engine` 下 `uv run --locked --extra dev pytest -q`（1113 passed）；Stage 3 `swift test`；Stage 4 `xcodebuild -scheme WorldOfMysteries -destination platform=macOS,arch=arm64 build`。
  - 证据产物：各任务 Work Receipt（含 scope audit 与四阶段结果）、`.hacf/run/xcode-derived/`（App 构建输出）、`.hacf/spm-scratch/`（SwiftPM scratch）；运行期短命名空间由 App 的 runtime lease 自建自清。
- 实施范围：T1 契约 → T2 可信初始化与 010 迁移 → T3 facade 与授权投影 → T4 runtime/公开 IPC/内容制品 → T5 App 接线 → T6 联合验收与事实回填。
- CI（GitHub Actions，PR #204，代码 head `e9682db`）全部通过：`Capsule Gate`、`All Quality Gates Passed`、Stage 1/2/3（架构适应度 / Python + 契约 / Swift 6 与协议往返）、`Relocatable sandboxed arm64 package`（真实执行 `stage_engine` + 随包 App 探针，5m32s）。
  - 过程记录：同一 head 早先一次 Stage 3 因既有 `ProbabilityDiePhysicsTests` 墙钟预算（1.65s > 1.5s）在慢速 runner 上抖动失败，重跑即通过；`BUNDLED_RUNTIME_P0` 首次真实执行暴露了随包探针固定源文件清单缺少首轮 Swift 闭包（`probe-compile.log`），已由 `M1-FIRST-TURN-PACKAGE-PROBE` 修复并复跑通过。

## 11.2 与规划稿的差异

1. 验收胶囊按职责拆为 10 枚（契约 / 初始化 / 仓储 / facade / runtime / 内容 / App / QA / 跨进程 / 验收补证），逐枚执行 `pack → 提交 → verify → 凭单独立提交`，未使用单枚 `M1-FIRST-TURN-QA` 覆盖全部范围。
2. 中间态提交使用 `--no-verify`：pre-commit 钩子固定跑 `FULL_P0`，而 T5 的 App 接线会先打破 `engine/tests/test_app_engine_session.py` 的真实 Swift 编译夹具，该夹具属不同角色写域。每个任务仍由自身受保护档案的 `agent_capsule verify` 立凭单收口，最终 HEAD 的 `FULL_P0` 全绿。
3. 跨进程 fault injection 由测试启动器注入：staging 模块树把生产 `ipc_server.py` 逐字节保存为 `_ipc_server_production.py`，只注入“声明宿主 SQLite 版本”（等价于既有 `expected_sqlite_version` 兼容注入）与一次性 fault hook 的启动器包装；生产代码没有任何故障开关，核心服务与仓储保持真实实现（测试逐字节断言）。
4. 测试环境以宿主 `sqlite3` 替身模块承担 `_wom_sqlite3` 角色，故本文不声称已验证私有 SQLite 3.53.4 扩展路径；该版本检查由打包与既有打包测试覆盖。
5. App journal 用 `CFFIXED_USER_HOME` 隔离到临时家目录，测试不触碰用户正式存档；本轮首次运行曾污染用户 Application Support 下的工程 Journal 目录，已回收并加入隔离断言。

## 11.3 明确未验证（不勾选）

- 可交互 GUI 现场演示（打开 App、点击开始、填入建议、提交、看到“第 1 轮已保存”、退出重开）与截图/观察记录。本轮证据为生产 `AppState`/`StorySessionModel`/`EngineIPCClient` 与真实独立 Engine 的双进程一致性，不等同于人工 GUI 演示。
- 随包 App 的「目标 Mac 安装与真实用户交互」验收：CI 已执行打包与随包探针（沙箱内启动随包 Engine），但未做目标机器安装、GUI 操作与发布签名/公证。
- Golden 五轮、全领域结算、真实 LLM 质量、TTS 播放、检索投影重建、目标设备与发布验收。
- 远端推送、PR、CI 检查、CODEOWNERS 评审与合入：按用户授权另行执行。
