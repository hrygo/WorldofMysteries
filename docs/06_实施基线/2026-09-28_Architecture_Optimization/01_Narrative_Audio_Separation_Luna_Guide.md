# AO-01 结构化叙事与音频解耦 — Luna 实施方案

> 日期：2026-09-28；源码基准：`ca68d485a15bacf46ade5e703abde00598ec5251`。
> 状态：待实施；无前置包。完整通路仍采用当前同步提交方式，异步恢复由 AO-03 单独交付。
> 本文新增符号均为拟新增设计；测试、门禁与真实服务验收未执行。共同约束见 [方案集](README.md)。

# 1. 问题结论

交付“领域事实提交后，先生成并保存结构化文字叙事，语音可选”。关闭语音服务不能阻止文字产物；旁白不能被合并成角色对白。

修复范围包括 Engine 表达编排、只读文字查询和真实会话面板展示；不建设完整 Story Book，不引入后台任务，也不改领域裁决。

# 2. 当前实现与根因

以下路径相对仓库根目录，均已核对：

| 文件 / 符号 | 现状 | 处置 |
|---|---|---|
| `engine/infrastructure/story_runtime.py`：`_DeliveryCoordinator.after_commit` | 先检查 voice，再构造 narrative compiler；音色解析也在叙事前 | 改为先叙事持久化，再执行音频分支 |
| 同文件：`_build_facade` | live 模式关闭 `frozen_expression` | 保留防双写，但让 live 文字不依赖音频 |
| `engine/ai/live_turn_workers.py`：`LiveNarrativeCompiler.compile` | 返回 `narration + newline + speech` | 返回强类型候选，不丢角色语义 |
| `engine/infrastructure/audio/voice_delivery.py`：`TurnDeliveryPipeline.deliver` | 整段写入一个 character segment，固定 seal index=0 | 拆开发布和音频准备；使用持久 segment 索引 |
| `engine/infrastructure/narrative_block_repository.py`：`publish` | 同 turn 同内容幂等；不同内容拒绝 | 原样保留不可变语义 |
| `engine/application/audio_disclosure.py`、`speech_unit.py` | 从已持久叙事重新授权与 seal | 复用，不绕过 |
| `contracts/schemas/narrative_block.schema.json` | 已支持 narration / character segment | 复用现有模型，不另定义持久叙事格式 |
| `engine/application/story_session_facade.py`：`TurnDeliveryView` | wire state 仅 ready/unavailable | 保持旧枚举，另增查询契约 |

复现：配置 live model，不配置 voice；提交成功后检查本轮 narrative。第二条复现：模型返回独立旁白和对白，检查持久 segment 类型与 spoken_text。

# 3. 目标行为

- live 回合 COMMIT 后生成 `NarrativeBlock`，没有语音仍能在真实会话面板读取。
- 固定模式维持已有固定表达，禁止再生成第二份叙事。
- 新叙事默认按有内容的 narration、character 顺序构建；speaker 由可信会话身份绑定，模型不得指定任意 speaker ID。
- 仅对白 segment 进入本包的角色 TTS；旁白保持文字，不新增旁白音色策略。
- 若已有 NarrativeBlock，先读取并复用，禁止再次调用模型后以新内容覆盖。
- 叙事失败返回表达不可用，保留领域事实；音频失败仅影响音频。

# 4. 推荐解决方案

拟新增 `engine/application/narrative_publication.py`：

- `NarrativeCandidate(narration: str, speech: str)`：内部不可变候选，继续遵循当前长度与非空约束。
- `CommittedNarrativeService.ensure(turn_id, source)`：先读取既有叙事；无既有产物才调用编译器并发布；source 必须来自该 turn 的已提交增量。
- `NarrativeReadPort` / `NarrativePublishPort`：复用 SQLite repository，AI 不获得写口。

`TurnDeliveryPipeline` 改为消费已发布的 NarrativeBlock 与显式 `segment_index`；不再自己调用模型或把两类文本揉成一个 segment。

拟新增 `story.expression.get` capability 和只读方法，输入 `{schema_version:"1.0",session_id,turn_id}`；在 `contracts/protocol/story_expression_control.schema.json` 定义唯一 wire：

```text
response:
  schema_version = "1.0"
  session_id, turn_id
  narrative_state = pending | ready | unavailable
  segments = [{type: narration|character, speaker_display_name?: string, text: string}]
  reason?: stable public code
```

ready 必须有已持久化且经玩家披露投影的 segments；pending/unavailable 返回空数组。不得直接 dump 内部 NarrativeBlock、隐藏身份或授权清单。没有持久失败记录时返回 pending，不臆测失败；unavailable 只用于当前明确不能生成的能力状态。该查询不生成内容、不 seal、不调用外部服务。

旧 submit 的 `delivery` 保持音频语义：仅有文字时仍为 unavailable，并给出准确音频原因；App 使用新查询显示文字，不扩充旧 state 枚举破坏严格 DTO。

# 5. 详细实施步骤

1. 在 `engine/tests/test_story_runtime.py` 增加无 voice 的 live 受控模型回归；断言 COMMIT 一次且文字存在。
2. 在 `live_turn_workers.py` 改编译器返回值；同步固定 factory 的 compiler adapter，统一返回候选接口。不改解释器/提案器。
3. 新增 `narrative_publication.py`，注入现有 repository；已有产物优先读取，检查 session、turn、source revision 一致。
4. 修改 `voice_delivery.py`，从持久角色 segment 选择 seal 索引；文字发布移出音色绑定前置条件。
5. 修改 `story_runtime.py`，固定表达只有原发布者，live 表达只有新服务；音色错误发生在文字之后。
6. 新增查询 schema、`engine/application/story_expression.py`、`engine/infrastructure/story_expression_control.py`，在 `story_runtime.py` 注册；新增 schema 为拟新增。
7. 在 `macos-app/WorldOfMysteries/StoryExpressionControl.swift`（拟新增）建立严格 DTO；`EngineIPCClient.swift` 增加 capability 检查；`StorySessionModel.swift` 提交/恢复后只读刷新，`StorySessionPanel.swift` 展示文字。
8. 同步契约 roundtrip、编译 driver 的显式源文件清单及 Xcode 文件纳入方式；不改未接线示例页。

# 6. 关键实现说明

```text
ensure(turn):
  assert turn 已提交且属于当前 session
  if stored narrative exists: return stored
  candidate = compile(该 turn 已提交事实的披露投影)
  block = bind segments to trusted speaker and source revision
  publish immutable block
  return reread stored block

after_commit:
  narrative = ensure(turn)
  if voice unavailable: return audio unavailable
  prepare audio from narrative's character segment
```

同一进程同 turn 的并发 ensure 使用有界 single-flight；进程崩溃后通过持久产物判断完成。若并发发布冲突，重新读取既有产物并验证同 turn 归属后复用，不覆盖文本。已有历史单段叙事保持原样，不尝试按换行拆分迁移。

模型提示词只约束表达，不构成事实正确性的机器证明；本包确保来源与类型边界，不声称解决所有模型幻觉。披露投影必须沿用已知授权源，不能扩大玩家视界。

# 7. 测试方案

| 目标文件 | 新增/调整断言 |
|---|---|
| `engine/tests/test_narrative_publication.py`（拟新增） | 已有文字零模型调用；重复请求同 ID；旁白与对白分段；错误 speaker 拒绝 |
| `engine/tests/test_narrative_block_repository.py` | 内容冲突仍拒绝，revision 与 StateDelta 绑定不放宽 |
| `engine/tests/test_story_runtime.py` | live 无 voice 仍有文字；绑定失败不撤销文字；固定模式无双写 |
| `engine/tests/test_speech_unit.py` | 仅对白索引 seal；旁白不会当角色声音播出 |
| `contracts/tests/test_story_expression_control.py`（拟新增） | 必填、未知字段、状态/segments 联合约束、身份越界 |
| `macos-app/WorldOfMysteriesTests/StoryExpressionControlTests.swift`（拟新增） | 严格解码、无 capability 降级、过期响应不覆盖当前会话 |
| `StorySessionModelTests.swift` | 提交成功但音频不可用仍显示文字；查询失败不重发提交 |

# 8. 验收标准

运行位置：实施工作区根目录。当前均未执行。

```bash
python3 scripts/gate_profile.py check
python3 scripts/gate_profile.py run --profile FULL_P0 --cwd . --log-dir .hacf/logs/ao-01
```

- [ ] 无 SpeechRail、受控模型成功：一份领域提交、一份可读叙事、无音频。
- [ ] 语音可用时 spoken_text 仅来自已持久授权对白。
- [ ] 重新读取/重复 ensure 不生成第二份文本，不改变世界修订。
- [ ] 旧 submit DTO/契约不变，未声明 capability 的客户端不调用新方法。
- [ ] FULL_P0 通过，新增用例未跳过；真实模型/扬声器体验若未执行，单列未验证。

# 9. 风险与注意事项

无数据库迁移；新 wire 方法需 Schema、Python、Swift 同步并经 AGT-ARB 授权。业务范围涉及 AI、Application、Infrastructure 和 macOS，胶囊必须明确跨目录所有权。

回退保留新产生的合法多段 NarrativeBlock；不得回写为旧单段。旧消费者是否接受多段用既有 schema 测试确认，若旧播放器只处理首段，回退版本不得宣称多段语音完整支持。

不处理持久任务调度、自动重试、旁白 TTS、多音色并行、完整故事书、模型切换。

# 10. Luna 执行清单

- [ ] 核对基准和工作区，确认已有同名实现后调整而非覆盖。
- [ ] 写出无 voice 缺文字和类型丢失两个回归用例，确认旧代码失败。
- [ ] 实现候选、唯一文字发布与音频消费分离；回归用例通过。
- [ ] 同步只读查询 schema/handler/Swift DTO/UI，跨语言 fixtures 一致。
- [ ] 验证旧固定模式、历史叙事与重复请求均不被改写。
- [ ] 完成受保护门禁与胶囊凭单，记录未执行的真实服务验收。
