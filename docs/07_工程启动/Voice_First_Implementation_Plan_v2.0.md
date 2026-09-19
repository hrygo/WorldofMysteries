# Voice-First Runtime v2.0 — 实施方案

日期：2026-09-19。状态：**执行设计，不是代码完成清单**。本次交付文档与上游 Issue；不改生产运行时、数据库或公共协议，不启动模型/麦克风/自动化听测，不授权合并。

固定基线：WorldofMysteries `591b4900606c122cb07416cd71fd56b66d056423`；SpeechRail `28755de8cc51046f25ce75c7869fe1bacd34752d`。技术定义见[技术方案](../03_工程规范/voice/Voice_First_Technical_Design_v2.0.md)，跨仓依赖见[接口与 Issue 映射](../03_工程规范/voice/SpeechRail_Integration_Contract_v1.0.md)，验收见[验收矩阵](Voice_First_Acceptance_v2.0.md)。

## 1. 交付目标与禁止的替代完成标准

首个完整闭环：用户说出建议 → 确认唯一 FinalTranscript → 当前角色合法行动 → 真实持久化 COMMIT → 固定音色回应 → 用户打断 → 本机立即停止 → 继续/新建议 → 不重复提交、不播放迟到音频。

必须分开标注两种模式：

- `media_demo`：真实麦克风、ASR、TTS、播放，使用显式的合成 Narrative fixture；不声称世界已经提交。可在 Domain 尚未完整时先交付。
- `story_voice`：使用真实 Session/Application、授权视图和提交事务；在 World/Character/Story 服务未就绪时不得启用，不允许把 fake CommitPort 包装为生产接线。

接口定义、模拟单测、服务 ready、CI 通过、真实声学验收是不同证据。任何阶段都不能仅以新增若干 Protocol 作为完成标准。

## 2. 关键路径与可并行工作

```text
W-V00 连接与能力基线
       ↓
W-V01 跨语言契约及安全媒体面
       ├── W-V02 原生采集与输入轮次
       ├── W-V03 流式输出及取消
       └── W-V04 持久声音身份
                     ↓
         W-V05 动态选角与表演
                     ↓
W-V06 播放恢复与场景混音 → W-V07 缓存与负载治理
                     ↓
W-V08 故事书音轨 / 撤销 / 清理
                     ↓
W-V09 真实游戏闭环 → W-V10 质量、无障碍与发布
```

W-V09 依赖真实 Domain 持久化服务，可以与媒体实现并行开发；不要把它藏在最后才发现。W-V02/03 的契约必须先固定；共改 `contracts/`、组合根或同一文件时串行集成。跨仓只使用 HTTP/WebSocket/版本契约，不共享 Python 虚拟环境或 import。

不设置臆测完成日期；任务按前置能力与验收证据推进。以下角色是责任建议，不表示已经运行独立多 Agent。

## 3. 任务卡（每项包含可运行交付）

### W-V00 — 连接与能力基线

**责任**：AGT-VOICE；复核 AGT-ARB。**依赖**：已运行的 SpeechRail 由用户明确提供或启动，不在探测时安装/下载。

**已有落点**：`engine/infrastructure/audio/config.py`、`openai_adapter.py`、`engine/domain/audio_voice.py`、`engine/tests/test_audio_adapter.py`。

**工作**：修正缺省 loopback 端点，保留显式配置优先级；unknown confidence 改为可空并追踪来源；兼容旧整段 API 的包装层不改变旧调用方签名意义；服务实例/模型/音色发现和参数拒绝映射。配置错误与 backend not ready 分开；不得把任意 URL 的失败静默重定向至云端。

**交付**：本地协议捕获测试；在用户许可的已安装服务上完成短 ASR/TTS smoke，记录实际版本与能力，不保存原始音频进公共仓库。**完成标准**：现有调用不回归，unknown 不变成 1.0，配置覆盖有测试。**回退**：旧 adapter 保留，关闭 v2 路由，不修改已有音色。

### W-V01 — 契约、权限与独立媒体通道

**责任**：AGT-ARB + AGT-VOICE + AGT-MAC。**依赖**：W-V00；新增 public schema/IPC/迁移必须显式 grant。

**已有落点**：`contracts/schemas/performance_plan.schema.json`、`audio_asset_ref.schema.json`、`contracts/protocol/engine_ipc.schema.json`、`engine/infrastructure/ipc_server.py`、`macos-app/WorldOfMysteries/EngineIPCClient.swift`、`DomainContracts.swift`。

**拟新增**：`contracts/schemas/voice_persona.schema.json`、`voice_binding.schema.json`、`speech_unit.schema.json`、`playback_receipt.schema.json`；`contracts/protocol/engine_media.schema.json`；Python/Swift 对应 DTO 与 roundtrip fixtures。路径与版本需在本任务设计评审确认后才创建，当前文档没有发布这些 API。

**工作**：确认严格 v1 不接受未知字段的影响，以能力协商选择新消息，不把新字段直接混入旧包；为 SpeechUnit、PlaybackReceipt 和媒体 ticket 绑定 engine epoch、scope、generation、schema version；实现短 UDS 地址、鉴权、长度上限、frame/credit/backpressure、无 payload 的控制 IPC。旧客户端明确拒绝不兼容模式或走旧整段路径。

**完成标准**：畸形帧/错误 peer/ticket 重放/过期权限/大包/乱序在边界拒绝；Swift↔Python schema roundtrip；媒体阻塞时暂停控制仍可用。**回退**：只关闭 v2 capability，旧控制协议不变；不得关闭 Sandbox 或 Library Validation。

### W-V02 — 原生采集、ASR 与完整输入轮次

**责任**：AGT-MAC，AGT-VOICE 配合。**依赖**：W-V01。

**拟新增模块**：`macos-app/WorldOfMysteries/Media/` 下 Capture、ASRTransport、InputTurnAssembler、EndpointPolicy；不要假定已有 WorldSession.swift 文件。

**工作**：AVAudioEngine 设备实际格式、一次重采样、可验证 AEC 参考；独立 ASR Realtime 连接；首版 PTT/manual endpoint，服务 server_vad 仅作为互斥兼容模式；多个 rollover item 聚合为一个 input_turn_id；partial 仅 UI；连接 epoch 与 item 去重；否定、自我修正与实体歧义进入确认策略。首版不得依赖尚无证据的语义端点模型。

**完成标准**：“先不要……等等”不提前提交；final/rollover 乱序、重复、缺失不重复回合；断网不会自动重放未确认音频；原生采集与外放回声实测。**回退**：PTT＋文本输入；禁用不合格免按键模式。

### W-V03 — 流式 TTS、独立媒体面与本机优先取消

**责任**：AGT-VOICE + AGT-MAC。**依赖**：W-V01；W-V02 可并行。

**拟新增**：`engine/application/voice_turn_coordinator.py`、`engine/infrastructure/audio/speechrail_realtime.py`、`media_bridge.py`；Swift Media 下 Playback/MediaStreamClient。

**首版路线**：独立 TTS Realtime 连接，单个活动 response，`conversation.item.create(input_text)` → `response.create`；不得与 ASR 共用会自动 barge-in 的连接。HTTP streaming 增强由上游 Issue 跟踪，未满足完整性交付证据时不承诺持久完整缓存。

**工作**：NarrativeBlock 完整验证后分句；没有 sealed segment 契约时不偷读未完成 LLM token。将响应音频组归一成 AudioFormat/Chunk/End/Error；检查 response_id、seq、PCM 偶数字节与总采样数；流关闭总 deadline；旧 generation 数据拒收；用户 stop 先执行本机清队列/失效，再异步网络 cancel。音频 render callback 不执行网络/JSON/文件/阻塞操作。

**完成标准**：真实服务可边生成边听；在首块前、句中、结束竞态均可取消；迟到块不回声，断流不发布完整 take；控制路和数据路互不无限等待。**回退**：完整音频短句路径或字幕，不重跑 Domain。

### W-V04 — 声音身份、版本与绑定持久化

**责任**：AGT-DOM + AGT-DATA + AGT-VOICE。**依赖**：W-V01；强上游版本锁定依赖 SR-V02。

**已有基础**：`engine/infrastructure/database_manager.py`、`database_schema.py` 与既有 migrations。**拟新增**：Domain voice identity 值对象；Application casting commands；infra binding repository/migrations。

**工作**：固定 Persona 与 ProviderRevision；CAS 建立 binding，首次输出前先持久化 reservation，丢失播放 ACK 不重新随机选角；音色更换有新 revision，世界线复制分叉快照，旧音轨仍引用旧 take；presentation revision 不冒充新的世界事实 revision。独立 revision pin 未就绪时只允许显式冻结合格音色并标为 legacy assurance；前后查询不能被宣传为原子的精确版本保证。

**完成标准**：重启/并发首次选角只产生一个有效绑定；已听角色升格不换声；撤销后即使缓存命中也禁止新用；迁移保留旧数据且不伪造缺失的 model revision。**回退**：保留旧绑定/旧 take，只禁新选角，不能破坏性 down-migrate。

### W-V05 — 智能选角、声音披露与有效表演

**责任**：AGT-VOICE + AGT-AI，AGT-DOM 审核授权。**依赖**：W-V04、现有 Context/Gateway。

**拟新增**：`engine/application/voice_casting.py`、`performance_compiler.py`、`audio_disclosure.py`。通过只读 Domain port 获取批准的 persona/presentation identity，不让 AI 直读数据库。

**工作**：先硬过滤语言、用途/同意、质量、availability，再在未绑定角色间联合优化场景共现辨识；确定性 tie-break；已绑定声线不可被局部优化改写。区分 desired/effective performance：Base clone 保持 speed=1.0、不发送 instructions，pause/volume 由 Timeline/Mixer 执行；仅支持的 native 能力出站。DisplayText/SpokenText 映射保留数字、否定与专名语义。

**完成标准**：只改变隐藏真相的反事实样例不改变公开声音/字幕/SFX；面具身份不能被旧熟悉音色意外揭露；unsupported 参数不漏发；“以后都用这个声音”与“这句轻一点”分成不同命令。**回退**：已批准静态绑定＋中性同身份表演。

### W-V06 — AudioTimeline、恢复和设备变化

**责任**：AGT-MAC + AGT-VOICE。**依赖**：W-V03/04。

**工作**：Speech/Narrator/Ambience/SFX/UI 通道；仅一个重要人声默认前景；系统 voice-processing ducking 与应用 ducking 交互实测；正常 EOF drain 不吞尾字，cancel 不输出尾巴；DeliveryCursor 区分 queued/rendered/estimated-output/fully-output；跨重采样/播放速度映射原始 sample offset；恢复重播句首而非伪造字级游标。

**完成标准**：耳机拔插、蓝牙切路由、App suspend/restart、短声误打断恢复；`dataConsumed`/排队完成不被记为已输出；没有硬件回环时明确游标是估计。**回退**：句级恢复＋清晰人声模式，设备故障保留字幕。

### W-V07 — 六层缓存、有限预取与负载治理

**责任**：AGT-VOICE + AGT-DATA + AGT-AI。**依赖**：W-V03/04；参考特征增强 SR-V05、HTTP 交互调度 SR-V04。

**工作**：实现完整 RenderManifest HMAC、AudioTake 文件 SHA256；单句 dry voice 与场景效果/播放速度 key 分离；临时文件成功后 fsync/原子发布；single-flight 相同 render 的独立订阅取消；所有条目 bounded；最新授权复核；只预取已提交、已获披露且已封定下一单元，不预生成未选分支。SpeechRail 管模型 admission，本应用只给 purpose/预算，不自行卸载其 worker。

**完成标准**：断流/取消/权限变更/同ID不同reference不误命中；冷暖与实际后端读写指标区分；实时活动中后台质检不得驱逐当前 TTS；未知成本/命中不记零。**回退**：禁用预取与条件缓存，保留按需合成/本地合法音频。

### W-V08 — 故事书、重配音、撤销与垃圾回收

**责任**：AGT-DATA + AGT-VOICE + AGT-MAC。**依赖**：W-V04/06/07。

**工作**：原版音轨只引用实际 take；重配音创建新的 track revision，不覆盖 Narrative；被音轨引用资产 pin，runtime cache 可重建；撤销的访问控制先行，垃圾回收异步可重试；磁盘不足、不完整资产与用户主动清理有可见状态；新音轨不得复用被禁止的声音授权。

**完成标准**：断网打开完整保留的故事书不调用模型；删缓存不丢绑定；关闭应用时的 file→manifest 故障注入不会出现 phantom 完整音频；授权撤销不声称可抹除第三方已导出的副本。**回退**：只读原版合法音轨。

### W-V09 — 真实世界回合接线

**责任**：AGT-AI + AGT-DOM + AGT-VOICE。**依赖**：真实 Session/Application/Writer 与 W-V02/03/05。

**已有落点**：`engine/application/session_orchestrator.py` 当前是协议边界；`gameplay_context.py` 为上下文协作，不等于完整事务实现。

**工作**：FinalTranscript 映射 PlayerAdvice 幂等命令；同一 writer 裁决 cancel vs commit；lost ACK 查询原 turn status；COMMIT 后声音故障仅重试表达；当前知识/世界线/disclosure epoch 与声音 scope 一致；ControlIntent（停止/继续/音量）不创建世界行动。对领域服务缺口提供端口与契约测试，不静默写假状态。

**完成标准**：Golden 场景多轮、重启、打断、Closure 与 episode finalization 均使用真实数据；重放相同 input_turn 不重复推进世界；未听完叙述不自动赋予用户理解或角色新知识。**回退**：关闭 `story_voice`，保留原文本与 media_demo 明确分离。

### W-V10 — 真机体验、质量与发布

**责任**：AGT-QA + AGT-MAC + AGT-VOICE。**依赖**：W-V09，已批准音色，SR质量待办和打包签名独立门禁。

**工作**：执行[验收矩阵](Voice_First_Acceptance_v2.0.md)，冷暖/设备/争用分组报告；中文盲听与同场辨识；逐条记录不支持功能；签名/公证不因音频功能通过而推定完成。UI 自动化、录屏、真实录音和服务操作必须取得相应明确授权，SpeechRail 自动化遵循其仓库规则。

**完成标准**：四级证据齐全；真实端到端统计和已知不足；local-only 没有云端请求；卸载/回滚不丢世界和历史音轨。**回退**：关闭 feature flags、不破坏性迁移、保留原批准声线和原音轨。

## 4. PR 与 HACF 范围安排

当前方案 PR 仅 Markdown，使用文档变更路径，不伪造运行时凭单。后续建议按四个能运行的工程目标组织 PR，各 PR 内持续原子增量，不按文件制造 micro-PR：

| 后续目标 | 覆盖任务 | 必需角色/授权范围 | 退出条件 |
|---|---|---|---|
| Voice Transport Vertical | W-V00–03 | ARB、VOICE、MAC；contracts/IPC 获 grant | 真实媒体链可说可听可停；不冒称完整游戏 |
| Stable Casting & Performance | W-V04–05 | DOM、DATA、VOICE、AI；迁移获 grant | 持久绑定与合法表演闭环 |
| Playback Continuity & Assets | W-V06–08 | MAC、VOICE、DATA | 设备/恢复/缓存/历史资产闭环 |
| Story Voice Integration | W-V09–10 | DOM、AI、VOICE、QA | 真正持久回合与声学/发布验收 |

每个正式实现任务执行当前仓库 pack→隔离工作区→代码提交→原始 verify→凭单独立提交→PR。合入目标发生变化时刷新契约，不用 allow-stale 绕过。并行修改受保护门禁、公共 Schema、迁移须先获得仲裁范围。

现有 `VOICE_P0` 仅覆盖架构与旧 adapter 单测。W-V01 需要为新增输入/媒体/身份/缓存/Swift tests 提交门禁扩展评审；命令仅落在受保护 gate profile，并刷新 registry。本文列验收语义和测试 ID，不创建一套文档外的第二验收命令源。

## 5. SpeechRail 依赖与不等待策略

使用 SR-V01..SR-V07 作为稳定任务键，真实 Issue 号码在[跨仓接口文档](../03_工程规范/voice/SpeechRail_Integration_Contract_v1.0.md)维护。

| WoM能力 | 上游依赖 | 在未完成前可交付什么 | 不可作出的承诺 |
|---|---|---|---|
| 双 Realtime 媒体 demo | 现有 Realtime | PTT、固定现有音色、原生停止 | 真正世界提交/已测声学性能 |
| 精确能力消费 | SR-V01 | legacy allowlist＋实际错误拒绝 | 仅凭模型名支持所有参数 |
| 强声音版本锁定 | SR-V02 | 固定批准 ID，记录 legacy assurance | 跨管理更新的原子同版本保证 |
| HTTP实时/持久完整缓存 | SR-V03/04 | Realtime terminal 后验收/缓存 | HTTP EOF 就证明内容完整 |
| 更快的重复 clone | SR-V05 | 已有波形缓存＋本地 take 缓存 | 已经复用 speaker/acoustic 条件 |
| 批准声音质量 | SR-V06、现有 #34 | 明确范围的人工试听/参考检查 | 201/pass 即完整身份/表演认证 |
| 丰富情感但同身份 | SR-V07 | 中性固定身份＋安全 Timeline/DSP | clone 任意 emotion/speed 原生有效 |

## 6. 发布开关与默认值

建议独立开关：`voice_transport_v2`、`story_voice`、`hands_free_input`、`dynamic_casting`、`voice_creation`、`audio_prefetch`、`cloud_voice_fallback`。全部默认关闭直到各自门禁通过；开发 media_demo 由显式入口开启。基础语音上线后，PTT 可先开，免按键与云端不自动随之开启。

版本升级先读旧数据，新增字段的 unknown 可回放既有合法文件但不能提升为精确身份保证；不可原地修改用户的参考音色。每轮实施报告分别给出已实现、已接真实服务、已测设备、未完成四栏。
