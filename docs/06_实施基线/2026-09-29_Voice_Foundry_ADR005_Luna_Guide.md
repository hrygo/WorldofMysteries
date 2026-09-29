# ADR-005 音色供给与持久绑定 — Luna 可执行方案

> 日期：2026-09-29。  
> 源码基准：`68b79c0b61e6f2044229d8d41ee291cfabb42373`；检查时本仓工作区干净。  
> 决策依据：[ADR-005](../01_总体架构/ADR-005_音色供给与铸造_v1.0.md)。  
> 交付口径：[价值目标与验收基准](2026-09-29_Voice_Foundry_价值目标与验收基准.md)。  
> 状态：本仓实施步骤、数据语义与验收标准已明确，尚未实施；真实 provider 准入单独受阻于契约与服务验证，不能提前宣称端到端可用。  
> 范围：本轮只生成方案；不修改业务代码、不执行迁移或模型任务、不提交、不推送、不创建子代理。下文所有新增文件、字段、方法和表均为**拟新增**，不是现有 API。  
> 表述：目标行为采用终态事实语态；“当前实现”专指上述基准的源码事实。

## 交付口径：价值目标

建设可持续供给、可审听验收、可恢复运行的角色音色体系，使旁白与人物拥有稳定、可区分、可追溯的声音身份。系统贯通需求授权、目录复用、候选生成、人工选优、跨文本复验、发布和持久绑定，减少人工配置及重复铸造。语音准备与剧情推进独立：缺货、服务故障或待审听时，文字正常交付，已提交世界事实保持不变。方案支持后续扩充人物与替换服务商，同时保持声音连续性、知识隔离和历史音轨完整。

## 交付口径：验收标准

1. **身份稳定**：旁白及首批 3—5 名主要人物完成真实听审；按身份逐段配音，不共用全局默认声线，不自动换声，显式替换仅影响未来片段。
2. **质量闭环**：参考确认、跨文本复验、人工身份与自然度评审、发布证据完整；证据绑定声音和模型版本，缺失、失效或撤销时拒绝正式合成。
3. **体验连续**：缺声片段显示字幕和明确状态，其他片段正常交付；音色就绪后不自动重播已读内容。
4. **可靠恢复**：重启、超时、重复请求、并发绑定及取消均不重复铸造、不覆盖有效绑定、不重复提交剧情。
5. **边界安全**：隐藏身份与未来剧情不进入提示、试听或日志；表现数据更新不改变世界事实，历史音轨保持可追溯。
6. **交付可信**：契约、迁移、客户端与测试同步交付，完整门禁通过；提供真实服务联调、冷启动严格合成及人工听审证据，明确未验收项，模拟测试不替代真实验收。

以上六条是交付团队对外承诺的结果口径。第 8 节给出逐项可执行检查，第 5 节给出实现依赖；[ADR-005](../01_总体架构/ADR-005_音色供给与铸造_v1.0.md) 的 V01–V12 是底层判定事实。任一条缺少证据即整体未完成，不以其他条目通过抵销。

# 1. 问题结论

本任务交付完整的“公开声音需求 → 目录复用 / 多候选试铸 → 真实听审 → 发布 → 持久绑定 → 分段严格合成”链路。音色创建属于准备工作，不阻塞领域提交；缺货时文字正常交付，不借用主角声线。

修复面不是单独增加一个创建接口：

1. 当前运行路径仍由全局 `voice_id` 选择声音，scope 固定为主角。
2. 持久音频任务只封装第一段主角对白，旁白被封装服务拒绝。
3. 内容寻址与生产质量资格没有贯穿 sealed unit、缓存和渲染回执。
4. 供给任务缺少可恢复的持久意图、选优、操作幂等及听审交互。
5. 音频 provider 启用与 `--voice-id` 耦合，直接删除参数会关闭音频面。

完成定义同时包含控制面和消费面：provider 已发布不等于游戏已绑定；绑定已存在不等于可正式生成；声音路由成功不等于输出已通过验收。

# 2. 当前实现与根因

## 2.1 当前源码定位

| 位置 / 符号 | 当前逻辑 | 实施处置 |
|---|---|---|
| `engine/infrastructure/voice_binding_resolver.py`：`binding_scope_for`、`resolve_voice_runtime` | 主角 scope；从给定 voice ID 探测并绑定；检查四类 pin | 改为调用方提供授权 scope；保留 pin 和冲突拒绝 |
| `engine/application/voice_casting_policy.py`：`VoiceCandidate`、`rank_candidates` | 依赖 `production_ready` 布尔值；允许 `explicit_legacy_approval`；空集抛错 | 生产准入改为证据判定；移除生产 legacy 例外；空集返回供给结果 |
| `engine/application/voice_casting.py`：`VoiceCastingService` | RESERVED→ACTIVE；`replace_for_future_render` 使用 CAS | 保留；补证据、历史修订及同事务结果登记 |
| `engine/domain/voice_identity.py` | scope 与内容寻址值对象；声音修订和目录修订已区分 | 增加独立证据引用与执行身份，不重定义既有 scope |
| `engine/infrastructure/scenarios/post_commit_handlers.py`：`ScenarioAudioPrepareHandler.execute` | 找第一段主角 character；持久化单个 sealed unit | 改为逐授权 segment 的持久音频批次 |
| `engine/application/speech_unit.py`：`SpeechUnitSealingService.seal` | speaker 必须与 binding identity 相同；speakerless narration 拒绝 | 增加显式旁白策略；加入证据准入 |
| `engine/infrastructure/audio/sealed_unit_codec.py`：`SealedSpeechUnitCodec` | 严格键集合与单 unit envelope | 增加新版本；旧版只读，不补造证据 |
| `engine/infrastructure/post_commit_control.py`：`WorkGetView` 等 | 单 delivery；get 纯读；retry 显式补交接 | 保留 v1；新增分段查询/显式准备协议 |
| `engine/infrastructure/story_runtime.py`：`StoryRuntime._compose_runtime` | 同时装配提交后 worker 和 voice handler；传 `config.voice_id` | 在当前装配点接 Foundry，不重做 AO-06 |
| `engine/infrastructure/ipc_server.py` | `args.voice_id` 决定是否调用 `AudioProviderConfig.from_env()` | provider 启用与选角分开 |
| `macos-app/WorldOfMysteries/EngineProcessManager.swift` | `voiceId` 传 `--voice-id`；`durablePostCommit` 默认 true | 保留持久路径，迁移声音配置 |
| `engine/infrastructure/database_schema.py` | world=14，逐版本迁移及迁移前备份 | 使用下一空闲版本，当前预计 015、016 |
| `engine/infrastructure/database_manager.py` | 单 Writer、受限 transaction；presentation 白名单只有 bindings/cursors | 新增窄权限 Foundry 写口，不放宽通用 SQL 权限 |
| `013_world_post_commit_jobs.sql` | job 必须关联 turn；kind 仅三种；唯一键 `(turn_id,kind,recipe_revision)` | 不把内容期 Foundry 强塞成第四种 turn job |

这些是定点读取结果，不是全仓完整影响证明。图谱工具发现仍只返回项目列表/图谱 schema 工具，未成功取得符号与 `check_index_coverage` 工具；本方案以直接源码补证。执行前重新定位调用方与所有协议解码点。

> 🧠 **From Hindsight memory (Component map)** — 提交后持久任务、sealed SpeechUnit、独立文字/音频投影和受限 Writer 是既有架构基础。方案复用这些边界；具体行为以上表源码为准。

记忆页中“App 尚未开启 durable post-COMMIT”的旧段落与当前默认 true 不一致；已写入项目记忆纠正。重新检索仍返回汇总页，不能据此宣称知识页已完成刷新。

## 2.2 上游静态事实

只读检查的 SpeechRail HEAD 为 `e48b49ff27e5352084b5b8b83e3ff9ad3c32829f`。上游存在其他未提交改动；本任务未修改该仓，也没有将工作树整体当作已发布版本。

源码入口：[voice_designs.py](https://github.com/hrygo/SpeechRail/blob/e48b49ff27e5352084b5b8b83e3ff9ad3c32829f/src/speechrail/http/routes/voice_designs.py)、[audio.py](https://github.com/hrygo/SpeechRail/blob/e48b49ff27e5352084b5b8b83e3ff9ad3c32829f/src/speechrail/http/routes/audio.py)。

| 操作 | 当前源码契约 | 实现约束 |
|---|---|---|
| 预览 | `POST /v1/voices/previews` | 返回媒体不等于注册声音；限定字节和时长 |
| 创建 | `POST /v1/voice-designs` | 不使用旧文档中的 `/voices/designs`；发送稳定 `Idempotency-Key` |
| 创建请求 | `voice_id/name/instruction/reference_text/seed/language` | voice ID 为 `[a-z0-9_-]{1,64}`；reference 20–240；seed 0–2³¹−1；当前 language 仅 `zh` |
| 查询 | `GET /v1/voice-designs/{candidate_id}` | 结果未知时先对账，不换 ID |
| 参考与验证音频 | `/{candidate_id}/audio`、`/{candidate_id}/validations/{validation_id}/audio` | 审听绑定实际资产摘要 |
| 确认 | `POST /{candidate_id}/confirm` | 参考文本变动绑定当前参考，不沿用旧确认 |
| 复验 / 人工评审 | `POST /{candidate_id}/validate` | `test_text`、`capability_key` 或 `human_review`；评审包含 validation ID、identity、naturalness |
| 发布 | `POST /{candidate_id}/publish` | 显式发送 `expected_candidate_revision`；201/200 本身不是游戏 ready |
| REST 正式合成 | `SpeechRail-Validation-Policy: require_output_pass` | 默认是 `allow_unverified`，正式路径不依赖默认值 |

当前游戏使用 Realtime TTS。上述 REST header **不证明** WebSocket 支持同样字段。SR 准入包必须提供实际 Realtime 严格范围及首音频前裁决证据；没有该能力时返回 `strict_render_unsupported` 并保留字幕，不发明参数、不绕到宽松合成。

## 2.3 根因

消费链把“已选中一个可路由声音”当作“每个身份均有已验收声音”；供给链、质量证据和逐段交付尚未成为同一套可追溯协议。长期解决方式是补齐身份、证据、持久工作与消费四个接点，不增加一条全局默认声线绕行路径。

# 3. 目标行为

- 每个角色/旁白按完整 scope 解析绑定，首用前持久保留并激活。
- 首次缺货产生一个可恢复任务；待人选优或审听时不占 worker，不自动通过。
- 人工批准绑定确切的 reference/validation 音频，不由机器评分代签。
- 正式渲染核对 voice、执行模型、证据范围；旧目录版本不冒充模型制品版本。
- 一段不可用只使该段使用字幕，其他已授权段按原顺序处理。
- 旁白使用明确的旁白身份，无 speaker 的角色段仍拒绝。
- 任务失败不修改 Commit、NarrativeBlock、世界 revision 或历史 take。
- 用户取消、并发竞争、服务超时、崩溃重启、发布后落库失败均有可判定结果。
- GET 查询无写入、无模型调用、无自动 retry；UI 刷新不会生成音频。
- 停用 Foundry 不破坏已有合格绑定；证据不全的旧绑定保持待补验。

# 4. 推荐解决方案

## 4.1 任务切分与依赖

| 包 | 范围 | 交付依赖 |
|---|---|---|
| VF-01 契约 | 请求、证据、状态、IPC、Python/Swift parity fixture | ADR-005 |
| VF-02 数据 | 表现任务、操作日记、绑定历史、证据快照、窄 Writer | VF-01 |
| VF-03 供给 | 授权需求、目录、预览、选优、确认、复验、评审、发布、恢复 | VF-01/02 |
| VF-SR 准入 | 上游映射 fixture、证据范围、Realtime 严格拒绝与冷态证据 | 可与本仓包独立推进 |
| VF-04 身份与封装 | 逐 scope resolver、旁白、证据封装/回执/缓存规则 | VF-01/02；真实启用依赖 VF-SR |
| VF-05 分段交付 | durable audio batch、逐段显式准备、顺序交接 | VF-04 |
| VF-06 App | 供给/审听 UI、配置拆分、分段消费、恢复 | VF-03/05 |
| VF-07 验收 | 内容期首批、重启/取消/缺货/严格拒绝、启用报告 | 全部 |

包表示职责和验收切片，不自动授权启动多个代理或跨仓写入。契约、迁移、App、Engine 按 HACF 角色拆胶囊，禁止用一个角色越过 forbidden。现有角色不足时由架构权限流程解决，不修改门禁绕行。

## 4.2 单一契约

拟新增产品文件：

- `contracts/schemas/voice_cast_request.schema.json`
- `contracts/schemas/voice_foundry_state.schema.json`
- `contracts/schemas/voice_identity_evidence.schema.json`
- `contracts/protocol/voice_foundry_control.schema.json`
- `contracts/protocol/voice_audio_batch_control.schema.json`

Python 声明放入拟新增 `engine/contracts/voice_foundry.py` 并由现有 `engine/contracts/__init__.py` 导出；Swift 使用拟新增 `VoiceFoundryControl.swift`、`VoiceAudioBatchControl.swift`。保持项目既有严格解码/fixture 校验风格，不假设已有自动代码生成器。

`VoiceCastRequest` 关键字段：

```text
schema_version="1.0"
request_id, request_digest, authorization_ref
scope={owner_id,world_id,worldline_id,presentation_identity,phase,locale}
persona_revision, usage=dialogue|narration
public_traits[], voice_description
reference_text, validation_text
provider_instance, requested_execution_scope
budget={candidate_count:1..4, timeout_ms, max_audio_bytes}
origin={kind:content|scene, source_ref, source_revision}
```

服务器从可信 session/content context 构造 scope 与授权，拒绝客户端伪造 owner/world。`request_digest` 由服务器对规范化 payload 计算；客户端提供值仅用于一致性核对。参考和复验文本必须不同，均经过可公开内容授权。

`VoiceIdentityEvidence` 引用与核验快照：

```text
evidence_id, evidence_digest, provider_instance, voice_id, voice_revision
execution={model_id,model_artifact_revision,variant,locale,
           validation_policy_revision,processing_fingerprint}
reference={status,audio_digest,text_digest}
output={status,validation_id,audio_digest,text_digest}
human={identity_status,naturalness_status,review_id,
       reference_audio_digest,validation_audio_digest}
publication={state,published_revision}
rights={allowed_usages,scope_ref}
created_at, expires_at?, revoked, cached_playback_policy
```

目录 revision 单列，不能填入 `model_artifact_revision`。缺任何必需证明返回 `evidence_incomplete`，不填默认 pass。游戏侧摘要用于防错与追踪，不自称密码学签名；信任来自配置的 provider、鉴权和实际核验。

## 4.3 状态与接口

任务状态唯一集合：

`requested / previewing / awaiting_selection / provisioning / validating / awaiting_review / published / binding / ready / failed / cancelled`

`awaiting_reference_confirmation` 用 `provisioning` 阶段的 `required_action=confirm_reference` 表达，避免 provider 状态与任务枚举混用。调度属性独立：`retry_at`、`attempt`、`operation_status=prepared|unknown|confirmed|rejected`、`reason_code`、`task_revision`。

拟新增 IPC 方法如下，全部基于现有认证 IPC 注册；下列名字不是已发布能力：

| 方法 | 操作与幂等 |
|---|---|
| `voice.foundry.request` | 登记持久需求，返回 task；同 request ID/同 digest 重放，异 payload 冲突 |
| `voice.foundry.get` / `list` | 纯读；list 按授权 world/scope 过滤并分页 |
| `voice.foundry.select` | 候选 ID + 预览摘要 + expected task revision |
| `voice.foundry.confirm_reference` | candidate revision + reference 音频/文本摘要 |
| `voice.foundry.validate` | 显式接受复验任务，冻结测试文本和目标 execution scope |
| `voice.foundry.review` | validation ID + 两个音频摘要 + identity/naturalness 结论 |
| `voice.foundry.publish` | expected candidate/task revision；接受后台发布工作 |
| `voice.foundry.retry` / `cancel` | command ID + expected task revision；返回 accepted/replayed/conflict |
| `voice.binding.replace` | 完整 scope、目标 voice/evidence 引用、expected binding revision |
| `voice.audio.batch.get` | 纯读逐 segment 状态和已持久 manifest |
| `voice.audio.segment.prepare` | 显式准备一个未消费段的交接，command ID 幂等；不重新生成叙事 |

每个写方法有 command ID 与 payload digest；相同 command 重放返回原接受结果并附当前任务视图。scope 越界统一拒绝，错误正文不透出另一个世界的对象。GET 不替代 provider 查询恢复，恢复由 worker 进行。

# 5. 详细实施步骤

## S0 · 固定实施基线和反例

核对分支与未提交内容；以实际基线重新生成胶囊。确认 ADR 未发生后续修改、world migration 015/016 是否空闲。新编号被占用时顺延，不覆盖既有迁移。

先建立第 7 节反例：两名说话者加一段旁白、没有绑定、已绑定但缺证据、相同键的发布超时、取消与发布回调竞争。原测试必须在旧实现明确失败，不能用忽略 scope/voice/model 的 fake 掩盖错误。

## S1 · 契约与授权需求

修改 `engine/application/context_compiler.py`、`context_plan.py` 的实际授权出口；拟新增 `engine/application/voice_cast_request.py` 承接已授权内容。

需求构造器只接受授权后的表现快照，不能接受任意 Character/World 对象。公开 trait 由内容管线维护，默认不增加 LLM 推断调用。自然语言描述来自已授权字段；不靠关键词过滤器猜测隐藏身份。

旁白内部身份使用保留命名空间 `presentation:narrator`，配合完整 world/worldline scope；角色 ID 禁止占用该命名空间。NarrativeBlock 的 narrator `speaker_id` 仍为 null，不把内部旁白 ID 写成新的故事人物。

修改 `performance_plan.schema.json` 与 `engine/contracts/models.py` 中对应表达模型时，保留旧版读取：新增明确 v2 分支并携带 binding/evidence 引用，不向严格 v1 payload 偷加字段。Schema、Python、Swift 和 IPC capability 同批更新。

完成条件：同一 fixture 被三端接受或同样拒绝；缺少授权的 narration 和 dialogue 都无法构造需求。

## S2 · 持久化与 Writer

拟新增 `015_world_voice_foundry.sql`，目标表：

| 表 | 主要键与职责 |
|---|---|
| `voice_foundry_tasks` | PK task_id；request ID 唯一；完整 scope、payload digest、阶段、task revision、last confirmed stage、cancel_requested |
| `voice_foundry_candidates` | PK `(task_id,candidate_id)`；slot、seed、recipe、preview asset digest、provider candidate ID/revision、参考和复验资产引用 |
| `voice_foundry_operations` | PK operation_id；UNIQUE `(task_id,stage,attempt_identity)`；冻结 payload、idempotency key、unknown/confirmed/rejected 及 provider result ref |
| `voice_foundry_commands` | PK command_id；请求摘要与接受结果，覆盖选优/听审/取消等命令重放 |
| `voice_evidence_snapshots` | PK `(provider_instance,evidence_id,evidence_digest)`；不可变核验快照，动态撤销观察另存 |
| `voice_binding_revisions` | PK `(binding_id,binding_revision)`；不可变绑定快照与 evidence 引用 |

`voice_bindings` 保留当前绑定索引，新增 nullable evidence 引用；历史缺失值表示 unevaluated。迁移将当前绑定复制为一个已知历史快照，不编造迁移前未保存的旧修订。分叉点早于可用历史时显式返回 `binding_history_unavailable`，不拿当前版本代替。

拟新增 `VoiceFoundryTransaction` / `DatabaseManager.voice_foundry_write` 及 repository。权限限上述表、必要绑定变更；禁止写 domain/world revision、Canon、turn 和 NarrativeBlock。证据与历史表 insert-only；任务只更新状态列。写入 callback 不执行网络 I/O。

绑定 CAS、history 插入、task→ready 在同一 `world.db` transaction 内提交；不能分别提交后声称原子。复用一个内部绑定 SQL 实现给现有 repository 和 Foundry transaction，避免两套 rebind 规则。

活动需求去重以完整 scope + persona revision + request digest + provider 为键；failed/cancelled 可以显式新建，但存在 unknown operation 时必须先对账。不同 request ID 命中同一活动需求返回既有 task，不多开铸造。

runtime 队列/租约可重建；操作 intent、attempt identity、取消标记和任务修订在 world 持久。仅持有该 world 的 Engine 独占 Writer 租约者执行 worker。runtime 清空后以 world task revision 拒绝旧 ACK，查询 provider 收敛未知操作，不因租约丢失重铸。

完成条件：崩溃后重启不丢幂等映射；更新表现数据不改变 world revision；权限反例均拒绝。

## S3 · Provider adapter 与准入

拟新增 `engine/application/voice_foundry_ports.py`、`engine/infrastructure/audio/voice_foundry_adapter.py`。端口能力明确列出 preview/create/query/confirm/validate/review/publish，以及 accepted locales、asset limits、strict rendering 和 evidence fields。

按 §2.2 映射实际 SpeechRail API。游戏 locale `zh-CN` 只在 adapter 的显式支持表映射为上游 `zh`；不从 `"language":"zh"` 推断其他 locale 已获验收。其他 locale 返回 `unsupported_locale`，不得静默翻译。

正式候选当前创建请求不包含预览音频导入字段，故采用“保存选中配方 → 创建新参考 → 再次确认参考”路径，不假设 seed 能复制预览。人工听审基于正式参考与实际复验资产。

创建超时通过稳定 candidate/voice ID、幂等键和受支持的查询对账。取消不是调用猜测的删除端点；没有确认的远端取消能力时，只停止本地后续步骤并收集迟到结果。

真实接线的准入 fixture 包含：candidate 生命周期、201/200 发布 envelope、同键冲突、失效 revision、证据读取和实际执行身份、冷态严格成功、错误证据的首音频前拒绝。上游字段不足即 `provider_contract_unsupported`；本仓单测可用 fake 完成，上游扩展由独立授权任务负责。

完成条件：adapter 不 import 上游代码；未知能力拒绝；正式渲染不回退为 allow_unverified。

## S4 · Foundry 编排与恢复

拟新增 `engine/application/voice_foundry.py`、`engine/infrastructure/voice_foundry_repository.py`、`voice_foundry_worker.py`、`voice_foundry_control.py`。

保留 `VoiceCastingPolicy` 的确定性排序和同场可区分约束；将新生产路径上的 boolean readiness 改为准入对象：qualified、needs_runtime_prepare、blocked。冷态可加载不等于缺证据，两个原因分开。

目录已命中合格声音则直接进入 binding；无合格候选返回 supply_required 并登记一次任务。明确鉴权失败、撤销、unsupported locale、用途不符不得转换为自动铸造循环。已绑定角色不重新排序。

默认候选最多 4、provider 并发 1；单个候选失败不覆盖兄弟卡。预览/验证预算由请求和服务上限取更小值；没有 provider 任务调度能力时，只在游戏互动空闲窗口启动新重任务，不承诺能够抢占已运行模型。

每次外部副作用遵守：

```text
持有 world Writer 所属权
transaction: 校验 task revision/取消状态；持久记录操作 intent 和固定请求
transaction 结束
adapter 调用 / 对账
transaction: 校验操作身份和 task revision；保存确认结果
若 cancel_requested：不绑定，不自动发布下一步
若发布成功：持久结果 → 核验 → 原子绑定/历史/task ready
若结果未知：operation=unknown，按原请求对账
```

transport 暂态错误自动重试最多 3 次，退避 1/2/4 秒并受总 deadline 限制；这属于实现默认值而非性能实测。重试复用同一操作身份。人工拒绝或 provider failed 终态不自动重试；重新铸造通过显式新任务，并链接旧任务。

`awaiting_selection`、`awaiting_review`、待参考确认均不占 worker。等待人工不计入执行 deadline；资产过期后 required_action 指向重新生成/确认，不继续使用失效摘要。

## S5 · 证据、旁白与安全封装

修改 resolver：输入由“session + voice_id”改为“授权 scope + usage + execution requirements”。已有 binding 先按 scope 读取，再核验其 provider/voice；目录与之冲突时拒绝，不替换。

拟新增 `engine/application/voice_evidence.py`，统一判定规则供选角、seal、render 使用。证据是否可用于新合成与历史缓存是否可播放分别返回。动态撤销由 provider 状态观察控制，不修改旧证据快照。

修改 `AudioDisclosureAuthorizer` 和 `SpeechUnitSealingService`：角色段要求 speaker 与 scope 相同；旁白段要求 segment type 为 narration、对应文本已经提交且获准公开、scope 为批准的旁白策略。不得简单删掉所有 `speaker_id is None` 检查。

`SealedSpeechUnit` 新版本包含 evidence ID/digest、完整 execution scope、明确 model artifact revision、catalog revision。同步修改 codec、`voice_control.py`、`voice_runtime.py`、`realtime_tts.py`、`render_receipts.py` 和所有严格请求/回执比较。逐句效果只能用 provider 声明支持的字段。

证据 fingerprint 进入新的 render recipe/缓存键；旧配方不能与新证据配方碰撞。保持项目既有 world-key 隔离的 HMAC 方案，不退回公开 SHA 缓存键。音频字节可复用也必须重新判断播放许可，不能靠缓存绕过撤销。

首 PCM 前由 provider 严格 gate 拒绝身份不匹配；终态回执负责确认实际产物。若 provider 只有末尾回执而无首块前锁定证明，当前 unit 全部隔离缓冲至回执核验后才交付；达到既有字节上限即失败，不用无界缓存解决。不能在音频已播放后才声称实现“首块前拒绝”。

完成条件：旁白正常封装，伪造 speakerless 对白拒绝；正确 pin 但缺证据也拒绝；错误模型无可交付 PCM。

## S6 · 持久分段音频，不覆写旧单段结果

拟新增 `016_world_voice_audio_batches.sql`、`engine/application/voice_audio_batch.py`、`engine/infrastructure/voice_audio_batch_repository.py`。表 `voice_audio_batches` 保存不可变来源 `(turn_id,narrative_block_id,recipe_revision)`；`voice_audio_segments` 按 `(batch_id,segment_index)` 保存授权身份、绑定/证据引用、准备状态、结果 ref 与 generation。

原 `post_commit_jobs` 保持一个 `audio_prepare` 父任务；新 recipe 生成 batch manifest，其完成只证明分段计划持久化，不表示每段 ready。现有 `post_commit_job_results` 单 unit 数据保持原样，不覆盖历史。新 batch 用独立版本 codec，不把 list 塞进旧 `unit` 字段。

`ScenarioAudioPrepareHandler.execute` 遍历 NarrativeBlock 原顺序：

1. 逐段授权，对非可发声段记录 skipped。
2. 解析角色或旁白 scope；合格绑定封装 unit，缺货登记需求并记录 waiting_voice。
3. 持久保存结果；部分失败保留其他段结果，最后记录稳定 manifest。
4. 未在播放窗口内的 unit 不批量塞满内存 registry；持久封装与可立即交接分开。

新 `voice.audio.batch.get` 返回各段 `waiting_voice|sealed|handoff_ready|unavailable|skipped`，不调用 provider。`voice.audio.segment.prepare` 为一个确定 segment/generation 接受有界交接工作；只有当前 registry 有对应 unit 时暴露 ready。get 不因 registry 过期自动 republish。

App 按原 segment index 前进，缺货段显示字幕并记本次播放已跳过；稍后音色 ready 不回头自动播。未消费的未来段可在用户正在进行的播放会话内显式 prepare；重启或旧页面重入不自动开声。用户重播生成新播放 generation，新合成使用独立 take。

保留 `story.turn.work.get` v1 形状及语义；新 App 协商 batch capability 后使用新方法。旧客户端不能理解多段时继续文字和既有合法单段历史交接，不随机选一段冒充整批成功。

完成条件：角色 A、角色 B、旁白按顺序解析各自身份；一个缺货不阻塞另外两段，不重复 Commit 或 NarrativeBlock。

## S7 · App、启动和真实用户流程

在 `EngineLaunchConfiguration` 与 `ipc_server.py` 新增独立 audio-enabled 配置，provider 有配置即可启动音频面；删除产品对 `voiceId` 的依赖。未配置 provider 的纯文字模式仍正常。

旧 `--voice-id` 保留为显式迁移输入：提示选择唯一作用域、核验并确认绑定后完成迁移；不自动套到每个人物。旧未知证据不赋予资格。更新 App 跨进程 driver 的启动契约。

拟新增 `VoiceFoundryModel.swift`、`VoiceFoundryPanel.swift`。接入现有 App/EngineIPCClient 与 StorySessionModel：

| 状态 | 用户动作 |
|---|---|
| previewing | 显示各卡进度；允许取消任务 |
| awaiting_selection | 试听各候选；选择一张 |
| provisioning + confirm_reference | 试听实际新参考、确认文案 |
| validating | 显示真实进度，不显示“可配音” |
| awaiting_review | 独立播放参考和复验音频，提交身份/自然度结论 |
| published / binding | 已发布，正在绑定；无自动播放 |
| ready | 后续句可用 |
| failed | 具体原因；仅展示 provider/任务允许的重试或新建动作 |
| cancelled / unknown | 已停止后续步骤 / 正在核实远端结果，不虚构资产已删除 |

听过标记至少绑定本次 asset digest 与实际播放器完成/用户确认，禁止只点开页面就自动填 pass；人类仍负责最终结论。状态回包带 task revision 和 request generation，迟到回包不能污染新选择。

短操作返回接受回执，长任务不占 IPC request。UI 轮询只读、停止于待人操作/终态/页面关闭；恢复从持久 task 读取，不保存秘密到 UI 日志。候选媒体经 Engine 媒体通道交付，App 不绕过 Engine 读取 provider 私有 URL。

`StorySessionModel.swift`、`StorySessionPanel.swift` 和 `Media/VoiceTurnController.swift` 接入分段状态及播放次序，保留现有逐段文字 reveal、打断、设备切换和独立文本可用性。

# 6. 关键实现说明

## 6.1 CAS 与取消竞争

取消 transaction 将 `cancel_requested=true` 并增加 task revision。绑定 transaction 必须在同一 Writer 内重新检查该标记：

- 取消先提交：迟到发布结果可登记，但不能绑定。
- 绑定先提交：取消返回 `already_ready`，不偷偷撤销声音；用户另发显式换声命令。
- 新旧 worker 结果都带 operation ID、task revision；旧结果最多记入操作日记，不能覆盖当前阶段。

用户 review 命令只允许当前 candidate revision + validation ID + 两份音频 digest，任一变化均 `stale_review`。用户确认不是服务验收结果；provider 必须成功保存并返回对应记录。

## 6.2 既有绑定、模型升级和目录变化

声音未变、模型升级时，原证据对旧模型仍是历史记录，对新范围无资格。重新验证后通过显式 revision 更新批准未来执行范围，不隐式替换声音。更新后的 sealed unit 使用新证据键。

目录变化不自动全量重铸或作废所有质量报告。实际绑定无法按 pin 执行时，该段 unavailable，提供复验/迁移入口。不能把新的 catalog revision 写入旧 `model_revision` 并继续使用旧 sealed digest。

## 6.3 缓存、旧格式和数据回滚

旧 codec 保留验证读取，用于历史审计/允许的缓存播放；没有证据的旧 unit 不能再次触发生产合成。新 decoder 不通过添加默认证据“升级”旧记录。

应用回滚前检查旧二进制是否支持新增 schema；拒绝未来 schema 是安全结果，不修改 `user_version` 伪装兼容。迁移备份只用于明确的数据恢复流程，不在启动时自动回退并丢弃迁移后用户数据。

## 6.4 明确限制

本方案的首个真实 adapter 是已协商能力范围内的 SpeechRail VoiceDesign。克隆、导入、其他 provider 使用同一资格接口，但不顺带建设完整录音采集、训练或云服务 UI。系统保留多来源准入能力，不以实现首发路径为由改变 ADR 的来源中立决策。

自动初筛首版采用 provider 质量结果与公开 metadata；未取得有效声学指标时展示“未测量”，不虚构 trait 分数或新增 embedding 模型。同场最终可区分性由内容验收覆盖。

# 7. 测试方案

所有拟新增测试与改动一并交付。禁止测试自动使用真实模型、用户目录、录音或凭据。

| 测试文件 | 必须覆盖的断言 |
|---|---|
| 现有 `engine/tests/test_voice_identity.py`、`test_voice_casting.py`、`test_voice_casting_policy.py` | 完整 scope、CAS、已有绑定硬锁；legacy 生产例外拒绝；空目录与 policy blocked 区分 |
| 拟新增 `engine/tests/test_voice_foundry_contracts.py`；`contracts/tests/test_voice_foundry_control.py` | extra 字段拒绝、三端相同 fixture、写命令幂等、scope 越权、合法按钮与阶段一致 |
| 拟新增 `engine/tests/test_voice_foundry_repository.py` | 14→新版本备份、旧绑定 unevaluated、同键异 payload 冲突、原子绑定历史、world revision 不变、SQL authorizer 拒绝越权 |
| 拟新增 `engine/tests/test_voice_foundry_worker.py` | preview 单卡失败；待人操作不占 worker；create/publish 响应丢失；重启与 runtime 索引清空；原操作恢复；取消先赢/绑定先赢；迟到结果 |
| 拟新增 `engine/tests/test_voice_foundry_adapter.py` | 实际路由与 payload、上游中文限制、201/200 不等于 ready、复验换文本、unknown 字段/能力拒绝 |
| 现有 `engine/tests/test_speech_unit.py`、`test_audio_disclosure.py` | 批准旁白可封装；speakerless character 拒绝；hidden trait 不出站；缺证据、错模型、错 locale 拒绝 |
| 现有 `engine/tests/test_speechrail_render_receipts.py`、`test_voice_runtime.py` | strict 冷态路径；回执范围不符；首块前拒绝；末尾核验模式不提前暴露 PCM；缓存撤销规则 |
| 现有 `engine/tests/test_post_commit_runtime_handlers.py`、`test_post_commit_control.py` | 批次来源精确匹配；GET 不写不调 provider；一个缺声段不使 narrative 降级；旧 v1 payload 不破坏 |
| 拟新增 `engine/tests/test_voice_audio_batch.py` | A/B/旁白顺序；partial batch 重启；同 command 幂等；registry 过期；不自动重播已跳段；新 generation |
| 现有 `engine/tests/test_database_manager.py`、`test_audio_take_store.py`、`test_audio_track_repository.py` | 新窄 Writer；历史 take/track 引用不变；旧 schema/codec 可读且不新增合成资格 |
| 拟新增 `macos-app/WorldOfMysteriesTests/VoiceFoundryControlTests.swift`、`VoiceFoundryModelTests.swift` | DTO parity、真实听审输入、迟到回调隔离、轮询停止、操作可达、资产变化清空旧确认 |
| 现有 `StoryPostCommitControlTests.swift`、`StorySessionModelTests.swift`、`VoiceTurnControllerTests.swift` | 新 capability 分支、文字正常、分段顺序、取消、关闭/重启不自动播 |
| 现有 `engine/tests/test_app_engine_session.py`、`test_voice_turn_e2e.py` 与对应 `fixtures/*driver.swift` | audio-enabled 配置、无全局 voice ID 的启动、Commit 不重复、缺货文字可用；真实设备用例保持显式启用 |

故障点至少包含：intent 落库后调用前、provider 成功后 ACK 前、发布记录落库后绑定前、绑定 transaction 中、registry handoff 后、取消与返回同刻。每例同时检查 DB、调用次数、音频是否可交付，不只断言错误码。

# 8. 验收标准

## 8.1 已有可执行入口

工作位置为实施工作区根目录。命令引用受保护档案，不在新脚本或胶囊内复制其验收命令：

```bash
python3 scripts/gate_profile.py show --profile FULL_P0
python3 scripts/gate_profile.py check
python3 scripts/gate_profile.py run --profile FULL_P0 --cwd . \
  --log-dir .hacf/logs/voice-foundry \
  --json-out .hacf/tmp/voice-foundry-full-p0.json
```

以上 CLI 参数和档案已静态核实，**本轮未执行门禁**。执行者先创建日志/报告父目录，复用工作区短 TMPDIR 与 SPM 租约。FULL_P0 覆盖架构、Python/契约、Swift 和 Xcode App Target；检查实际阶段结果及是否意外跳过新增用例。

`VOICE_P0` 当前仅执行架构检查和 `test_audio_adapter.py`，不能证明本任务完成。若为本任务新增聚焦门禁，由 AGT-ARB 修改受保护档案并刷新 registry；否则直接使用 FULL_P0，不为了快捷另造脚本。

## 8.2 完成清单

- [ ] ADR V01/V02：引用稳定性与质量证据分别核验，正确 voice + 错模型仍拒绝。
- [ ] ADR V03：正式 reference 与跨文本输出都有真实人工听审记录；机器结果不代签。
- [ ] ADR V04：实际 Realtime 严格协议有契约与冷态验证，不能用 REST 成功替代。
- [ ] ADR V05：新人物无音色时 COMMIT/文字保留，不借主角声线。
- [ ] ADR V06/V07：部分成功、崩溃、并发、取消、deprecated/revoked 均收敛。
- [ ] ADR V08：换声只影响未来边界；历史与分叉使用准确版本。
- [ ] ADR V09：授权反例覆盖请求、日志、错误和审听材料。
- [ ] ADR V10/V11：删除运行索引后恢复；旧数据不丢、回滚不绕过 gate。
- [ ] 新角色、第二角色、旁白均有生产调用方，不能只在测试里连通。
- [ ] audio-enabled 与角色绑定解耦；旧参数迁移有明确反馈。
- [ ] 所有新 schema、Python/Swift DTO、IPC capability、codec/cache revision 同步。
- [ ] FULL_P0 实际通过，记录 source SHA、日志和凭单；未通过不能用文档检查替代。
- [ ] ADR V12：获准运行真实服务后，旁白与 3–5 个人物完成内容验收，记录真实模型/服务身份、试听素材、人工结论和资源竞争测量。

本方案生成时上述项目均未执行。不做未经授权的真实合成、模型加载、服务升级、跨仓修复或自动发布。

# 9. 风险与注意事项

| 风险 | 处理与停止边界 |
|---|---|
| 上游缺少可锁定模型制品/证据读取/Realtime 严格 gate | adapter fail-closed；本仓 fake 和契约包可交付，生产启用停止在 VF-SR |
| schema 编号与其他工作并行 | 重新核实下一空闲编号并迁移测试，不重写他人迁移 |
| 把 Foundry 泛化成全项目任务平台 | 不重构 post_commit_worker 为通用框架；复用事务/幂等模式，保留内容任务独立生命周期 |
| 分段批次造成接口扩大 | 使用独立 capability/协议，保留旧纯读行为；不改输入提交或领域 resolver |
| 历史绑定修订不足 | 如实 unavailable；不伪造分叉前版本 |
| 听审长期等待 | 持久待审、字幕可用，不自动审核、不占执行槽 |
| 预览争抢 TTS | 默认串行、空闲窗口、有界预算；并行优化以测量为依据 |
| 私有参考泄露 | provider 持有原始证据；游戏只保存必要资产引用和摘要；不把秘密写到 recipe 或日志 |
| 已有系统音色成为隐式 fallback | 普通 UI 提示与角色生产权限分离，测试覆盖禁止旁路 |

不处理世界模拟、Canon 内容制作、AgentScope 改造、通用模型训练、跨平台兼容、全局 UI 重设计、自动安装/更新 SpeechRail。需要上游改动时交付缺口证据与独立方案，不在本任务顺手修改关联仓库。

# 10. Luna 执行清单

1. **基线与反例**：复核本仓状态、ADR、迁移编号和上游 fixture；在第 7 节目标测试中复现全局声音/首段主角/旁白拒绝等缺口。完成条件：每个缺口有可定位失败断言。
2. **VF-01**：在 `contracts/`、Python 与 Swift 落请求、证据、状态和 IPC parity。完成条件：同一 fixture 三端同判，未知字段和 scope 伪造拒绝。
3. **VF-02**：新增迁移、repository 和窄 Writer。完成条件：备份、幂等、取消 CAS、绑定历史与原子 ready 均通过，世界 revision 不变。
4. **VF-03 adapter**：按实际 `/v1/voice-designs` 路由完成 fake/recorded 映射。完成条件：创建与发布未知结果可用原身份恢复，缺能力明确拒绝。
5. **VF-03 worker**：实现目录复用、多候选、重新确认、机器复验、真实听审与发布。完成条件：等待人工不占槽、失败不放宽、重启不重铸。
6. **VF-04**：改 resolver、sealing、codec、render/cache/receipt。完成条件：每个身份独立，旁白有授权，旧证据不隐式升级，错误执行范围无可交付音频。
7. **VF-05**：实现 batch 持久化及纯读/显式准备协议，接 `ScenarioAudioPrepareHandler`。完成条件：三段不同身份按顺序、部分缺货、registry 失效与重启均可验证。
8. **VF-06**：接 App 控制/听审 UI、audio-enabled 和分段播放。完成条件：人类确认绑定实际资产，迟到回包隔离，文字不中断，旧已读段不自动重播。
9. **VF-SR**：在已有授权范围内核实真实上游准入；缺失则提交具体契约缺口，保持生产关闭。完成条件：真实接线的每个字段与错误都有可复核来源，不能凭 mock 宣称完成。
10. **VF-07**：执行 FULL_P0、恢复矩阵及获准的首批内容验收，更新接续文档。完成条件：逐项报告 ADR V01–V12、通过/未通过/未执行、源 SHA、证据与剩余阻塞；按授权范围完成 HACF 凭单及后续交付。
