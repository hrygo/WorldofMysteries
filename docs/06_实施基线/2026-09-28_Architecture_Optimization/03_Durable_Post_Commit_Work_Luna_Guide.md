# AO-03 提交后持久工作与恢复 — Luna 实施方案

> 日期：2026-09-28；原始源码基准：`ca68d485a15bacf46ade5e703abde00598ec5251`。
> 状态：待实施；硬依赖 AO-01 的文字发布服务与只读表达查询、AO-02 的共享提交协调器。
> 实施前以两包合入后的 SHA 重新 pack。表、状态、v2 方法和新模块均为拟新增；本次未执行迁移或验收。

# 1. 问题结论

交付“领域提交有明确回执，必要后续工作可跨进程恢复”。保持现有领域幂等与事务语义，将结算、叙事、音频准备移出公开提交的长等待和会话锁。

这不是把 `await after_commit` 换为裸 `create_task`。进程终止后必须有足够的持久意图和来源重建工作，不能仅靠内存 Future。

# 2. 当前实现与根因

| 现有文件 / 符号 | 当前逻辑 | 处置 |
|---|---|---|
| `engine/application/story_session_facade.py`：`_submit_turn` | 会话锁内完成模型、commit 和 after_commit；已 committed 直接返回 | 保留预提交串行与输入身份；提交后改为工作调度 |
| `engine/infrastructure/episode_settlement.py`：`SettlingCommitPort` / `FiveTurnSettlement.settle` | commit 装饰器同步结算；异常吞掉 | 登记与执行分开，失败显式记录 |
| `engine/infrastructure/story_session_repository.py`：`commit_turn` | 原子保存 turn、delta、领域事件 | 同事务登记后续工作意图 |
| `engine/infrastructure/outbox.py`：`OutboxProjector` | 消费领域 revision 并更新检索投影水位 | 不改语义，不给任务 worker 复用其 ACK |
| `engine/infrastructure/database_manager.py` | 单 writer，已有 scoped authorizer | 新增受限工作状态写口，不放宽其他写权限 |
| `engine/infrastructure/database_schema.py` | world schema=12，有迁移前备份 | 新增下一空闲 world migration |
| `engine/tests/test_app_engine_session.py`：CP4–CP8 | 验证事实不重复及表达精确停位，重启不补产物 | 保留崩溃瞬间断言，增加“恢复后收敛”阶段 |

当前测试证明“不重交事实”，不能当作“所有后续工作最终完成”的证据。当前实现重发已提交输入会跳过结算/表达，不是补偿入口。

# 3. 目标行为

- v2 提交在领域 COMMIT 成功后即可返回，不等待模型叙述、音色探测或 TTS。
- 领域事务回滚时工作意图也回滚；不得出现任务引用未提交 turn。
- worker 崩溃、服务不可用与重复唤醒不会重复领域提交、覆盖 NarrativeBlock 或重复 Episode。
- UI 分开显示领域已保存、篇章待结算、文字待生成、音频不可用。
- 服务恢复后可显式重试表达；不能为了听声音重新提交 advice。
- 第五轮在篇章结算未完成时禁止新领域回合；前四轮允许后续回合，但所有表达读取各自冻结来源，不读最新会话替代旧 turn。

# 4. 推荐解决方案

## 4.1 持久工作表

拟新增 `013_world_post_commit_jobs.sql`；编号以实际分支为准。表 `post_commit_jobs` 位于 `world.db`，与来源 turn 一起备份。不是领域事实真相的第二份副本。

```text
job_id TEXT PRIMARY KEY
turn_id TEXT NOT NULL REFERENCES turn_transactions(id)
session_id TEXT NOT NULL
kind TEXT NOT NULL: episode_finalize | narrative_publish | audio_prepare
recipe_revision TEXT NOT NULL
source_story_revision INTEGER NOT NULL
source_world_revision INTEGER NOT NULL
input_digest TEXT NOT NULL
state TEXT NOT NULL: pending | running | retry_wait | blocked | succeeded
attempt INTEGER NOT NULL DEFAULT 0
lease_owner TEXT NULL
lease_generation INTEGER NOT NULL DEFAULT 0
next_attempt_at TEXT NULL
last_error_code TEXT NULL
result_ref TEXT NULL
UNIQUE(turn_id, kind, recipe_revision)
```

来源指针、身份、recipe、digest 插入后不可改；调度字段只能由专用工作写口更新。`input_digest` 来自已冻结场景版本、已提交 delta 与绑定 recipe，不哈希凭据。任务不保存 token、URL 密钥、原始全量 prompt 或冗余世界快照。

最小任务图：每轮 `narrative_publish`，最后一轮另有 `episode_finalize`；`audio_prepare` 依赖 narrative，语音未配置则 blocked，不阻塞文字和 Episode。实际 PCM 渲染/播放仍由原媒体协议触发，不自动向扬声器播放后台恢复的声音。

## 4.2 运行与接口

拟新增：

- `engine/application/post_commit_work.py`：任务类型、执行端口、结果与依赖判定。
- `engine/infrastructure/post_commit_job_repository.py`：登记、领取、CAS 完成、查询。
- `engine/infrastructure/post_commit_worker.py`：Engine 内有界执行器，默认并发 1。
- `engine/infrastructure/post_commit_control.py`：公开只读查询与显式 retry。
- `contracts/protocol/story_post_commit_control.schema.json`：唯一 wire。

新增 capability / 方法：

| 方法 | 输入 | 返回与语义 |
|---|---|---|
| `story.advice.submit.v2` | 与旧固定 submit 同形 | 领域 receipt、public session、replayed；无同步 delivery 承诺 |
| `story.turn.submit.v2` | 与旧 live submit 同形 | 同上；input_mode 不变 |
| `story.turn.work.get` | session_id、turn_id | settlement/narrative/audio 三个独立状态与公开原因；音频可交接时附旧类型 delivery；无 lease/内部错误 |
| `story.turn.work.retry` | session_id、turn_id、kind、retry_request_id | 幂等受理；retry_wait/blocked 的合法重试，或已完成音频的过期交接重建；不重交领域 |

以上均有 `schema_version:"1.0"`，新方法有新 schema 定义。`work.get` 中 settlement 为 not_required|pending|running|blocked|succeeded，narrative 为 pending|running|blocked|ready，audio 为 pending|running|unavailable|ready；这是公开投影，不复制数据库状态机。

`audio=ready` 必须同时满足持久 sealed 结果有效、当前 Engine registry 中存在可交接 unit；此时响应含 `delivery: TurnDeliveryView`，其中 state=ready 且 render_recipe 完整。App 从这里取得 v2 播放配方。registry 已过期/被 consume/Engine 重启时返回 audio=unavailable、reason=`handoff_expired`，不在只读查询里偷偷修改或调用 provider。用户显式重播通过 work.retry 的 audio_prepare 分支重建交接，继续使用原 recipe。

旧 v1 方法保持其同步返回行为：同一提交核心登记任务后，由兼容适配器在**会话锁外**等待本次可执行工作至完成或有界失败，再映射旧 delivery；重试/重启由 worker 独立恢复，不再次调用 Resolver。不得同时保留旧直接发布与 worker 发布两个执行者。

# 5. 详细实施步骤

1. 新增终止点测试，证明当前 COMMIT 后重启不补齐表达；保留原“不重复领域 commit”断言。
2. 新增迁移、索引、约束；在 `database_schema.py` 注册 next version。新增 `post_commit_job_write` 同步事务口，authorizer 只允许工作表调度列，不允许写世界、turn delta、canon 或投影 ACK。
3. `SQLiteStorySessionCommitPort.commit_turn` 的同一 DomainTransaction 登记确定的任务集合。已存在同 identity/digest 的记录复用，冲突拒绝，禁止吞冲突。
4. repository 实现按 session 来源顺序领取和 `lease_generation` CAS；网络 await 不发生在 SQLite 事务里。
5. worker 接入 AO-01 `ensure`、现有 Episode repository、原 seal 流程。每次先查询产物，完成后写 succeeded；崩溃在产物提交后/任务 ACK 前也能收敛。
6. 移除 `SettlingCommitPort` 中的执行职责，将 frozen BeatPlan/Narrative 发布纳入 narrative job 的 fixed handler；保留固定模板与已有 IDs。
7. 在 `StoryRuntime.open/close` 管理 worker。数据库 writer lease 获得后才能恢复上个 Engine 遗留 running；取消先停领取，再结束任务，最后关闭 DB。
8. 新增 v2 handler 与 capability；AO-02 coordinator 在冻结日志之前选择 method，日志永久保存选择，不在重试时换 v1/v2。
9. App 在回执后展示事实，查询 work 状态与 AO-01 expression；查询采用有界退避，页面关闭/切换会话停止轮询，pending 不重发领域请求。
10. 完成历史 backfill、迁移恢复、legacy 客户端测试及 CP4–CP8 新旧证据的明确更新。

# 6. 关键实现说明

## 6.1 领取、重试与取消

领取条件：state=pending，或 retry_wait 且到期；依赖产物存在且来源一致。一次短事务将 state 改 running，递增 generation，写进程 owner；完成/失败 UPDATE 必须匹配 owner+generation。单 writer lease 确保当前仅一个 Engine 拥有该 world；启动恢复只重置已失效进程的 running，不能仅靠超时抢占仍存活任务。

自动重试仅处理暂时网络错误/超时，单次失败后间隔 1、5、30 秒共最多 3 次自动重试；之后 blocked，保留公开原因和显式重试入口。配置/权限/身份错误直接 blocked。这些值是拟定本地策略，不是性能实测。实际时间只用于调度，不推进世界时钟。

显式 retry_request_id 需幂等保存，拟新增同迁移中的 `post_commit_retry_requests` 表，键为 request ID，绑定 job ID；同 ID 不同 job 拒绝。重试时保留 immutable job source，清理调度错误并置 pending，不重置产物。

## 6.2 原子性与世界修订

- 登记任务与 turn 在同一领域事务；领取、重试和 ACK 不增加 world revision。
- 叙事使用现有 post_commit_write；Episode 仍走独立领域结算事务，成功时按现有语义增加 world revision。
- Episode 执行时先 `load_by_session` 判断已完成；未完成则读当前 store revision 后 CAS finalize，并重新验证会话仍处于目标结束轮次。不能反复用旧 turn 的 store revision造成永久冲突。
- 最后一轮后的“禁止新回合”由服务端规则保证，不只禁 UI 按钮；无关会话推进 world revision时可重新读取/CAS，不能改结算语义摘要。
- Narrative 来源必须是 job 指向的 committed delta 和当时允许披露事实。后续回合更新场景不能改变前一轮表达上下文。
- 不把所有 post-COMMIT 异常吞成成功；可执行器报告结构化失败，由 repository 落盘。

## 6.3 持久音频结果与短期交接

现有 `SealedSpeechUnitRegistry` 为有界内存注册表，默认 TTL 60 秒，consume 后条目消失；仅持久化公开 render_recipe 不足以重建完整 SealedSpeechUnit。

拟在同一迁移新增 `post_commit_job_results(job_id PRIMARY KEY, format_version, payload_json, payload_digest)`，用于保存 Engine-owned sealed unit 的完整版本化数据。codec 拟放 `engine/infrastructure/audio/sealed_unit_codec.py`，仅反序列化白名单 typed 字段（含绑定/模型版本、发音映射、performance 三组类型），禁止 pickle、任意类型导入及凭据。工作 writer 对结果表仅允许 INSERT；冲突时要求 canonical 内容完全相同。

audio_prepare 顺序为：从持久 narrative 授权 → 绑定并 seal → 原子保存 sealed result 与任务 succeeded → 发布内存交接。最后一步失败不丢 sealed result。retry 遇到已有结果时不再 seal 为新版本，而是校验 turn/narrative/内容摘要和绑定安全条件后重新 publish 同一 unit。当前 provider 不支持原 voice/model revision 时明确 blocked，不擅自换声音。

只有 audio_prepare 可在“任务 succeeded 但交接已过期”时重入 pending；仅重建内存交接，不删除或更新 sealed result。其余 succeeded 工作不能被 retry 重置。启动无需把所有历史音频注册到容量有限的 registry；按用户显式需求恢复。work.get 严格区分产物持久成功与当前交接可用。

## 6.4 历史数据与回退

迁移只建表，不在 SQL 中调用模型。启动 reconciliation 按持久 turn 和产物指针建立缺失记录：

- 已存在 narrative/Episode：验证来源后置对应工作 succeeded。
- 缺表达的历史 turn：只有可确认旧场景、内容摘要、recipe 的记录才置 pending。
- 无法确定旧执行模式或 recipe：置 blocked，reason=`legacy_recipe_unknown`；不猜测用当前模型补写历史。解决需单独明确映射。
- 已有 narrative 但从未 seal 的 audio_prepare 可以读取同一文字准备首次配方；已有 sealed result 时按 §6.3 恢复原 unit/recipe，不能换身份。

world 从 v12 升级前使用现有 Online Backup。不支持直接降级数据库；回退应用版本必须保留新 schema reader 支持或采用前向修复，禁止删除任务表/覆盖升级后新事实。

# 7. 测试方案

| 文件 | 必须证明 |
|---|---|
| `engine/tests/test_post_commit_jobs.py`（拟新增） | 任务与 turn 同事务、CAS、防重复、authorizer、重试去重、未知 recipe blocked |
| `engine/tests/test_post_commit_worker.py`（拟新增） | 产物写后 ACK 前崩溃、运行中取消、网络上限、依赖顺序 |
| `engine/tests/test_sealed_unit_codec.py`（拟新增） | 全 typed 字段往返、摘要与来源拒绝、无任意类型加载、registry 过期/重启后同 unit 交接 |
| `engine/tests/test_story_session_migration.py` | v12 升级、备份验证、未知新版本拒绝、旧数据不丢 |
| `engine/tests/test_app_engine_session.py` | CP4–CP8 崩溃瞬间仍满足原断言；恢复完成后文字/Episode 收敛，无重复回合 |
| `engine/tests/test_outbox.py` | 工作 ACK 不影响 projection_outbox，检索仍可全量重建 |
| `contracts/tests/test_story_post_commit_control.py`（拟新增） | v1/v2 shapes、方法 capability、身份越界、状态投影 |
| `StorySubmissionCoordinatorTests.swift` | 冻结 method 不切换、快回执、工作 pending 不是提交失败 |

验证等待解耦时用受控事件 barrier 暂停 narrator：回执应在 barrier 释放前到达，不用固定毫秒阈值证明性能。真实延迟另测。

# 8. 验收标准

工作区根目录，当前未执行：

```bash
python3 scripts/gate_profile.py check
python3 scripts/gate_profile.py run --profile FULL_P0 --cwd . --log-dir .hacf/logs/ao-03
```

- [ ] 领域提交 1 次，必要任务与其原子出现；COMMIT 后终止不会丢任务。
- [ ] 产物提交后终止可重启收敛，无第二份叙事或 Episode。
- [ ] 最终结算 world revision 恰按真实领域事务推进，任务 ACK 不推进。
- [ ] 投影 ACK 与工作 ACK 完全独立。
- [ ] v2 客户端能从只读查询取得完整配方；registry 过期只显式恢复原交接，不重复 seal 或重生成叙事。
- [ ] v2 快回执、v1 兼容、严格 DTO 和 App journal method 保持一致。
- [ ] CP4–CP8 原子边界与恢复后收敛分别有证据；不得删故障测试求绿。
- [ ] 全门禁和迁移用例通过；真实网络恢复未测试时单列限制。

# 9. 风险与注意事项

高风险面为 migration、DB authorizer、IPC 和运行时生命周期，须明确 AGT-ARB 授权。此方案改变历史“停位”验收预期，只能新增恢复后阶段，不伪称旧记录已经验证新语义。

不引入 Redis/Celery、分布式队列、任意 job 插件，不后台自动播放，不让 App 持有数据库。不把单机重试解释为外部 provider 请求 exactly-once：模型调用可重复，但本地事实与产物发布必须幂等。

# 10. Luna 执行清单

- [ ] AO-01/02 已合入，读取其最终接口，修订胶囊与 migration 编号。
- [ ] 故障回归先建立，当前缺口可复现。
- [ ] 建表、scoped writer、原子登记与迁移验证完成。
- [ ] worker 及幂等产物检测完成，原固定表达唯一执行者成立。
- [ ] v2 / work query / retry 契约与 App 接线完成，旧接口兼容。
- [ ] 历史 reconciliation、关闭取消、重启恢复与 CP4–CP8 通过。
- [ ] FULL_P0 与凭单齐备，记录版本、数据兼容和实测限制。
