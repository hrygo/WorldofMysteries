# AO-02 统一文字与语音请求恢复 — Luna 实施方案

> 日期：2026-09-28；源码基准：`ca68d485a15bacf46ade5e703abde00598ec5251`。
> 状态：待实施；无硬依赖。可在 AO-01 前交付，不依赖表达查询。
> 拟新增符号显式标记；测试和门禁未执行。共同边界见 [方案集](README.md)。

# 1. 问题结论

交付一个 App 内的持久提交协调器，使最终文字和 ASR 转写采用相同身份冻结、未知结果查询与同一请求重试机制。语音失败不能简单等同于未提交。

本包不修改服务器领域事务、数据库或现有两个 submit wire 方法，不把固定输入限制改成自由输入。

# 2. 当前实现与根因

| 现有文件 / 符号 | 当前逻辑 | 目标处置 |
|---|---|---|
| `macos-app/WorldOfMysteries/StoryRequestJournal.swift`：`StoryRequestRecord` / `StoryFrozenSubmission` | 保存 ID、文本、修订；缺输入模式与提交方法 | 扩展版本化日志，兼容历史固定文字记录 |
| `StorySessionModel.swift`：`submit(_ frozen:)` / `recover` | 提交前记日志，查询恢复 | 将通用部分迁入协调器 |
| `Media/VoiceTurnController.swift`：`finishAndSpeak` | 临时 UUID 直接 storyTurnSubmit；异常返回 commit_failed | 调用协调器；保留采集和播放职责 |
| `EngineIPCClient.swift`：`storySubmit` / `storyTurnSubmit` / `storyAdvice` | 分别调用两个提交接口和查询 | 保留 wire；通过同一 port 注入 |
| `AppState.swift` | 分别持有 storyModel 与 voiceTurn | 创建同一个协调器实例并注入两端 |
| `StorySessionControl.swift` | 两种提交 DTO 与 input_mode | 复用，不合并 wire 协议 |

根因：输入设备控制器承担了业务提交职责，导致两套请求身份与失败状态。只给语音 catch 增加一次 retry 会放大未知结果风险。

# 3. 目标行为

- 最终输入只生成一次 `input_turn_id`，先原子保存本地日志再发网络请求。
- 冻结 session、raw_input、story/store revision、input_mode、method；重试全部复用，不能 trim、重新转写或换方法。
- 网络失败进入 `outcome_unknown`，先调用 `story.advice.get` 查询。
- found+committed：恢复事实，禁止重发；found+received：允许显式继续原请求；not found：允许显式重试同一身份。
- journal 丢失/损坏但服务器 pending：只读展示，禁止制造文本或新 ID 绕过。
- 文字和语音同时操作只能有一个当前未决提交；切换设备或导航不能取消已提交事实。

# 4. 推荐解决方案

拟新增 `macos-app/WorldOfMysteries/StorySubmissionCoordinator.swift`，`@MainActor @Observable`；采用注入的 `StorySubmissionClient` protocol、现有 journal port 与 ID factory。协调器拥有一份操作状态，控制器不再维护独立的“提交是否成功”判断。

拟新增内部状态：

```text
idle -> submitting -> committed
                  -> outcomeUnknown -> querying
querying -> committed | received | notFound | blocked
received/notFound -> submitting（仅用户显式继续，复用冻结请求）
```

这些是客户端操作状态，不替换服务器 receipt.status。播放失败不改变 committed。

日志新增 `recordVersion=2`、`inputMode=text|voice`、`submissionMethod=story.advice.submit|story.turn.submit`。旧记录没有三个字段时，仅按历史事实映射为 v1/text/story.advice.submit，成功读取后下次保存写 v2。未知版本或非法组合进入 blocked，不静默删除。

不增加通用重试引擎；只为已有单会话持久命令复用实现。

# 5. 详细实施步骤

1. 在 `StorySessionModelTests.swift` 固化现有 Lost ACK 与重试行为，新增语音等价测试预期。
2. 扩展 `StoryRequestJournal.swift` 的自定义 Codable 解码和冻结请求；保留旧 fileName、路径、权限与原子写行为。
3. 新增协调器，先搬迁日志、提交、查询流程，再让 StorySessionModel 调用；不要同时改 UI 布局。
4. 改 `VoiceTurnController.finishAndSpeak`：拿到最终转写后交协调器；禁止内部重新生成 UUID 或自行 storyTurnSubmit。
5. 改 `AppState.swift` 注入一个共享实例；连接 generation 变化使旧完成回调失效，但保留 journal。
6. `StorySessionPanel.swift` 显示“结果待确认 / 已记录未提交 / 已保存 / 无法恢复”；语音和文字复用查询/继续入口。
7. 协调器只报告结果与可选 delivery；播放交回 VoiceTurnController。恢复 committed 但没有 delivery 时不重发领域请求求声音。
8. 更新 `engine/tests/fixtures/app_engine_driver.swift` 的使用方式及 `test_app_engine_session.py`、`test_voice_turn_e2e.py` 中显式 Swift 源文件清单；核对 Xcode 编译输入。

# 6. 关键实现说明

冻结顺序必须为 `validate locally → allocate identity → save journal → send`。日志写失败时零 IPC mutation。只保留现有合法输入规范化策略：文字首次冻结前可沿现有策略 trim；ASR 原文首次冻结后绝不改变。固定输入的最终合法性仍由服务器裁决。

协调器增加 in-flight guard 与 generation token；文字/语音 UI 禁用只是辅助，方法层仍拒绝并发。请求结果返回给不同 scene 前，验证 session 和 generation。

查询返回 not found 仅说明该次查询未看到该 ID，不产生新 ID；连接重建后需先恢复未决请求，再允许新输入。旧 v1 日志不得被推断为 live 方法，避免服务端 input identity 冲突。

预期错误分类：

| 情况 | 行为 |
|---|---|
| 空 ASR / 用户取消采集 | 不创建提交日志 |
| 日志落盘失败 | 显示本地保存失败，不提交 |
| IPC 超时 / 断连 | 结果未知，查询同 ID |
| schema/identity/revision 冲突 | 保留记录并阻止盲重试，显示稳定原因 |
| 已提交但播放失败 | 保留 committed，仅显示声音不可用 |

# 7. 测试方案

| 测试文件 | 验证内容 |
|---|---|
| `macos-app/WorldOfMysteriesTests/StorySubmissionCoordinatorTests.swift`（拟新增） | text/voice 参数化同一矩阵；ACK 丢失；notFound；received；重复点击；日志失败零发送 |
| `StoryRequestJournalTests.swift`（拟新增） | v1/v2 roundtrip、损坏与未知版本、method/input_mode 不丢失 |
| `StorySessionModelTests.swift` | 旧文字恢复全部保持，连接旧回调不污染 |
| `VoiceTurnControllerTests.swift`（拟新增） | 转写只提交一次；断线保留身份；播放失败不重交领域 |
| `engine/tests/test_app_engine_session.py` | 真实 Swift/Engine 的语音模式命令恢复，使用受控转写不依赖麦克风 |
| `engine/tests/test_voice_turn_e2e.py` | 既有 opt-in 实测保留，未运行不得标成功 |

# 8. 验收标准

工作区根目录运行；当前未执行：

```bash
python3 scripts/gate_profile.py check
python3 scripts/gate_profile.py run --profile FULL_P0 --cwd . --log-dir .hacf/logs/ao-02
```

- [ ] 文字、语音 Lost ACK 后恢复同一个 turn，领域提交计数不增加。
- [ ] App 重启保留原 ID、input_mode、method、文本和修订。
- [ ] 旧日志仍恢复原固定文字请求；未知日志版本不自动发送。
- [ ] 同时触发文字与语音不会覆盖日志或形成第二个未决请求。
- [ ] 固定模式限制不放宽；UI 不把网络失败称为未保存。
- [ ] FULL_P0 与新增用例通过；真实设备验收状态单独记录。

# 9. 风险与注意事项

只修改本地重试意图，不改变世界事实。回退到不认识 v2 字段的 App 前需保留日志副本，并禁止旧版把 voice 日志误作 text 自动处理；无法保证时用升级版本继续恢复，不能删日志“修好”。

AO-01 若已合入，保持其文字查询和展示，避免重构时移除。AO-03 后续只扩展 coordinator 的 method 选择与交付观察，不再建立第二套 journal。

不处理自动重录、转写修订、跨会话队列、后台自动重发、音频任务恢复、设备选择。

# 10. Luna 执行清单

- [ ] 确认现有日志和未决命令的保护策略，建立回归 fixtures。
- [ ] 完成版本化冻结记录；旧日志测试通过。
- [ ] 搬迁文字提交到协调器；原测试保持通过。
- [ ] 语音接入同一实例；禁止控制器直接提交。
- [ ] 完成状态文案与连接代次保护，跨进程 Lost ACK 用例通过。
- [ ] 跑受保护门禁并签发凭单，记录兼容与设备验证限制。
