# Voice-First Runtime v2.0 — 技术设计

日期：2026-09-19。状态：**待实现、待评审的技术契约，不是已上线能力**。
固定代码基线：WorldofMysteries `591b4900606c122cb07416cd71fd56b66d056423`；SpeechRail `28755de8cc51046f25ce75c7869fe1bacd34752d`。

入口：[语音工作包](README.md)；[实施计划](../../07_工程启动/Voice_First_Implementation_Plan_v2.0.md)；[跨仓契约](SpeechRail_Integration_Contract_v1.0.md)；[验收矩阵](../../07_工程启动/Voice_First_Acceptance_v2.0.md)。

## 1. 决策、继承与本轮细化

继承 [Audio / Voice 基线](../../02_领域引擎/Audio_Voice_Engine_v1.0.md)、[事务编排](../Runtime_Orchestration_v1.0.md)、[玩法上下文](../Gameplay_Context_Cache_Strategy_v1.0.md)。声音表达已提交事实；人物身份、知识授权与领域提交均不交给语音服务。此设计落实前一轮《Voice-First Runtime v2 与动态音色管理方案》，不是重新定义游戏。

| 决策 | 具体约束 | 对前一方案的关系 |
|---|---|---|
| D01 本地默认 | SpeechRail 独立 Python 3.12 服务，游戏 Engine 维持其锁定 Python；不合并环境、不跨仓 import | 保持 |
| D02 真正可打断 | 本机停声先于网络 ACK；最终取消游戏行为由领域 Writer 判定 | 将 Commit 边界细化为竞态可执行规则 |
| D03 双连接先行 | 首版 ASR 与 TTS 分别使用现有 Realtime 连接；ASR 只发送语音输入，TTS 只发送已封定文字 | 原方案偏好 ASR WS + TTS HTTP；源码核对发现 HTTP TTS 为 BATCH_TTS，且 PCM 无独立完成凭据，因此先走可验证双 WS，HTTP 作为后续协商路线 |
| D04 身份与表演分离 | VoicePersona → Binding → ProviderVoiceRevision；单句 Performance 独立编译 | 保持并增加 CAS、来源和版本规则 |
| D05 先配音池后动态创造 | 热路径只使用已验收声音；创建/质检不与互动争抢重计算 | 保持 |
| D06 两种“完成” | Provider 完成≠设备播放完成≠用户理解；生成资产与 DeliveryCursor 分开 | 保持并定义事件时钟 |
| D07 非静默降级 | local-only 不上云；重要人物不随机换 default voice；未支持情绪明确降级 | 拟替代旧基线的宽松 default_voice 回退，须经评审并完成实现后生效 |
| D08 无额外权威库 | world.db 保存绑定/音轨等持久表现元数据；assets 保存实际音频；runtime.db 仅做可重建索引 | 保持 |

本轮只落文档和跨仓 Issue，不修改现有协议、数据库迁移、App 启动或 SpeechRail 运行态。所有新增名称均为待实现接口。文中的性能数字是验收目标，不是当前测量结果。

## 2. 已核实的源码事实

### 2.1 游戏侧

- [config.py](../../../engine/infrastructure/audio/config.py) 默认 `localhost:8080/v1`，应迁移默认发现到 SpeechRail 当前 `127.0.0.1:8201/v1`；用户显式配置不覆盖。
- [openai_adapter.py](../../../engine/infrastructure/audio/openai_adapter.py) 完整读取合成音频后返回；ASR 未取得置信度却填 `1.0`。应新增流端口并将未知置信度保持 unknown，旧整段接口通过兼容包装保留。
- [audio_voice.py](../../../engine/domain/audio_voice.py) 目前为整段 bytes Protocol，不是已建成的播放 Runtime。
- [performance_plan.schema.json](../../../contracts/schemas/performance_plan.schema.json) 和 [audio_asset_ref.schema.json](../../../contracts/schemas/audio_asset_ref.schema.json) 已有 persona/performance/text/model revision 字段；必须复用语义并通过契约版本演进。
- [session_orchestrator.py](../../../engine/application/session_orchestrator.py) 仍是接口，不能把测试中的模拟 Commit 当作已接真实游戏回合。
- [VOICE_P0](../../../.hacf/gates/voice_p0.json) 目前只含架构检查与旧 `test_audio_adapter.py`；未来新增模块不能仅依赖此旧门禁宣称全覆盖。

### 2.2 SpeechRail 侧

固定版本已提供 Realtime ASR/TTS、HTTP 音频流、VoiceDesign/Base 双 capability worker、目录、生成参考注册及质量探针。[SR1–SR6]

已有的能力不能重复申请为“新增”：ResourceGovernor 已有 realtime reservation、batch FIFO/aging 与 capability lane；worker 已有参考**波形**缓存；Realtime 已有 `response.cancel` 与 `response.done`；目录已区分 voice 的 variant 与基本能力。

实际待补的是：一致快照与精确参数域、不可变 revision 与推理条件检查、HTTP 可验证完成/优先级、编码后参考条件缓存、独立身份/表演质量证据。Base clone 现阶段拒绝 instructions、非 1.0 speed 和调用方 seed；`/voices/designs` 注册成功不代表 Base 合成质量已通过。

## 3. 运行时拓扑与模块所有权

```text
Swift App
  MicrophoneGraph / VoiceProcessing / UtteranceAssembler
    └─ StreamingASRClient ──独立 WS── SpeechRail
  NativePlaybackActor / AudioGraph / SubtitleTimeline
    └─ 受保护媒体 UDS ← Engine MediaBridge ← 独立 TTS WS ← SpeechRail
  Session UI
    └─ 现有鉴权控制 IPC + 新增协商的 voice 控制方法 → Local Engine

Local Engine
  VoiceTurnCoordinator
  Gameplay Context / Domain Writer / Narrative
  AudioDisclosureService → VoiceCastingService → PerformanceCompiler
  SpeechRenderCoordinator → ProviderAdapter / MediaBridge / AssetStore
  VoiceBindingRepository / AudioTrackRepository / DeliveryCursorRepository

SpeechRail
  public protocols / VoiceRegistry / reference preparation
  ResourceGovernor / capability workers / inference / quality evidence
```

App 持有设备和 ASR 物理客户端，Engine 决定获准热词、游戏输入提交和叙述合成。TTS 走 Engine 便于统一授权、资产落盘和模型路由；ASR 直接连接遵循既有进程所有权，不为每一帧再经过领域 IPC。云端 ASR 必须由获准配置启用且单独披露数据流向。

本方案不创建分布式语音集群、不复制模型进程、不建设跨用户声纹库；不用更换整套 Agent 框架来回避现有事务边界。

## 4. 数据模型与不变量

### 4.1 不可变对象

| 对象 | 必需语义 | 权威归属 |
|---|---|---|
| VoicePersonaRevision | logical_id、revision、语言、音域/质感/咬字/节奏、允许表演与禁忌、来源 | 内容包默认或游戏持久表现元数据 |
| VoiceBinding | owner/world/worldline、presentation_identity、人物阶段、locale、persona_revision、provider_voice_revision、binding_revision、状态 | world.db，独立表现 aggregate revision |
| ProviderVoiceRevision | provider_instance、voice_id、immutable revision 或显式 unknown、resolved model/variant/量化、参考与预处理指纹、质量证据 | SpeechRail；游戏仅保存受控引用和快照 |
| AudioGrant | 当前 policy_revision、消费者、presentation_identity、台词/音色/字幕/SFX 许可、过期/撤销条件 | 可信 Application 授权，不接受 LLM 自制 grant |
| SpeechUnit | unit_id、turn_id、narrative_id+revision、segment_index、sealed、grant_ref、binding_revision、display/spoken text、effective performance | Engine；仅合法不可修改表达 |
| RenderManifest | 配方指纹、实际后端身份、格式、端到端终态证据、sample count、内容校验 | 持久媒体元数据 |
| AudioTake | take_id、manifest、实际文件 sha256、完整性状态、来源和引用 | assets + world.db 音轨索引 |
| DeliveryCursor | track/unit、generation、已输出源采样偏移、偏移证据类型、停止原因、revision | world.db 持久表现元数据，不改剧情事实 |

不把用户名、真实隐藏身份、参考全文或凭据放进外部 cache key/日志。逻辑 ID 只在获准范围内流转；第三方只收到它执行需要的字段。

### 4.2 持久化最小设计（表名为提案，未执行迁移）

| 建议表 | 主键/唯一约束 | 写入规则 |
|---|---|---|
| voice_persona_revisions | (logical_voice_id, revision) | insert-only，停用另记状态 |
| voice_bindings | (owner, world, worldline, presentation, phase, locale) | `WHERE binding_revision=expected` 的 CAS 更新；引用 immutable revision |
| audio_takes | take_id；文件 digest 与 render_key 分列 | 只有校验完成的 `.partial` 才能发布 |
| audio_tracks / audio_track_units | track_id；(track_id, ordinal) | 原版音轨不可被重配音覆盖 |
| delivery_cursors | (track_id, consumer) | 单调推进，同 generation；stop/seek 使用独立 revision |

数据库 Writer 仍由 Engine 控制。表现性绑定、暂停和听读进度不会提升世界事实 revision，不产生假的 WorldEvent。需要剧情意义的“角色衰老/伪装”先由领域事实驱动，再生成表现变体。

文件先临时写、校验、fsync、原子 rename，再登记可用 take；崩溃留下的无引用完整文件可 GC，绝不能让数据库指向半文件。反向删除先检查音轨 pin/授权，再标记不可用、删除实际文件；外部删除能力缺失要显示限制。

## 5. 输入轮次与 Commit 竞态

### 5.1 分离状态机

```text
Input: IDLE → CAPTURING → ENDPOINT_CANDIDATE → FINALIZING → FINAL_READY
                                         ↘ CAPTURING（用户续说）
                                                   ↘ FAILED/CANCELLED
Turn:  RECEIVED → ... → VALIDATING → COMMITTED → EXPRESSING → DELIVERED
Media: PREPARING → BUFFERING → PLAYING ↔ PAUSED → COMPLETED/INTERRUPTED/FAILED
```

ASR `input_audio_buffer.committed` 是转录缓冲边界，不是游戏 COMMIT。多个 ASR item 通过 `(asr_connection_epoch,item_id)` 去重并归入一个 `input_turn_id`；按服务 sequence 和前后 item 关系排序，不按网络返回时间拼接。

UtteranceAssembler 必须维护输入边界水位：本轮采样范围、已请求 finish 的序号、尚未得到终态的 item。所有对应终态齐备后才形成最终文本；到期缺片段返回 `TRANSCRIPT_INCOMPLETE`，不能只把最后片段当作完整建议。重连创建新 connection epoch；不重播未确认 PCM 来“猜测恢复”。

VAD 选择唯一主控：首版按键说话 + manual finish；再开放本地 endpointing，server_vad 仅为互斥配置。用户停顿、自我修正、否定句歧义不以 partial 执行。服务器产生的自动 rollover 仍纳入本轮聚合。

### 5.2 用户指令路由

明确的按钮/快捷键 pause/stop/replay 走本机媒体控制；语音“停止”先触发低风险本机停声，再确认是否为新建议。含否定或引用的“不要停”“他说‘停下’”不可仅凭关键词触发领域取消。

`开始说话`≠`作出新建议`：短应答先 duck/暂停，判定误打断后按 cursor 恢复；新建议经过最终转录和意图解释。高影响、实体歧义或否定冲突要澄清，未知 ASR confidence 不填 1.0。

### 5.3 必须解决的并发顺序

本机停止时先增 `playback_generation`，使旧媒体块失效；再调用 `TurnControlPort.cancel_pending(turn_id, expected_revision)`。取消和 Commit 在同一领域 Writer 序列化：

- 取消先赢：返回 `cancelled_before_commit`；释放 pending 工作，不生成世界结果。
- Commit 先赢：返回 `already_committed` 及 committed revision；只停止表达，新建议创建新 turn。
- ACK 丢失：查询原 turn 的幂等状态，不重新生成/重复提交。

客户端显示的 PRE_COMMIT 标签不能当作数据库尚未 Commit 的证据。取消 provider 失败不影响本机已停止，不允许旧 PCM 因迟到 ACK 再次入队。

## 6. 流式传输与媒体通道

### 6.1 SpeechRail 起步路线

ASR 连接只用于输入和转写，`turn_detection=null/manual`；TTS 连接只发送一条已封定 SpeechUnit 的 `conversation.item.create`，之后 `response.create`。等待该 response 的成功 `response.done` 才认为后端生成完整。首版一个活跃 TTS response，后续单元顺序排队；后台批任务不得偷偷争抢同一路径。

两条连接不意味着创建两套模型。它们仍服从 SpeechRail 现有 worker 准入，连接数与可执行推理数分开。`/v1/realtime` 不支持 `conversation.item.truncate`，客户端不发送它；用户已输出位置由游戏保存。

HTTP PCM 作为后续可选实现：没有可验证完成证据时，网络 EOF 只表明传输结束，不足以宣称语义完整与历史可重播；中断流不登记为完整 take。增强接口见跨仓契约。

### 6.2 App—Engine 媒体面提案

控制仍使用现有鉴权 NDJSON UDS；新增能力 `voice.media.v1` 只在双方支持时启用。音频不以内嵌 Base64 挤入领域消息。

Engine 经鉴权控制面发出 `MediaStreamOffer`：短路径媒体 UDS、opaque stream_id、一次性 media_ticket、过期时间、format、unit_id 和 generation。ticket 绑定 App 会话、engine_epoch、连接对端及 grant；不放 URL query、不写日志。媒体监听仅同用户可访问，验证 peer uid，权限最小化；路径长度纳入现有 AF_UNIX 短路径策略。

帧提案：`WOMA` magic + version(u16) + type(u16) + header_length(u32) + payload_length(u32)，整数为网络字节序；header 为 UTF-8 JSON，payload 为协商后的 PCM。首版 header 上限 4 KiB、payload 上限 256 KiB，都是工程边界，必须在分配内存前验证。帧类型 FORMAT/CHUNK/END/ERROR/CANCEL_ACK/CREDIT。

CHUNK header：`stream_id / engine_epoch / unit_id / generation / seq / sample_offset / sample_count`。PCM16-LE 为初始支持，sample_rate/channels 不猜测；`bytes == sample_count * channels * 2`，offset 连续、seq 严格递增。奇数字节网络块在适配器中重组，终态有残字节即错误。

END 必须包含 total_samples、接收音频 digest、provider terminal kind；digest 只能证明完整接收与一致性，不证明没漏读文字。ERROR/取消不 flush 过期尾部。信用按可接纳媒体时长计算，并设置字节硬上限，避免高速推理淹没播放内存。慢消费者有界 backpressure；取消控制不能堵在 PCM 队列后。

### 6.3 过渡与升级

未知 `voice.media.v1` 时保留旧整段 SpeechResult/AudioAssetRef 路径；不向 v1 的 `additionalProperties=false` 消息追加新字段。新 Schema、Python/Swift DTO、NDJSON 方法集合与版本协商在 W-V01 同步落地，禁止只改一端。

## 7. 原生音频实现

推荐 AVAudioEngine 单一有控制的设备图；对白、环境声、SFX 与 UI 分 bus。回声消除使用平台 voice processing 能力并按设备路由验收；不可假设独立播放器都自动进入正确 echo reference。[E1]

音频回调只做有界缓冲和样本移动，不执行 JSON、网络、SQLite、模型、文件 I/O、MainActor 工作或潜在阻塞锁。采样率转换与解码放专用媒体队列，保留设备真实格式，单次有状态重采样；configuration change 先停止/升 generation，再重建图。

`NativePlaybackActor` 串行控制设备与播放器状态，SwiftUI 仅接收节流后的状态更新。源采样时钟、设备时钟和 UI 时间分开映射；变速/seek 后 cursor 仍按源音频偏移记录。schedule completion 不是扬声器已响；存储 `scheduled / rendered_estimate / measured_loopback` 证据等级。

蓝牙路由改变、耳机断开、系统睡眠、麦克风授权撤销：停止旧输入/输出、保存 cursor、回到显式可恢复状态；不自动重放用户旧建议。AEC 不可用时回退按键说话/半双工并明确状态。

## 8. 动态选角与身份版本

### 8.1 Casting Scope

输入只能是当前允许呈现的身份、公开声音特征、语言、人物阶段、当前同场角色与其已绑定声音。隐藏真身和未公开关系不能影响可闻选角，除非该声音识别本身是获准线索。

候选先按 rights/locale/availability/quality 硬过滤，再优化：人设贴合、场景可区分度、已绑定连续性、准备时延与成本。已有绑定为硬锁；新角色采用确定性 tie-break。第一版采用小集合穷举/贪心后局部改良即可，不提前引入全世界图优化。

多角色并发首次出现：先事务保留 binding，再允许首块输出。第一次收到输出回执后标 sticky；即使回执丢失，已有 reservation 也不能被下一请求随意重分配。角色升格不自动换声。

世界线分叉继承分叉点可见的 binding revision，不继承未来变体。声线替换需要显式用户命令/CAS，新 revision 在句或场景边界生效；历史音轨不变。

### 8.2 创建流程

`DRAFT → CANDIDATE → REFERENCE_VALIDATED → SYNTHESIS_TESTED → IDENTITY_ACCEPTED → PUBLISHED`，任何阶段可失败或取消；`DEPRECATED` 和 `REVOKED` 语义不同。

VoiceDesign 仅在准备期生成候选；Base 负责稳定参考合成。`/voices/designs` 201 为参考注册成功，不提升到 PUBLISHED。录音克隆必须具备用途授权，不能把游戏每句合成音频自动回灌为新参考。

首版内容验收从旁白 + 3–5 个主要人物开始；12–24 个基础候选音色为后续内容目标，不是上线前所有人物都必须专门训练。旁白转述必须使用已经审核的替代表达模板，不得临场再造新事实。

## 9. 表演编译与读音

PerformanceCompiler 输出 desired/effective/unsupported/degradation 四部分。停顿与轻度音量进 Timeline/Mixer；后端情绪/耳语/重音只在 voice 级能力确认后下发。Base clone 保持 `speed=1.0` 且不发 instructions/seed，当前不支持的表演降级为有限播放层操作或中性同声线，不切 VoiceDesign 重新造人。[SR2]

用户全局播放速度属于播放配置，不改 RenderKey 的干声部分；TTS 原生 speed 若确实使用则属于配方。显示文本与实际朗读文本分别保存；数字、人名和术语替换有版本与 span 映射，否定词、量值、单位不可改变。字级字幕只有真实对齐证据时开启，起步只做句级。

高位存在：保留清晰主体声线，空间效果另存 EffectChain revision，提供低刺激/清晰语音开关。不用削波、大音量或听不清的叠声冒充位格。

## 10. 缓存、预取与调度

```text
Context prefix：稳定规则、获准 persona → 动态台词尾部
Voice catalog：短时快照，使用前验 revision/撤销
Reference conditions：SpeechRail 内不可变参考特征，不共享目标 decoder/KV
Dry speech take：完整配方 key + 实际文件 digest
Playback ring：短时有界 PCM
StoryBook track：被引用 take pin，不当作可随意淘汰的 cache
```

RenderKey 使用带私有 key 的 HMAC(canonical_json)，覆盖实际 provider instance/model revision/variant、voice revision、参考指纹、spoken text、effective backend performance、读音字典/renderer revision、输出格式及实际使用的 conditioning。unknown revision 必须写明 `reproducibility=unverified`；不以 alias/seed/mtime 冒称可重现。

音轨内文件 checksum 独立于 key；相同请求可有不同波形。已选 take 固定保存，重配音创建新 track。授权撤销与删除优先于 pin；失效条目不读缓存、不送云端，旧文件清理策略可追踪。

相同完整 key 的并发合成采用 single-flight；每个等待者独立取消，最后等待者离开才取消共享渲染。权限和 generation 在交付前再次检查；不同 turn 不能因为台词相同就合并领域执行。

首版预取上限：下一已封定语音单元，最多 2 个待执行单元；缓冲初值 0.2–0.5 秒起播、约 4 秒高水位，必须按实际语速/RTF/设备调整，不构成服务延迟承诺。预取不推测未选择结局，不保活空请求。

调度顺序：停止/设备事件 > 用户 ASR/首句 > 当前下一句 > 有界预取 > 设计/质量/重配音。SpeechRail 负责具体 worker 预算和锁，游戏不再造一套驱逐器。时间预算传相对毫秒，服务端转换为自身 monotonic deadline；禁止跨进程比较不同时钟原点。

## 11. 故障、恢复与版本迁移

| 情况 | 行为 | 禁止 |
|---|---|---|
| 后端忙/超时 | 期限内一次有界重试或字幕，保留失败类别 | SDK/网关/业务三层叠加无界重试 |
| voice 不可用 | 缓存同 take → 同绑定重试 → 获准备用 → 字幕 | 半句随机 default_voice |
| provider 重启 | catalog epoch 失效，重新发现，旧 PCM generation 拒绝 | 自动假定 alias 指向同一声线 |
| stream 断裂 | `.partial` 不发布；仅重做未完成表达单元 | 重跑 Domain Commit |
| App/Engine crash | 读取 turn 持久状态、track、cursor，从边界恢复 | 把未听完当作事实未发生 |
| cloud 失败 | 按用户已批准的本地映射或字幕 | local-only 外呼 |
| 旧 schema | 保留兼容整段读路径 | 原地塞字段破坏严格 DTO |
| voice revision 撤销 | 禁止新使用，按策略停播/清理衍生品，标记音轨不可用 | 为离线承诺永久保留无权使用的声音 |

已有音频标 legacy，保留实际文件，不补造未知 model/voice revision。新写入采用新 manifest，旧回放继续可用；数据迁移失败保持旧库和资产，不做不可逆覆盖。正式发行继续遵守同 Team ID、Sandbox/Hardened Runtime/Library Validation 与公证要求，不能用语音改造绕过签名基线。

## 12. 端口与组合根

| Port / Service | 具体接线点 | 缺失时策略 |
|---|---|---|
| StreamingASRPort | Swift SpeechRail Realtime client | 按键录音整段转写兼容模式，标明无流式 |
| StreamingTTSPort | Engine SpeechRail独立Realtime适配器 | 旧整段 TTS，只在成功后播放 |
| VoiceCatalogPort | 当前 models/voices；未来一致快照 | 保守能力，不猜参数 |
| VoiceBindingRepository | Engine 数据基础设施 + CAS | 仅显式固定角色集，不启用动态选角 |
| AudioDisclosurePort | Context/application授权服务 | 缺少真实授权禁止生产播放，fake仅fixture |
| TurnControlPort | 真正的事务Writer | 只能媒体demo，不声称游戏闭环 |
| SpeechAssetPort | 受控assets与音轨库 | 不承诺离线完整故事书 |
| VoiceCreationPort / VoiceQualityPort | SpeechRail创建/质检API | 原声音池继续工作 |
| PlaybackPort | Swift NativePlaybackActor | 字幕兼容 |

组合根 `VoiceServices` 明确注入真实/fake模式，生产启动不得把 fake authorize/commit 自动包装成真服务。协议伪代码由 W-V01 定义，实际实现路径见实施任务表。

## 13. 来源与证据口径

本地取得的是两仓固定 SHA 的 UTF-8 源码/文档范围快照及完整文件清单，不含二进制和完整 Git 历史；每个导出文件校验 Git blob SHA 与 SHA-256。没有运行 SpeechRail 服务、模型、benchmark 或 UI 自动化。代码事实与本文件提案分开。

- SR1 [服务定位与现有入口](https://github.com/hrygo/SpeechRail/blob/28755de8cc51046f25ce75c7869fe1bacd34752d/README.md)
- SR2 [实际TTS参数、BATCH_TTS与PCM返回](https://github.com/hrygo/SpeechRail/blob/28755de8cc51046f25ce75c7869fe1bacd34752d/src/speechrail/http/routes/audio.py#L1380-L1548)
- SR3 [现有Realtime契约](https://github.com/hrygo/SpeechRail/blob/28755de8cc51046f25ce75c7869fe1bacd34752d/contracts/realtime-openai.md)
- SR4 [波形缓存与Base生成调用](https://github.com/hrygo/SpeechRail/blob/28755de8cc51046f25ce75c7869fe1bacd34752d/src/speechrail/backends/qwen3_tts_worker.py#L458-L594)
- SR5 [voice目录/幂等/质量入口](https://github.com/hrygo/SpeechRail/blob/28755de8cc51046f25ce75c7869fe1bacd34752d/src/speechrail/http/routes/system.py)
- SR6 [双capability与生成参考注册边界](https://github.com/hrygo/SpeechRail/blob/28755de8cc51046f25ce75c7869fe1bacd34752d/docs/architecture/quality-voice-capabilities.md)
- E1 [Apple voice processing](https://developer.apple.com/videos/play/wwdc2023/10235/)：平台能力依据，不是本App设备验收。
- E2 [Qwen官方VoiceDesign/Base与可复用clone prompt](https://github.com/QwenLM/Qwen3-TTS)：上游能力依据，不能推导锁定MLX vendor已有相同接口。
- E3 [OpenAI TTS流式输出](https://developers.openai.com/api/docs/guides/text-to-speech)：云端可选适配依据，不是所有兼容服务的能力承诺。
