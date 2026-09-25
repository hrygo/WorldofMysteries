# 1. 问题结论

**下一迭代：持久化 Session Open、第一轮 Advice 提交与数据库重启恢复。**

- 日期：2026-09-25。
- 证据基线：`main@0890eb308b833c9afdf9ade9ef147cf63b4d4a2f`，最新合入 #201。
- 文档性质：设计方案及 2026-09-25 候选交付记录。T1–T3 已实施并通过 FULL_P0；T4 状态文档更新正在独立候选分支验收。实现尚未推送、创建 PR 或合并。
- 目标：合法初始会话无需先提交虚构的引导回合，即可持久化；第一条真实输入经现有服务到达 COMMIT，重复请求及数据库重启均不重复推进。
- 范围：Application 内部端口、SQLite adapter、持久回归测试、进度文档。此次不承诺 App 可玩闭环或 Golden 001 五轮验收完成。
- 技术基线：现有 Python 3.14.7、SQLite 四库隔离、单写者事务及 Pydantic 契约。不得引入新 SDK、数据库、服务或模型依赖。

前一轮建议中的“Session Open → App 接线 → 五轮 → 发布”是整个推进序列。本迭代只交付第一个可独立验收的阶段。源码表明首轮入口、非 Story 增量结算、产品组合根是不同工作量，不能在同一小迭代里笼统承诺全部解决。

规范入口：

- [Persistent World Alpha](Persistent_World_Alpha_Plan_v1.0.md)
- [Story Engine §19 持久语义](../02_领域引擎/Story_Engine_v1.0.md)
- [Engine API Contracts §5](../03_工程规范/Engine_API_Contracts_v1.0.md)
- [Voice-First 实施方案 W-V09/W-V10](../07_工程启动/Voice_First_Implementation_Plan_v2.0.md)
- [现有 durable chain 测试](../../engine/tests/test_golden_voice_chain_durable.py)

# 2. 当前实现与根因

## 2.1 已核实的代码事实

本次没有可调用的 Codebase Memory 图谱工具，采用定向文件检索和源码阅读；结论限定在下表路径及其直接依赖，不声称完成全库审计。

| 文件 / 符号 | 当前实现 | 本迭代处理 |
|---|---|---|
| `engine/application/turn_input.py` / `StoryTurnInputService.receive` | 先恢复已有 input，再读取已存在且 active 的 session；冻结 base revisions | 保留；让新 opener 产出的 session 满足现有入口 |
| `engine/infrastructure/story_session_repository.py` / `SQLiteStorySessionCommitPort.commit_turn` | session 不存在时，只有 story base revision=0 的已验证回合能建立记录 | 保留旧路径兼容性；新增显式开启 adapter，不移除隐式路径 |
| 同文件 / `load_session` | 从权威表组装 `StorySession` | 复用；必要时提取文件内行解码函数，不改变旧签名 |
| `engine/infrastructure/migrations/002_world_story_sessions.sql` | session 的 `committed_world_revision` 非空且引用 `domain_commits`；同一 worldline 仅允许一个未终结 session | 原样保留，不回写历史 migration |
| `engine/infrastructure/database_manager.py` / `commit_resolved`、`_commit` | 同一单写队列内做幂等、CAS、业务写入、事件、Outbox 和 COMMIT | 复用，不增加旁路写者 |
| 同文件 / `turn_command_write` | 只允许写 intake/advice；没有 session 写权限 | 保留限制，不扩权为任意领域写入 |
| `engine/application/story_turn_commit.py` / `_validate` | 拒绝 character/relationship/knowledge/world-event overlays | 保留；这是五轮全领域验收的后续依赖 |
| `engine/application/advice_commit.py` / `AdviceCommitService` | 从 durable advice 到提案、裁决和提交；已提交 intake 重放不再调用模型 | 原样复用 |
| `engine/tests/test_golden_voice_chain_durable.py` | `bootstrap_turn_one` 先提交引导回合，真实输入链从 turn 2 开始 | 移除该测试的引导回合，改为 opener 后从 turn 1 测起 |
| `engine/tests/test_golden_turn1_durable.py` | Golden 第一步直接提交 validated turn，有真实 SQLite 和重开验证 | 保留一例旧路径回归，并新增显式开启后的 Golden 首轮路径 |
| `engine/application/session_orchestrator.py` | 当前只有上下文准备 Protocol | 本次不扩建完整产品 Orchestrator |
| `engine/infrastructure/ipc_server.py` | 通过注入 control handlers 公布业务能力 | 本次不新增 handler 或 capability |

## 2.2 复现与技术原因

在干净的测试 world.db 中，直接向 `StoryTurnInputService.receive` 传入一个从未落库的 session ID，会在 `load_session` 处失败。现有测试通过先提交 turn 1 避开这个入口断点。

直接原因是缺少显式的持久会话开启端口。更深的原因是原垂直切片把“建立会话”合并到了“首次回合 COMMIT”，但后来的 durable intake 要求会话先存在，两个前置条件形成循环。

这不是 SQLite 表缺失，也不需要重新设计四库架构。现有 schema 已允许 `story_revision=0`，只需用合法的领域生命周期事务建立记录。

## 2.3 当前证据边界

#201 的 Work Receipt 与主线 CI 是历史基线证据，不作为新 opener 的验收结果。新 opener 的验收证据见 §2.4。

主工作区存在其他工作的未提交内容：`ComponentGalleryView.swift`、`scripts/build_macos_package.py` 及未跟踪凭单。本方案不涉及这些文件；实施期间保留原状。

## 2.4 本轮执行结果（2026-09-25）

- 实施基线为 `main@0890eb308b833c9afdf9ade9ef147cf63b4d4a2f`。代码 head `b848ad66f159f7a2d493da51ce23e716b0d5fbc2`，对应 QA Receipt 独立提交 `710d7bf5d96a23268be09822a14934b2a12ad2f8`。
- Work Receipt `RCP-WORK-VOICE-V09-SESSION-OPEN-QA-b848ad66f159` 绑定 `FULL_P0`，架构、Python/Contracts、Swift 6 测试与 arm64 Xcode App Target Build 四阶段均通过；`coverage_gaps` 和 scope violations 均为空。候选 diff 未包含产品 Schema 或 migration。
- Session Open 原子增加 store revision 一次并写入 session、`story.session.opened` 与 Outbox；Story revision/turn 保持 0。首条真实 Advice→COMMIT 再增加 store revision 一次并将 Story revision/turn 推进到 1。候选测试覆盖语义重放、当前权威快照恢复、数据库关闭重开、CAS、唯一活跃会话、并发以及提交前 fault rollback 和提交后失 ACK 重试。
- 对候选业务代码和测试的只读整分支审查未发现 Critical、Important 或 Required 问题。审查没有重跑门禁或独立复算 Receipt。
- 候选尚未推送、创建 PR 或合并。M1 仍缺产品组合根、受限 IPC 与 App 接线；M2 全量四库范围、M5 Golden 五轮、进程/App 重启连续性、真实模型、设备和发布验收也仍未完成。

# 3. 目标行为

## 3.1 开启与首轮

1. 可信 Application 调用方提供经过类型验证的初始 `StorySession`。其来源将来由 StorySeed/StoryContext 初始化负责；本次不实现 Genesis、世界装载或用户输入到初始会话的映射。
2. 开启请求原子建立一个 `active` session：`story_state.revision=0`、`turn=0`、`last_state_delta_id=None`。
3. 开启属于持久领域生命周期事件；存储 revision 从 R 到 R+1，写一条 `story.session.opened` 事件及一条 Outbox。不得建立 `TurnTransaction`、`StateDelta`、Narrative 或音频。
4. 世界叙事时间保持初始值；开启不调用模型、Resolver 或 Story reducer。
5. 首条输入以 story revision 0 冻结，后续 Advice 提交流程保持现有逻辑；提交成功后 story revision=1、turn=1，存储 revision=R+2。
6. `base_revisions.world/character` 是冻结的领域快照版本，不能以存储 revision 替换。例如现有 Golden 的 world=103、character=27，不能因开启改成 1。

## 3.2 重放、恢复和冲突

- 同一开启键、完全相同的初始请求重试：返回首次开启 revision 和当前权威 session，不新增事件或回合。
- 同键不同初始状态、身份或原始 expected revision：返回明确冲突，不更新旧会话。
- 首轮已经提交后重试开启：允许恢复，返回 story revision 1 的当前 session，绝不把它重置为 0。
- 数据库关闭重开后，可通过 session ID 只读恢复；不存在时明确报错，不偷偷新建。
- 恢复保持原 status。`suspended` 不自动变 active，`finalized` 不重新开启；状态迁移另行实现。
- 同 worldline 的 active/suspended/closing/recovery_required 会话阻止另一新会话。finalized/cancelled 不占用该唯一槽，但旧 ID 永不覆盖复用。
- 新请求 expected revision 陈旧时拒绝；不自行读取最新 revision 后盲目重试。

# 4. 推荐解决方案

## 4.1 选型

| 方案 | 影响 | 结论 |
|---|---|---|
| 伪造第 0/第 1 回合引导 | 污染回合数、事件、幂等和世界时间语义 | 不采用 |
| 放宽 FK，允许 session 绕过领域日志插入 | 引入迁移、新事务授权及恢复规则 | 不采用 |
| 用现有 `commit_resolved` 提交 session-open 生命周期事件 | 无 schema 变更，继承现有 CAS、幂等、Outbox 和故障保障 | 推荐 |

“开启使存储 revision 加一、故事回合不变”是本方案明确提出的设计决策，不是现有实现事实。它符合持久 Domain state 定义，并满足当前 FK。实施评审若要求开启完全不增加存储 revision，应停止该任务并重新设计迁移与事务边界，不能私自改成 pre-commit command write。

## 4.2 模块与接口

**新增** `engine/application/story_session_open.py`：

```python
@dataclass(frozen=True, slots=True)
class OpenStorySessionCommand:
    initial_session: StorySession
    open_request_id: str
    store_expected_revision: int
    request_id: str
    trace_id: str

@dataclass(frozen=True, slots=True)
class StorySessionSnapshot:
    session: StorySession
    observed_store_revision: int

@dataclass(frozen=True, slots=True)
class StorySessionOpenResult:
    snapshot: StorySessionSnapshot
    opened_store_revision: int
    replayed: bool

class StorySessionOpenError(RuntimeError):
    # __init__(code: str) stores self.code and passes code to RuntimeError.
    ...

class StorySessionOpenPort(Protocol):
    async def open_session(
        self, command: OpenStorySessionCommand
    ) -> StorySessionOpenResult: ...
    async def load_snapshot(self, session_id: str) -> StorySessionSnapshot: ...

class StorySessionOpenService:
    # __init__(port: StorySessionOpenPort)
    async def open(self, command: OpenStorySessionCommand) -> StorySessionOpenResult: ...
    async def recover(self, session_id: str) -> StorySessionSnapshot: ...
```

以上均为内部 Python 接口，不是已发布 IPC API；省略号仅表示端口签名。实现行为在第 5、6 节定义。复用 `contracts.StorySession`、`StorySessionStatus`，不新建会话状态枚举或跨语言字段。

**新增** `engine/infrastructure/story_session_open_repository.py`，实现 `SQLiteStorySessionOpenPort`。保留现有提交 adapter 的职责；两个 adapter 共用同一个 `DatabaseManager` 实例。

`recover` 只读当前会话及数据库 revision。`open` 的首次 revision 来自幂等日志，当前快照可能更晚。不能把 `opened_store_revision` 当作下一次写入 CAS 值，也不能声称多次读取构成一个原子快照。

# 5. 详细实施步骤

## T1：Application 端口和验证（AGT-AI）

文件：`engine/application/story_session_open.py`、`engine/tests/test_story_session_open.py`。

先写 fake-port 单元测试，覆盖合法初始状态、非法输入不调用 port、恢复原样保留 status。再实现服务：

- `initial_session` 必须是 `StorySession`，用 `model_dump(mode="json")` 后 `StorySession.model_validate` 重新校验，不能信任 `model_copy(update=...)` 构造的未验证模型。
- 新请求必须 `ACTIVE`、story revision=0、turn=0、base story=0、last delta 为 None；state.session_id 必须等于 session.id。
- session/world/worldline/protagonist/seed ID 与三个请求 ID 均要求非空、非纯空白、无 NUL、长度不超过 256；拒绝而不静默 trim 身份。
- `world_time` 必须为非空字符串且符合现有存储标识长度/NUL 约束；它表示叙事世界时间，不额外要求时区或改写格式。当前 `StoryState` Schema 允许 string/null、既有测试含无时区值，而领域提交要求非空，因此 opener 在创建领域事件时拒绝空值。不以现实时间补空，不自行改初始 phase/scene/clues/secrets/pressure。
- store expected revision 为非 bool 整数，范围 `0 <= n < 2**63-1`。
- 在第一次 await 之前深拷贝并重新校验初始模型；adapter 也在排队前冻结持久化请求，避免外部修改嵌套字段。
- `recover` 只验证 session ID，再调用 `load_snapshot`，不强制 ACTIVE，不使用 open 替代恢复。

稳定错误码：`invalid_open_command`、`invalid_initial_session`、`invalid_open_identity`、`invalid_world_time`、`invalid_store_expected_revision`。Pydantic 详情可留在内部异常链，不输出隐藏状态正文。

完成条件：新 Application 模块无 SQLite/Infrastructure import；单测能证明非法请求零持久化调用。

## T2：SQLite 开启与恢复（AGT-DATA，依赖 T1）

文件：`engine/infrastructure/story_session_open_repository.py`、`engine/tests/test_story_session_open_repository.py`；另小幅修改 `story_session_repository.py`，提取并复用行解码函数。

1. 构造稳定幂等键：`story-session-open:` 加 SHA256，输入为版本化前缀、session ID、open_request_id，使用 NUL 分隔。事件 ID 使用同一摘要的独立事件前缀。
2. canonical 初始 session 使用 JSON mode、排序键、紧凑分隔、`allow_nan=False`；统一使用 `exclude_none=True`。`operation` 必须包含 `kind=story.session.open`、完整规范化初始 session、open_request_id。不能只绑定 session ID，否则同键不同状态会误命中。
3. `CommitRequest` 复用原请求 expected revision、initial worldline/world_time、trace/request ID；事件最小 payload 为 session ID 和 story revision 0，不把隐藏 secrets 或完整状态复制到事件 payload。
4. `apply(tx)` 内查 session ID；若已存在且非幂等重放，报 `story_session_exists`。再查 worldline 未终结会话，命中则报 `worldline_has_open_session`。
5. 插入现有 `story_sessions` 13 列：冻结 bases 原样保存，story revision=0，status=active，完整初始 state JSON，`committed_world_revision=tx.revision`。
6. callback 返回可 JSON 序列化的 `{session_id, initial_session_digest}`。不能返回 Pydantic 对象或 coroutine。框架原子完成日志、事件、Outbox。
7. `commit_resolved` 返回后校验 value 与本次 canonical 初始状态一致，再读取当前 snapshot，返回 `opened_store_revision=committed.revision`、`replayed=committed.replayed`。
8. `load_snapshot` 用**一个 SELECT** 读取 session 行并 `CROSS JOIN world_meta`（`singleton=1`），获取同一 SQL 快照的当前存储 revision；零行报 `story_session_not_found`，异常行数或模型损坏报 `story_session_corrupt`。

adapter 映射：`RevisionConflict` → `revision_conflict`；`IdempotencyConflict` → `session_open_identity_conflict`。I/O、数据库损坏等存储异常不得被宽泛吞成业务冲突。

保留唯一索引为最终防线。并发不同新请求使用同一个 expected revision 时，后排请求可先被 CAS 拒绝；不要求它一定返回 worldline 冲突。使用新 revision 的独立请求再验证唯一槽规则。

不修改 DatabaseManager authorizer，不新增连接，不写 migrations、canon.db、runtime.db 或 retrieval.db。

## T3：首轮 durable chain 与故障回归（AGT-QA，依赖 T2）

文件：

- 修改 `engine/tests/test_golden_voice_chain_durable.py`。
- 修改 `engine/tests/test_golden_turn1_durable.py`。
- 新增 `engine/tests/test_story_session_open_durable.py`。

将语音链的 `bootstrap_turn_one`、bootstrap delta/transaction 替换为真实 opener；修改相关命名与 docstring，消除“从第二轮起测”的限制说明。链路仍只替代 Interpreter/Proposer 输出，不能 mock Repository、Resolver、Commit 或取消事务。

干净数据库的顺序断言：

```text
open                   store 0→1, story=0, turn=0, turns=0, deltas=0
receive + interpret    store=1,   story=0, turn=0
AdviceCommit           store 1→2, story=1, turn=1, turns=1, deltas=1
same input retry       store=2,   model call count unchanged
close/reopen + replay  store=2,   new model instances called zero times
```

修订已有“turn_transactions 有两行”的断言为真实业务回合行数，不通过保留空引导行凑数。取消用例以 open 后的首个 intake 测试；取消只影响 intake，不删除会话、不撤销 open 生命周期事件。

Golden 首轮增加 explicit-open 测试，对 `01_committed_state.json` 的 story revision、turn、clues、secrets、pressure 期望保持不变；只有存储日志数量和 store revision 因 open 多一次而变化。保留旧 direct commit 测试，证明既有调用方不回归。

## T4：证据与工程罗盘（AGT-ARB，依赖 T3）

文件：`docs/PROJECT_STATE.json`、`docs/07_工程启动/Voice_First_Handoff_2026-09-19.md`，以及本方案执行清单。

完成实际验证后更新 W-V09 的明确子范围、验证 SHA、平台和结果；不要把整个 M1/M2/M5/M6 标成完成。下一关键路径应转向“产品组合根与 IPC/App 第一轮接线”，并登记非 Story overlays、Episode finalization、五轮和真实设备验收仍未完成。

当前 status schema 没有验证过细分状态枚举兼容性，不凭空新增状态值；沿用现有结构与可接受值，在说明字段表达局部完成。对 `project_status.py status/next` 做输出核对。

本次不改 nightly；完整五轮测试存在且经过验收后，另由 AGT-ARB 将真实入口接入受保护工作流。

# 6. 关键实现说明

## 6.1 幂等顺序与请求冻结

`DatabaseManager._commit` 已经先查幂等日志，再检查 expected revision。不能在 adapter 外先读最新 revision 并覆盖原请求，否则“首次请求 expected=0，重放 expected=2”会改变 request digest。

```text
validate and freeze original initial-session command
build canonical CommitRequest including complete initial-session payload
commit_resolved:
    existing idempotency key → verify semantic digest → return original result
    otherwise → CAS expected revision → callback insert → event/outbox → COMMIT
read current authoritative snapshot in one query
return original opened revision + current snapshot + replayed
```

request_id/trace_id 可在网络重试时变化，因为当前框架从语义 digest 中排除了它们；open_request_id、expected revision 和初始 session 不得改变。

已有 session 的同键重放不执行插入 callback，所以即使当前已经 suspended/finalized 或 story revision>0，也只回读，不错误地要求当前状态仍为初始值。验证初始请求与验证当前快照是两件事。

## 6.2 事务一致性与故障

现有 hooks 为 `before_apply`、`after_apply`、`after_events`、`before_commit`、`after_commit`。使用这些点，不新造没有实现的故障接口。

- 前四点抛异常：session、commit、event、outbox 全部回滚，store revision 不变。
- after_commit 抛异常：调用方可能收到失败，但事实已提交。用同一冻结命令恢复，得到 replayed，不能补一次新开启动作。
- cancellation 的框架语义是已入队操作等待完成后传播取消。测试取消后读取真实结果，不假设 CancelledError 代表数据库回滚。
- 重开后恢复用正常 DatabaseManager 生命周期；不能直接操作生产数据库，不杀用户正在使用的 Engine。

## 6.3 兼容与知识边界

- 不新增公共 JSON Schema、不改 Swift DTO、不广告 `story.open` capability。完整 StoryState 含隐藏事实，不能直接变成将来的 App 返回值。
- 初始会话由可信调用方提供；本次 opener 不证明 seed 的正典合法性或跨世界实体归属。未来公开入口必须通过权威 World/Character/Seed 装载和授权检查，不接受客户端上传完整 session。
- 不自动 suspend/resume；本迭代“重启恢复”指数据库重开后找回权威记录，不等于 App 生命周期接线完成。
- 保留旧首次 commit 建立 session 的能力，现有用户历史与旧单测不迁移、不重写。
- OutboxProjector 当前只重建内部事件索引；新增 open 事件可按现有机制投影，不能将此描述为全部向量/图谱检索重建完成。

# 7. 测试方案

| 测试文件 | 必须覆盖的具体断言 |
|---|---|
| `test_story_session_open.py` | 非 active、非零 story/turn/base-story、state ID 不匹配、last delta 非空、空身份、缺失或空 world_time、bool/负数/越界 revision 均在 port 前拒绝；非空无时区 world_time 合法；recover 不改变 status；原始嵌套模型在调用后被修改不影响冻结请求 |
| `test_story_session_open_repository.py` | session 初始值完整往返；13 列与 FK 合法；同键同参只一条 open；同键不同 seed/secret/base/time/expected 拒绝；trace/request ID 改变仍可重放；旧 session ID 不覆盖；四种未终结 status 阻止新开，终结 status 允许新 ID |
| `test_story_session_open_durable.py` | 同键并发仅一次持久提交；同 worldline 不同键/ID 并发最多一个成功；每个现有 fault hook 的原子性；after_commit 失 ACK 后重开恢复；仅 open 后重启仍是 turn 0；首轮后重新 open 保留 turn 1；未知 ID 恢复不写库 |
| 修改 `test_golden_voice_chain_durable.py` | 开启后从第一条 FinalizedStoryInput 走全链；lost ACK/重启不新增回合或模型调用；首轮取消先赢世界不推进；首轮 COMMIT 先赢迟到取消返回已提交 revision |
| 修改 `test_golden_turn1_durable.py` | 新增显式 open 的 Golden 首轮；fixture 的 story 期望不变；保留旧路径和非 Story overlay 拒绝 |
| 既有 `test_story_session_migration.py` | 无 schema 修改，原有迁移和备份测试保持通过，不因新行为更改 schema version |
| 既有 `test_outbox.py`；可在新 durable 文件加组合测试 | open 事件 drain 后无重复；重建内部事件索引保持同一 open 事件；不改 Canon 或权威世界 |
| 既有 advice/turn-input/turn-control 测试 | 原身份、revision、取消和已提交重放语义不回归 |

测试只能使用临时目录与现有测试 SQLite 注入方式；不能把测试注入用作生产降级。故障测试是本生命周期的五个 hooks，不冒称 #47 的八个完整游戏 kill 点已验收。

本次没有 UI 或协议变更，因此不新增模拟 UI 端到端测试。FULL_P0 仍会运行现有 Swift 测试与 Xcode 编译以查回归；真实麦克风、模型、App 和发布验收不在本迭代结果中。

# 8. 验收标准

## 8.1 功能 Checklist（候选代码 head `b848ad66`）

- [x] 干净测试世界只 open 即有 active session，story revision/turn 均为 0，零 TurnTransaction/StateDelta。
- [x] 第一条输入完整执行 Advice→Intent→Resolver→COMMIT，story revision/turn 均为 1。
- [x] domain journal 区分一条 open 和一条 turn commit，revision 连续，FK 完整。
- [x] opener 重放与 input 重放无重复副作用；覆盖首轮提交后恢复及数据库关闭重开。
- [x] 五个 fault hooks、CAS、唯一槽与并发检查均有测试并通过 FULL_P0。
- [x] 候选 diff 未修改 Canon、历史、产品 Schema、migration 或 authorizer。
- [x] 原 Golden expected 内容不变，旧 direct-commit 路径回归通过。
- [x] FULL_P0 四阶段对候选代码 head 通过，Receipt 独立提交且不复用 #201 凭单。
- [ ] 状态文档与工程罗盘更新并验收；完成后仍将 M5/W-V10 标为未验收。

## 8.2 受保护门禁与执行位置

现有门禁命令唯一来源为 `.hacf/gates/*.json`。以下只调用既有启动器或凭单 CLI，不新增脚本内嵌验收命令。均在对应隔离工作区仓库根目录运行。

```bash
python3 scripts/gate_profile.py --help
python3 scripts/agent_capsule.py show --capsule .agents/capsules/VOICE-V09-SESSION-OPEN-QA.json
python3 scripts/agent_capsule.py verify --capsule .agents/capsules/VOICE-V09-SESSION-OPEN-QA.json --cwd "$(pwd)"
python3 scripts/project_status.py status
python3 scripts/project_status.py next
```

QA 胶囊与代码 Receipt 已存在；T3 的 verify 在代码提交后运行并由 `RCP-WORK-VOICE-V09-SESSION-OPEN-QA-b848ad66f159` 记录四阶段通过。T4 文档改动使用自己的胶囊和 verify，不复用 T3 Receipt。每个切片仍须先提交实质改动、再 verify、最后独立提交 Receipt。

FULL_P0 已包含 Architecture Fitness、全体 Python/Contracts、Swift tests、Xcode App Target。候选代码的 QA Receipt 已记录四阶段全部通过。Application/Data 切片的默认档案在各自 pack 后检查并使用对应门禁；定向测试用于开发反馈。没有必要为本迭代修改门禁档案。

提交、推送、PR 和合并按执行时用户授权处理；本方案不等于这些动作的授权。若进入 PR 流程，沿用 HACF 的独立工作区、提交后 verify、凭单独立提交与合入后有证据回收规则。

# 9. 风险与注意事项

1. **revision 混用**：store revision、初始 world/character base、story revision 三者分别断言。不要改 Golden 的领域版本来凑存储版本。
2. **幂等摘要漏字段**：完整 canonical 初始 session 必须进入 operation；隐藏状态变化也应冲突，但不进入错误日志或公共事件正文。
3. **重试回滚状态**：重放结果包含当前 session，不能返回初始模型覆盖后续 turn、status、clues。
4. **权限范围**：AGT-AI 默认禁止写 infrastructure；AGT-DATA 实现具体 adapter；AGT-QA 只写测试。按角色顺序交接，不借改胶囊或放宽 forbidden 跨界。
5. **可变模型**：frozen dataclass 不冻结内层 Pydantic；必须显式复制并在排队前构造规范化数据。
6. **陈旧方案**：实施前若 main 已出现 opener 或相关表变化，先核实并调整最小差异，不能再新建第二套实现。
7. **历史文档陈旧**：进度更新必须用实际新凭单，不能依据 Issue open/closed 单独判断代码是否存在。
8. **数据回退**：无 migration；回退新增代码后持久会话仍保留在旧 schema。无已提交 turn 的 active session 可能占据 worldline 唯一槽，应记录为可恢复用户状态，不以 DELETE“修复”。
9. **范围外**：完整 seed 生成、世界/角色装载、公开 IPC、App UI、真实模型接线、Narrative/TTS 自动串联、非 Story overlays、Episode finalization、完整 Golden 五轮、发布故障、美术与新治理框架均不实施。

后续迭代出口已固定：本迭代完成后先设计可信会话初始化与最小授权 UI 投影，再将内部端口接入 Engine 组合根/IPC/App；随后扩展全领域结算和 Golden 五轮。不能把包含 secrets 的内部 StorySession 直接传给 UI 来省略授权设计。

# 10. Luna 执行清单

任务按顺序执行。角色代表职责与胶囊范围，不表示自动启动独立代理；本方案不要求委派。

- [x] **核对基线与写域**：确认 main 基线与相关写域；隔离主工作区用户未提交内容，并以候选 diff 核实没有重复实现。
- [x] **T1 / `VOICE-V09-SESSION-OPEN-APP` / AGT-AI**：Application 端口与输入验证已实现；单测证明非法输入不调用持久端口，应用层不依赖具体数据库。
- [x] **T2 / `VOICE-V09-SESSION-OPEN-DATA` / AGT-DATA**：SQLite adapter、canonical request、事务插入、单查询 snapshot 与错误映射已实现；测试覆盖持久化、幂等、CAS、唯一槽与故障路径，未改 schema。
- [x] **T3 / `VOICE-V09-SESSION-OPEN-QA` / AGT-QA**：语音链从显式 open 后的真实首轮启动；首轮 COMMIT、取消、重放、并发、重开与 Golden 首轮组合测试通过 FULL_P0。
- [x] **T4 / AGT-ARB**：状态 JSON 与 handoff 已记录验收 SHA、候选边界及后续可信初始化/组合根/产品接线；`project_status.py status/next` 已复核，未声称五轮或真机完成。
- [x] **交付**：本地候选已完成 T4 提交后 verify 与 Receipt 独立提交；记录改动、门禁、凭单与未覆盖项。无 schema/API 变化。候选交付不包含推送、PR、合并或 worktree 回收。

每个代码任务执行现有 `pack → start → 实施与提交 → verify → 凭单独立提交` 流程；分支使用 `codex/` 前缀、`target_ref=origin/main`。依赖任务合入后重新 pack 后继任务，避免继承陈旧范围或把前序代码重复计入本任务摘要。不得通过 `--allow-stale` 放行正式凭单。

**迭代完成定义：无需伪造前置回合即可创建并恢复持久会话，第一条建议能通过真实持久链提交；工程证据明确，产品接线及五轮验收仍有独立后续任务。**
