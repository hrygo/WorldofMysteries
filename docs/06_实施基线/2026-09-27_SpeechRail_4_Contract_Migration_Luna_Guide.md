# 1. 问题结论

本方案指导 Luna 将 WorldofMysteries 的 SpeechRail 接入迁移到 Realtime 契约 `4.0.0`，完成离线契约、状态机、媒体桥和采集链验证。交付边界是“语音组件可接线”，不自动增加正式 App 语音入口，不宣称设备听感或已安装服务通过。

证据核实日期：2026-09-27。WoM 基线 `e9849d3`；SpeechRail 基线 `3a1b02e07a573041d08920a09efc195af794332f`（提交说明 `release: prepare 3.3.0`）。两边工作树在本次开始检查时均干净。版本提交不证明 Release 已发布或本机服务已升级。

关键修复：

1. Python TTS：替换旧会话、`tts.create`、`response.*` 协议；实现 start、文本 ACK、finish、音频、终态和 REST receipt 完整闭环。
2. Swift ASR：迁到嵌套 `session.update` 与 24 kHz wire；移除 `committed/cleared` 依赖，安全聚合自动分段结果。
3. 对齐 revision 校验、错误关联、鉴权可诊断性、能力观察与测试。
4. 更新旧供应者基线，建立固定上游契约证据，防止测试与真实服务长期脱节。

纠正前序分析：没有运行测试，不能说“测试现在是绿的”；有限字符串查找不能证明整个语音栈绝无产品调用；能力快照解析成功不证明推理已就绪；端点存在不证明全部 SR-V 待办的行为验收完成。本文采用更窄的结论。

# 2. 当前实现与根因

## 2.1 证据及处置

以下 WoM 路径均相对仓库根目录。

| 路径 / 符号 | 已核实问题 | 处置 |
|---|---|---|
| `engine/infrastructure/audio/realtime_tts.py`：`SpeechRailRealtimeTTSAdapter.connect/render/cancel_active/_validate_receipt` | 旧会话事件、平铺字段、`tts.create`、`response.*`；cancel 缺 event ID；内联 receipt；旧完整性边界 | 重写 provider 协议状态机，保留注入 transport、PCM sink 和封存文本输入 |
| 同文件 `_receive` | 首 sequence 期待 1；上游当前实现也从 1 发出，但文档正文称从 0 开始，schema 允许 0 | 握手接受首 sequence 为 0 或 1；后续严格连续 |
| `engine/infrastructure/audio/voice_control.py`：`VoiceRenderControlRequest` | model revision 限制 40 位 hex；`provider_tts_fields` 保留旧供应者字段 | 放宽应用契约；明确应用字段到 provider 字段的唯一转换点 |
| `engine/domain/voice_identity.py`：`ProviderVoiceRevision` | `_MODEL_REVISION` 同样限制 40 位 hex | 同步放宽，不在纯 Domain 引用供应者 SDK |
| `contracts/protocol/voice_render_control.schema.json` | model revision 的同一限制 | 保留字段名，兼容性放宽 pattern |
| `engine/application/speech_unit.py`：`SealedSpeechUnit` / 封存流程 | model revision 来自 binding 的 `model_catalog_revision` | 保留封存与 COMMIT 边界，补新 revision 的贯通测试 |
| `engine/infrastructure/audio/media_bridge.py` | 对外 W-V01 已是 24 kHz；消费旧 TTS chunk/terminal 类型 | 保留信用、分块、generation、防旧音频机制，仅适配新 provider 结果 |
| `engine/infrastructure/audio/voice_runtime.py`：`VoiceRenderRuntime` | 按封存单元建 adapter，调用 connect/render | 复用；注入 receipt reader，保持失败不回滚领域状态 |
| `engine/infrastructure/audio/capabilities.py`：`_parse_snapshot/_parse_voices` | 能读当前基本 schema，但忽略 `realtime`、运行级保证、可用性原因；HTTP 参数支持不等于实时支持 | 增量扩充观察对象，不改变成模型控制面 |
| `engine/infrastructure/audio/config.py` | 环境变量已有 key 注入；默认 placeholder | 去掉真实 WS/发现请求的虚构凭据，保持显式注入 |
| `engine/infrastructure/audio/websocket_transport.py` | HTTP 拒绝与 close code 被折叠；先校验 accept 再判断 status 会掩盖认证失败 | 保留底层 transport，修复错误分类与脱敏 |
| `macos-app/WorldOfMysteries/Media/SpeechRailRealtimeASRConnection.swift` | 16 kHz 硬校验；旧会话格式与确认事件 | 24 kHz + 新会话契约 + 单接收者 |
| `macos-app/WorldOfMysteries/Media/SpeechRailRealtimeASR.swift`：`InputTurnAssembler` | 必须先有 committed；cleared 后才完成 | 以首见 item 建序，重做 finalization barrier |
| `macos-app/WorldOfMysteries/Media/SpeechRailRealtimeASRTurnCoordinator.swift` | finish 发 commit → clear，再等 cleared | 改为 commit → 同配置 session.update → session.updated |
| `macos-app/WorldOfMysteries/Media/MicrophoneCapture.swift`、`VoiceInputPTTSession.swift`、`VoiceProcessingDuplexGraph.swift` | capture、pump、duplex 都限定 16 kHz | 一起迁到 24 kHz，保留连续重采样、帧计数和 AEC 图 |
| `macos-app/WorldOfMysteries/EngineRuntimeModels.swift`：`VoiceRenderControlRequestDTO` | 应用 IPC 字段为 expected revision | 保留 Codable 字段名，验证与 Python/schema 一致 |
| `docs/03_工程规范/voice/SpeechRail_Integration_Contract_v1.0.md` | 供应者钉在 2026-09-17；把旧 clear 回执当栅栏，SR-V 状态是历史快照 | 原位重基线，历史日期保留并标注 |

当前查询没有在 `AppState.swift` / `ContentView.swift` 找到上述 ASR 构造点；`voice_runtime.py` 的现有直接引用主要在测试。实施前还须沿实际生产组合根检查注册和注入，不能仅凭 import 搜索宣称全仓“未接线”。

## 2.2 上游固定证据

上游根地址：<https://github.com/hrygo/SpeechRail>。下面文件均以本方案锁定的完整 SHA 获取，不直接 import 相邻仓库，不在 CI 引用开发机路径。

- `contracts/realtime-openai.md`：4.0.0 会话、事件与 24 kHz 音频责任。
- `contracts/realtime-events.schema.json`、`contracts/realtime-field-matrix.json`：机器 schema 与字段责任。
- `contracts/openapi.yaml`：能力、voice、receipt、timing 的 REST 契约。
- `src/speechrail/compatibility/openai_realtime.py`：事件白名单、session 更新、ACK、终态与 error 的实际字段。
- `src/speechrail/http/routes/realtime_openai.py`：普通队列 FIFO、只有 TTS cancel 进入控制队列；服务端 sequence 首值 1。
- `src/speechrail/application/realtime_openai.py`：`_commit_audio_once` 等待 ASR reader；`_update_session` 成功后发 updated；仍有自动 rollover。
- `src/speechrail/application/tts_stream.py`：receipt 在 terminal 前完成；`TtsStreamReceipt.boundary = pcm16_after_transport_send`。
- `src/speechrail/application/capability_snapshot.py`：发现不预留推理资源，`available` 与模型 residency、quality 分离。

这些证据来自本地源码核对。网页访问未取得可用正文，因此不据此断言远端 Release、Issue 状态。图谱工具已尝试发现，但本会话仅暴露项目列表/schema 等工具，未取得所需 coverage/符号查询工具；结构结论以相关源码回退核实，不声称完成全仓调用图审计。

## 2.3 直接原因和设计原因

供应者执行 current-only 硬切换，WoM 同时冻结了旧 wire 和旧 fake events。内部通过的假事件无法证明跨仓兼容。另有“服务端文本 final”“整轮输入结束”“音频生成完成”“完整 take 可发布”“用户实际听到”五种状态，需要分别验证。

# 3. 目标行为

- ASR 使用 24 kHz、mono、PCM16 little-endian；无头 PCM 的非空偶数字节通过 append 发送。设备原生采样率可以不同，由 App 连续转换。
- PTT 仅在全部采集块排空、所有已观察 item 成功终结、收口屏障到达后产生一次 `FinalTranscript`。partial/hypothesis 永远不进入 Advice/Domain。
- TTS 仅处理已 COMMIT/封存的 `spoken_text`，保持一次完整文本调用；供应者适配器内部按协商限制拆成增量 append。
- 仅 `completed + 样本连续 + digest/revision/格式匹配的 receipt` 可以产生完整成功结果、发布 take。播放过的部分音频不等于完整缓存。
- 取消先使 App generation 失效/本机停止，再尽力取消 provider；已提交世界事实不变。
- 认证失败、服务未就绪、busy、协议不匹配、receipt 不足分别可诊断；不自动升级服务、下载模型、换音色或重发已部分播放的 utterance。
- HTTP OpenAI-compatible adapter 保留；SpeechRail 专有 wire 不套用到第三方供应者。

# 4. 推荐解决方案

## 4.1 范围与取舍

推荐在现有边界内更新三个适配面：ASR、TTS、能力观察。复用 W-V01、封存单元、voice binding、take/cursor 存储与既有 SDK。

不采用“全体改用 HTTP 批处理”替代实时流；也不实现旧 Realtime alias。只增加 ASR/TTS 协议所需能力。Alignment、Diarization 的展示、VoiceDesign/clone 制作流程、词典 UI、timing 字幕、模型 spec 管理均另列后续工作。

## 4.2 ASR 收口决策

每轮独立连接；manual/null endpointing，alignment/diarization=false，握手完成后无并发配置更新。结束顺序：

`停止采集 → drain append pump → commit → 重发完全相同的 session.update → 等 session.updated → 校验 item 终态 → 关闭连接`

依据：当前上游普通 handler 顺序执行；commit 等 reader 结束；相同配置更新在其后处理并确认。该用法是**锁定实现的消费者屏障**，不是 OpenAI 标准或所有 SpeechRail 未来版本的通用保证。无更高优先级的 endpointing 配置，不使用 clear 或网络静默时长代替证明。

实施 T01 必须先验证：延迟 reader、rollover、多 item、commit error 时，updated 不提前。若固定上游不能证明该顺序，停止 ASR 成功路径交付，保留超时失败；提出上游独立契约缺口，不能退化为“第一个 final 就成功”。其余 TTS/采集/文档工作继续。

## 4.3 凭据决策

本迭代保留现有外部注入，不读取 SpeechRail 私有受管配置、不新增 Keychain wrapper、不把 key 落盘。Python 优先级保持 `OPENAI_AUDIO_API_KEY` → `SPEECHRAIL_API_KEY`；Swift 由调用方显式传入，供后续产品组合根接线。

未提供真实 key 时 WS/发现不发 Authorization。若 Python SDK 构造器必须有非空 key，可仅在通用 REST SDK 边界保留兼容占位，不把它作为服务端凭据事实。鉴权启用而未注入 key 时明确失败。正式 App 设置/持久化凭据另作产品任务。

# 5. 详细实施步骤

## T01：锁定契约与先写失败回归（AGT-ARB / AGT-QA）

拟新增 `fixtures/speechrail_contract/`：

- `manifest.json`：仓库 URL、完整 commit SHA、Realtime version、源文件相对路径、每个文件 SHA-256、已核实实现差异。
- `realtime-events.schema.json` 与必要 REST schema 快照：原样只读快照，不在本仓维护第二套 provider 定义；新版本必须整体更新 manifest 和 digest。
- `cases.json`：合成文本及测试生成 PCM；有效会话、start/ACK/audio/terminal、多个 ASR item、error、receipt。禁真实录音、reference text、key、绝对路径。

拟新增 `engine/tests/test_speechrail_wire_contract.py`，使用现有 JSON Schema 依赖验证快照和 fixture。Swift 共享 cases 从测试源码 `#filePath` 推导仓库相对位置读取，避免为此修改生产打包或引入 JSON Schema SDK；Swift 解码语义与 Python schema 校验分工明确。

先让旧请求/旧收口在新 fixture 下失败，记录失败原因；测试要调用现有适配器，不能仅证明 fixture 自身有效。未来联调使用固定上游的 mock backend/WS 服务验证屏障；本仓不 import 上游 Python 包。新增测试纳入现有 FULL_P0 的目录收集；若修改 VOICE_P0 选集，由 ARB 修改受保护档案及 registry。

完成条件：旧请求被机器 schema 拒绝；新示例有效；屏障的上游顺序证据有明确测试记录或阻塞状态。

## T02：应用 revision 与能力观察（AGT-ARB + 对应文件所有者）

1. `voice_render_control.schema.json`、`voice_control.py`、`voice_identity.py` 对齐 model revision 为 `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`。40 位 hex 仍有效；拒绝空值、空格、斜杠、控制字符和超长值。
2. 保留应用字段 `expected_voice_revision`，由 adapter 转成上游 `voice_revision`；不要把 provider 改名传播成数据库列改名。
3. `model_catalog_revision` 仍是模型制品 revision，不能拿快照的全局 `catalog_revision` 或 `snapshot_id` 替代；`runtime_revision` 为独立观察证据。
4. 贯通 `ProviderVoiceRevision → SealedSpeechUnit → VoiceRenderControlRequest → RealtimeTTSRequest`；Swift DTO 保持同字段；既有持久化值原样读取。当前 `003_world_voice_bindings.sql` 为 TEXT，无需仅为 pattern 放宽增加迁移。
5. `capabilities.py` 保留原子快照与 ETag。新增可选观察：`availability_reason`、`production_ready_reason`、模型 identity、`realtime` 责任声明、`guarantees`。字段缺失保持 unknown，不猜 true。
6. `operations.http_speech` 与 `operations.realtime_speech` 分开判断；前者支持参数不代表后者有增量路径。`tts_streaming_unsupported` 必须被正常传播。
7. 若保留 `status=ready`，文档明确其只表示发现结果可解析；`ready/asr_ready/tts_ready` 没有证据仍为 None，不把它用于产品“可开始录音/合成”指示。

完成条件：新旧合法 revision 跨模型/IPC/存储 round-trip；参数与就绪语义不混淆。

## T03：Engine TTS 状态机（AGT-VOICE）

修改 `realtime_tts.py`，必要时拟新增 `render_receipts.py` 存放有界 REST reader。

握手发送：

```json
{"type":"session.update","event_id":"evt_unique","session":{"type":"transcription","audio":{"input":{"format":{"type":"audio/pcm","rate":24000},"transcription":{"model":"whisper-1"},"turn_detection":null}},"speechrail":{"task":"render","tts":{"enabled":true},"alignment":{"enabled":false},"diarization":{"enabled":false}}}}
```

等待 `session.updated`，校验实际格式及 TTS enabled。移除 session 上的 `render_receipts` 和旧 `model_revision` 对象；模型 revision 放在该 voice 的 `tts.start.expected_model_revision`，避免 session 默认 voice 的模型路线与目标 clone 模型不一致。

render 流程：

1. 验证已有封存文本和 request ID；一次只有一个 active request。
2. 发 `speechrail.tts.start`：event_id、request_id、task=`render`、voice、voice_revision、speed、可选 expected_model_revision。
3. 等 `started`；锁定 task_id/plan_id/voice_revision，校验 output_format 为 `audio/pcm`、`sample_rate=24000`、channels=1；读取 limits。
4. 按 Unicode codepoint 拆不可变文本，每段不超过 max_append_codepoints、max_pending_codepoints，全文不超过 max_total_codepoints。禁止修改、正规化或丢掉封存字符。超过总限直接失败，不静默截断。
5. 单段在途，append sequence 从 0；每段等 `text_accepted.append_sequence`，校验 accepted/total codepoints，再发下一段。音频可与 ACK 交错，始终由唯一 reader 分发。
6. 最后一段 ACK 后发 finish_text，last_sequence 等于最后 ACK 序号。
7. audio.delta 校验 request_id/task_id、chunk_index 从 0 连续、sample_offset 与累计 PCM 帧一致、base64 严格、字节偶数、格式与上限；然后交给现有 sink。
8. completed.generated_samples 必须等于累计帧数且非空合成有音频，再读取 receipt；failed/cancelled 不走成功校验或发布 take。

保留 `render(request, on_chunk)` 外观；不要为 LLM token 直接流入 TTS 新建业务入口。内部 chunk/terminal 将旧 response/item 关联替换成 request/task/plan；修改已核实的消费者，禁止用 task_id 冒充真实 provider response_id。W-V01 的 stream_id/generation 不变。

## T04：receipt、媒体取消与错误（AGT-VOICE）

通过注入 reader 读取 `/v1/speechrail/audio/receipts/by-request/{request_id}`，URL path segment 编码，拒重定向、限响应体、沿用真实鉴权。保留 connect 的 `enable_render_receipts` 参数时，定义为本地“要求成功凭单”策略，默认开启，不再发 wire flag；改名需同步所有调用及测试。

成功至少验证：

- receipt.status=`completed`、request_id 完全匹配、receipt_id 合法。
- voice.id/revision 与本次 canonical voice 和 pin 相同；caller 应消费 canonical ID，不能把 alias 不等当作真实 identity 冲突。
- model.source_model 与封存的 model_id（存在时）匹配；model.catalog_revision 与请求模型制品 pin 匹配。runtime_revision 不冒充 catalog revision。
- audio.format=`pcm16`、pcm_sample_rate=24000、channels=1、sample_count 等于接收帧、pcm_sha256 等于本地 digest。
- integrity_boundary=`pcm16_after_transport_send`；不得继续校验旧 `pcm16_after_websocket_send`。

当前实现 receipt 先于成功终态完成，默认读一次。网络瞬断/5xx 至多再试一次，整个 receipt 阶段限 3 秒；401、404、pending、缺字段、digest 错立即失败。未知完整性不放行、不自动重新合成。禁止把服务端 transport-send 凭据描述成实际听到；DeliveryCursor 的 scheduled/rendered/measured 证据级别保持独立。

cancel 只发 type/event_id/request_id，删除 response_id；cancel 超时或 peer 消失关闭连接并结束本地 render。给 ACK、started、terminal、sink 等待设置有界期限；等待 media CREDIT 时仍能处理取消并解除阻塞，reader/sink 之间采用有界队列，不因拆分任务引入无限 PCM 缓冲。生产默认每 render 关闭连接，消除旧终态串入下次的风险。

error 顶层 request_id 关联 utterance，error.event_id 关联被拒客户端事件。保留 sent-event 到 request 的映射；不能继续读 error.request_id；不从自由文本 message 解析协议事实。

完成条件：错误 receipt/取消/断网永不 END-success、永不发布完整 take；世界状态不变化。

## T05：Swift 24 kHz 与新 ASR 收口（AGT-MAC）

修改 §2 列出的 6 个 Media 文件及相应测试。

- 将麦克风输出、PTT 校验、duplex 输入约束和 ASR 配置统一 24_000。帧时长、buffer 上限按新采样率重新计算；不全局替换所有 16_000（其他内核/测试输入可能合法）。
- 拟在现有 ASR 配置中提供一个共享 wireSampleRate 常量；采集配置使用该值，避免四处独立硬编码。
- 连续 AVAudioConverter/重采样状态跨块保留；设备切换重建 epoch；44.1/48 kHz 设备输入不按字节直接重标 24k。
- 新会话 task=`transcription`，TTS、alignment、diarization=false；manual/null；删除旧平铺参数；收到 updated 后验证 effective 配置。
- 握手结束才交唯一 reader 给 coordinator；finish 不另开 receive 来抢 `session.updated`。
- `InputTurnAssembler` 移除 committedOrder 的“必须由 committed 创建”要求：按 delta/completed/failed 首见 item 顺序建记录。completed 可先于 delta，覆盖草稿；重复相同 final 幂等，冲突 final 失败。
- hypothesis 是可修订草稿，按 task/epoch/utterance/revision 更新，不作为 append-only delta；与最终 item 缺少可证明关联时，仅作为临时全局草稿显示，不拼入 FinalTranscript。终态以 completed 文本为准。
- finish 停采集并排空 pump；标记 finalizing，发 commit 后发同配置 update。只有本轮唯一 pending barrier 对应的后续 updated 才可完成；不依赖服务端 echo 客户 event_id。
- barrier 到达时，所有已观察 item 必须有成功 final；任意 error/failed、sequence 缺口、未终结 item 均使整轮失败；空白 final 聚合为 empty；有文字且无失败才给 transcript。
- 先到的 rollover final 不能提前完成；超时/取消/错误关闭连接；成功也关闭连接。terminal continuation 恰好恢复一次。
- 已关闭的辅助能力事件不能改变文本终态；本迭代无需增加 alignment/diarization UI。不要让未知新事件直接越过 envelope 序号校验。

完成条件：无需 committed/cleared 的多 item PTT 回归通过；取消、错误和无声音频均不生成 Advice。

## T06：鉴权与传输诊断（AGT-VOICE / AGT-MAC）

按 §4.3 修改配置和 Python transport；Swift 保留 URLSessionWebSocketTask，读取可用 closeCode/HTTP 信息并给结构化失败。accept 前被拒可能呈 HTTP 403，不能假定客户端一定收到 1008；无法区分时返回 handshake_rejected，不杜撰 invalid-key 结论。

统一失败语义：authentication_required/failed、backend_not_ready、busy、protocol_incompatible、transport_closed、receipt_invalid（名称拟新增，内部枚举按现有类型落地）。外部 code 保留用于诊断，日志禁 key、PCM、全文 transcript 和绝对模型路径。原始 close reason 只作限长脱敏诊断，用户提示使用本地文案。

完成条件：未设 key 不发假 Bearer；401/403/1008 与普通网络错误有足够证据时区分；取消不会被 capability probe 的广泛异常捕获吞掉（`asyncio.CancelledError` 应继续传播）。

## T07：文档、集成测试与交接（AGT-ARB / AGT-QA）

更新：

- `docs/03_工程规范/voice/SpeechRail_Integration_Contract_v1.0.md`
- `docs/03_工程规范/voice/Voice_First_Technical_Design_v2.0.md`
- `docs/07_工程启动/Voice_First_Kickoff_Spec_v1.0.md`
- 与上述新验收冲突的 `Voice_First_Acceptance_v2.0.md` 条目。

SR-V 状态分开写“schema/端点存在”“消费者已实现”“集成已验证”“设备人工验收”；不根据 endpoint 存在关闭上游 Issue。更新供应者 SHA 和 source path，保留历史变更账本。

离线集成连接新 adapter → 真实 MediaBridge → 本地测试 peer，驱动 CREDIT/cancel/END/error；把 `VoiceRenderRuntime` 放入测试 IPC composition，证明 sealed-unit 授权与拒绝伪造文本仍生效。此测试注册不自动改变生产 `_run` 或 App 入口。

# 6. 关键实现说明

## 6.1 TTS 状态集合

```text
disconnected → connecting → ready
ready → starting → streaming → finishing → verifying_receipt → completed
starting/streaming/finishing → cancelling → cancelled
任一执行状态 → failed → closed
```

`streaming` 内有 last_sent_append/last_acked_append/next_chunk_index/received_samples；connection sequence 与 append sequence、chunk_index 分别计数，不混用。ACK 可以夹在音频事件之间。`finish_text` 只发送一次。任何取消后 generation 无效，不再向 sink 交付旧块。

## 6.2 ASR 屏障伪代码

```text
finish:
  stop capture
  await append pump drained
  if capture/pump failed: fail + close
  mark finalizing and install one barrier waiter
  send commit
  send identical effective session.update
  existing receive loop keeps collecting all items
  on later session.updated:
    validate same effective config
    if any error or observed nonterminal item: fail
    else freeze completed texts in first-seen item order
    close connection and emit one terminal
```

session.updated 仅是普通 handler 已排空的实现证据，不表示后台 alignment 已完成；本迭代将其禁用。不能引入“超时就返回已收到部分文字”的成功路径。

## 6.3 测试证据单一来源

fixture JSON 与 schema 快照不成为运行时依赖；生产协议解析是应用代码。manifest 保留源 SHA 与 digest，任何快照改动必须能说明来源。固定 SHA 的跨仓 fixture 不等于共享代码依赖。

现有 provider 模型别名 `whisper-1`、`tts-1` 与 `alloy` 不需要因名字像旧 API 就删除；强 identity 的 render 使用 canonical voice 和封存 revision。不得从发现 endpoint 成功推断 clone 可生产发布或任意 speed 可用。

# 7. 测试方案

本次仅完成方案与源码核查；下面测试均为实施要求，尚未执行。

| 测试文件 | 必须覆盖 |
|---|---|
| 拟新增 `engine/tests/test_speechrail_wire_contract.py` | manifest/digest；客户端事件 schema；旧事件拒绝；共享 cases 合法性；0/1 首序号与后续连续性 |
| `engine/tests/test_audio_adapter.py` | 新握手；ACK/audio 交错；多 append；中文/emoji codepoint；协商 limits；非法 revision；错误关联；cancel/timeout；能力 unknown/available/production_ready 分离 |
| 拟新增 `engine/tests/test_speechrail_render_receipts.py` | 200 成功、401/404/5xx/pending、身份/样本/hash/边界错、重定向拒绝、超大 body、有界重试 |
| `engine/tests/test_voice_identity.py`、`test_voice_binding_repository.py`、`test_speech_unit.py` | 新旧 model revision round-trip；非法值拒绝；既有记录与封存 hash 不被重写 |
| `engine/tests/test_voice_runtime.py` | sealed-unit 一次授权；真实新 adapter + fake provider；失败 receipt 不发布成功；媒体取消先行；CREDIT 阻塞可取消 |
| `engine/tests/test_audio_take_coordinator.py`、`test_audio_take_store.py` | 不完整流不入完整 take；旧已完成音频仍可回放 |
| `SpeechRailRealtimeASRConnectionTests.swift` | 嵌套字段、24k、鉴权、session.updated、首序号、单 reader |
| `SpeechRailRealtimeASRTests.swift` | 无 committed 的 final；rollover 多 item；重复/冲突 final；hypothesis 修订；序号缺口；旧 epoch |
| `SpeechRailRealtimeASRTurnCoordinatorTests.swift` | 延迟 final + updated；先收到部分 final 不完成；commit error 后 updated 仍失败；barrier 超时；取消只终结一次 |
| `VoiceInputPTTSessionTests.swift`、`MicrophoneCaptureTests.swift` | 24k、停止后 drain、转换跨块连续、错误采样率拒绝；duplex 配置一致 |

Swift 测试路径统一在 `macos-app/WorldOfMysteriesTests/`。若 duplex 当前无独立测试文件，拟新增 `VoiceProcessingDuplexGraphTests.swift`，只测试本任务改变的格式约束和可注入纯逻辑，不在 CI 自动打开真实麦克风。

上游 mock 服务验证屏障需使用锁定版本的无模型后端：延迟 reader、自动 rollover、commit timeout/error、后续 same-config update。fake WoM 服务只能证明消费者行为，不能替代上游顺序验证。模型、设备与人工听感验证不在离线测试结论中。

# 8. 验收标准

仓库根目录已有的受保护启动器（命令在本方案仅引用，真实定义仍在 `.hacf/gates/`）：

```bash
bash scripts/gate_runner.sh VOICE_P0
bash scripts/gate_runner.sh MACOS_APP_P0
bash scripts/gate_runner.sh FULL_P0
```

VOICE_P0 当前只收 `tests/test_audio_adapter.py`，不能独自证明新 receipt/runtime 测试通过；最终 FULL_P0 包含 Python 全集、Swift 测试和 Xcode App build，必须核对新测试确实被收集。新增或修改门禁命令仅由 ARB 在档案内定义，再执行已有 registry 刷新流程。不要把验收命令塞入 capsule。

- [ ] 以新 schema 复现旧协议失败，修复后相同回归通过。
- [ ] 上游 pinned mock 证明 ASR barrier 顺序；无证据时明确标记 ASR 阻塞，不降级成功标准。
- [ ] 新 TTS 三段式、样本连续性、receipt 与取消竞争均覆盖。
- [ ] microphone/PTT/duplex/ASR wire 均为 24 kHz，播放与 W-V01 不退化。
- [ ] revision 放宽跨 schema/Pydantic/Domain/Swift DTO 一致，旧数据库无需重写。
- [ ] 无 committed/cleared/response.* 的旧 wire 路径；负例与历史文档引用可以保留。
- [ ] 文档固定上游 SHA；区分代码版本、契约版本、运行中服务版本。
- [ ] FULL_P0 实际通过；日志记录所运行 HEAD、测试数量、失败/跳过及具体原因。
- [ ] 无凭据、真实录音、开发机路径进入仓库产物。
- [ ] 仅在获准真实设备/服务联调后补充录音、停止延迟、听感结果；未测不得写通过。

实施时遵守 HACF：核对目标分支 → pack → 隔离工作区 → 回归与实现 → 实质提交 → verify → 独立凭单提交。此方案不代表已创建胶囊、已签发凭单或已获远端发布授权。

# 9. 风险与注意事项

1. ASR barrier 是锁定实现依赖，需明确回归守卫；服务升级若改变队列或 commit reader 等待行为，必须 fail closed。
2. 当前上游文档 sequence 初值与实现有差异。只放宽握手首值为 0/1，不能容忍任意 gap/backtrack。
3. receipt 终态在 WS 外，服务重启/淘汰可能导致 404。允许本地临时音频失败清理，不允许把缺证据音频升格成完整 take。
4. 某些 voice 可用但不支持增量或非 1.0 speed。返回结构化不支持，不强改 speed 或换身份。
5. 运行中的 SpeechRail 未探测；源码 HEAD 不代表安装服务。联调前通过公开只读接口核实能力，禁止读取私有 key 文件或启动模型来“探测”。
6. 项目角色：TTS adapter 属 AGT-VOICE，不是 AGT-DOM；纯 Domain revision 由 AGT-DOM/ARB 覆核；contracts/gates 高风险变更由 ARB 管理。切片须按实际 ROLE_DEFAULTS 核对范围。
7. 若执行环境提供受管 worktree 工具，优先复用/创建受管工作区；按现行工具与项目租约规则衔接，不能重复创建两个 checkout。保持 `/tmp` 短 socket 命名空间。
8. 本方案不要求数据库迁移、改世界推进逻辑、启用生产语音 UI、升级 SDK 或搬运上游私有代码。
9. 文件有并行改动时先核查归属，保留对方修改；禁止整文件覆盖以恢复本方案基线。

# 10. Luna 执行清单

按依赖执行，任务角色表示代码所有权，不要求自动启动多个代理：

| 顺序 | 任务 | 目标与独立完成条件 |
|---|---|---|
| 0 | 核对工作区/证据 | 两仓 HEAD、当前改动、生产组合根注册、可用门禁；记录与本文偏差 |
| 1 | T01 契约回归 | manifest + 固定 schema/cases + 旧实现失败证据；上游 ASR 屏障验证 |
| 2 | T02 revision/观察 | Domain、IPC、能力对象增量修改，round-trip 与 unknown 语义通过 |
| 3 | T03 新 TTS | 三段式、ACK/音频交错、limits、唯一 reader 与终态测试通过 |
| 4 | T04 receipt/媒体 | REST 验证、错误关联、有界取消与 CREDIT 场景通过 |
| 5 | T05 新 ASR | 24k 采集贯通、多 item + updated 屏障、失败不提交测试通过 |
| 6 | T06 连接诊断 | 双端真实凭据注入、HTTP/WS 错误分类与脱敏验证 |
| 7 | T07 文档/联调 | 新固定基线、测试 IPC/media composition、完整 take 发布条件验证 |
| 8 | 最终交付 | FULL_P0、变更范围、HACF 凭单；明确列出未执行的真实服务/设备验收 |

依赖关系：T03/T05 依赖 T01；T04 依赖 T02/T03；T06 可与对应适配器同步；T07 汇总全部。修改相同文件时保持单一执行者。上游顺序验证失败只阻塞 ASR 成功交付，其他独立任务可以继续。

最终交接需报告：固定基线、实际修改文件、回归结果、未验证项、生产入口是否接线，以及仍需另行批准的设备/模型/发布操作。
