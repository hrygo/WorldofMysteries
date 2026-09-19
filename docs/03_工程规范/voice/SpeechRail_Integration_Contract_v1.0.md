# SpeechRail 接入契约与跨仓依赖 v1.0

日期：2026-09-19。状态：**提议的接入与演进合同；下列新字段/操作尚非当前SpeechRail API**。

消费者基线 WorldofMysteries `591b4900606c122cb07416cd71fd56b66d056423`；供应者基线 SpeechRail `28755de8cc51046f25ce75c7869fe1bacd34752d`。总设计见[Voice-First技术方案](Voice_First_Technical_Design_v2.0.md)。两仓无共享Python环境和文件路径依赖。

## 1. 已有契约与不能假定的能力

已存在：`/health`、`/readyz`、`/v1/models`、`/v1/voices`、HTTP audio、独立Realtime ASR/TTS；voice级available/variant/capabilities；规范参考注册；Base与VoiceDesign独立worker；资源准入、取消与流式PCM校验。**不提出“重新实现流式TTS/基础调度”的重复任务。**

尚不能据此保证：所有发现信息来自同一可锁定snapshot、合成精确绑定不可变voice revision、HTTP raw PCM EOF具有语义完整证明、已实现speaker/acoustic条件缓存、质量总pass证明身份/自然度、Base接受任意emotion/instructions。

## 2. 首版直接接线：两个独立Realtime连接

- App负责ASR连接，Engine负责TTS连接；每条连接有独立connection_epoch、服务会话ID和单调sequence。
- ASR按实际协商格式append，在manual/null模式由唯一应用端点器commit；把多个item聚合成一个input_turn，partial不进入Domain。
- TTS使用一个text item和一个活动response，明确voice；当前支持的audio事件组归一成PCM；收到正常`response.done`并校验流后才允许发布完整take。
- 本机stop不依赖`response.cancel`成功；独立generation避免旧块回流。`conversation.item.truncate`不支持且不需要用于本游戏事实回滚。
- 请求被拒绝、连接终止、超时或无正常终态时清理临时流；已经完成的独立单元可继续合法回放。

这修订此前“首版TTS采用HTTP streaming”的建议：当前HTTP实现按BATCH_TTS准入且raw PCM缺少显式语义终态，因此先用已有Realtime的调度/取消/终态能力。不是宣称HTTP不能流式，也不是让两连接共享ASR状态。

### 2.1 普通 ASR 收口的已存在路径与消费者责任

已核查普通事件由 FIFO handler 串行执行，commit 等待 reader 后退出，clear 完成清理后发送 cleared。首版独立 manual/no-diarization 连接在本轮 append 全部排队完成后执行 `commit → clear → cleared`，收口期间不发送下一轮 append。不要只等某个 completed，也不要使用当前始终为空的 previous_item_id。所有 item 按 committed 的 service sequence 排序、按 connection epoch 与 item ID 配对。

cleared 仅是排空栅栏；本轮任意 append/commit error、failed item、缺终态或连接缺口都必须使整体失败。clear 不能把之前失败“洗成成功”；取消时的 clear 也不能生成 FinalTranscript。该路径不声称有源采样水位证明，不替代内容正确性验收。其他 Provider 未证明同一串行语义时退回明确支持的整段模式，不猜测等价。

这不是新协议提案；[SR-V08 / #69](https://github.com/hrygo/SpeechRail/issues/69) 将已有 legacy EOF 集中写入当前契约并补组合回归，保留 #10 已完成的语音准入工作。只有今后架构改变确需新 barrier 时才另行协商扩展。

## 3. 新契约草案（必须经上游评审/能力协商）

### C1 — EffectiveCapabilitySnapshot

建议通过SpeechRail专有discover能力或对已有发现响应作经审查的加法演进提供：`schema_version/service_instance_epoch/catalog_revision`、resolved model/artifact/variant、voice ID/revision、availability/reason、真实支持的参数取值域、输入输出格式、stream terminal证据能力、可用调度类别。

同一snapshot内的信息必须一致；不把description存在当成支持。读取不加载/卸载模型、不下载模型；缓存ETag或opaque snapshot ID仅供版本比较，不携带reference路径。标准SDK的旧请求不带这些私有字段；未知扩展先走legacy路径。

### C2 — ImmutableVoiceRevision与条件渲染

建议`voice_id`作为友好别名，revision作为不可变制品；生成/录音来源、参考音频与准确文本hash、preprocess/model身份、许可状态与质量报告绑定版本。别名CAS更新与immutable修订创建分开。

合成可选的expected revision必须在registry/model租约内原子解析并锁定，首PCM之前拒绝不一致；出站结果回传实际resolved identity。API名称/字段放在哪个SR命名空间需评审，不能在未支持的`/v1/audio/speech`中直接发送自造参数。

创建幂等建议按(owner, operation, key, canonical payload fingerprint)保存有界durable记录；同key不同payload明确冲突，未知完成状态先查询；并发ID不覆盖，重启不重复发布。现有clone内存幂等只能作为legacy优化，不是强保证。

### C3 — 可核验的语音交付

已有Realtime events保留。建议可选metadata记录实际resolved voice/model、format、累计sample count和已交付PCM digest、终态completed/cancelled/error及稳定失败码；HTTP通过独立可协商元数据/receipt能力提供同等证据，raw audio body保持兼容。

摘要仅证明该次流的完整生成/传输边界，不证明所有文字正确朗读，更不证明扬声器已输出。确认正常终态后应用仍执行本地PCM/时长/尾部检查；音质由质量门决定。取消不得伪造成功END；慢消费者和断流均有单一deadline与清理。

### C4 — 交互调度与维护隔离

建议经协商的purpose类别：interactive_asr、interactive_tts、playback_prefetch、voice_creation、quality_validation；普通旧请求保留原语义。客户端提供相对`timeout_ms`/budget，服务取min(请求预算,服务上限)，不比较不同进程的单调时钟绝对值。

现有governor保留为唯一资源事实源；低优先工作在真实可中断的单元边界让出，不能承诺抢占正在执行的Metal kernel。维护操作在活动流期间不得无条件驱逐整组模型；有界队列、aging、取消后租约回收和重试提示。与现有#44的调度/测量工作关联，而不是再建一套调度器。

### C5 — ReferenceCondition缓存

已有`_reference_audio_cache`缓存解码波形；本提案只增加实际模型API支持的不可变speaker/reference acoustic条件。key绑定内容hash、文本hash、preprocess、model/tokenizer/encoder revision、mode；限条目且限bytes；in-flight保护、LRU、重启/换模/撤销失效。

若固定MLX-Audio版本无公开且正确的预计算接口，记录该限制并保持波形缓存，不调用不匹配的VoiceDesign私有ICL、不共享目标文本mutable decoder/KV、不冒充完成。

### C6 — 多维质量与可审计发布

注册、参考、合成可懂度、跨文本身份、自然度、重复性分别报告状态与实际模型/声音revision；missing为unevaluated。固定seed和PCM重复性不是身份判据；没有声明确定性保证时，正常随机差异不自动等于不可用声音。独立speaker验证按真实语料校准，人工盲听是产品发布条件。参考/输出增益复用#34，不另设矛盾响度管线。

### C7 — 身份保持的表演能力实验

先如实声明Base clone不支持instructions和非1.0 speed，再评估有限参考变体或真实支持表达的后端。输出effective performance与不支持项；不支持则同身份中性合成，由App处理pause/安全volume。不能以逐句VoiceDesign重新设计来假装稳定人物表达。

## 4. Issue映射与优先级

以下12项Issue已在SpeechRail登记（2026-09-19），均为open待办，**不是已实现能力**。对应下游文档PR为[WorldofMysteries #69](https://github.com/hrygo/WorldofMysteries/pull/69)。稳定任务键不随Issue编号变化。

| 键 / 实际Issue | 优先级 | 范围 | 对WoM的依赖关系 |
|---|---|---|---|
| [SR-V01 / #62](https://github.com/hrygo/SpeechRail/issues/62) | P0 | C1有效能力snapshot | 启用v2能力自动路由前完成；legacy有界可用 |
| [SR-V02 / #63](https://github.com/hrygo/SpeechRail/issues/63) | P0 | C2版本锁定/并发/持久幂等 | 强动态身份承诺的前置 |
| [SR-V03 / #64](https://github.com/hrygo/SpeechRail/issues/64) | P0 | C3流完整性与resolved receipt | 完整缓存/HTTP增强；Realtime基础可先接 |
| [SR-V04 / #65](https://github.com/hrygo/SpeechRail/issues/65) | P1 | C4交互优先与维护隔离 | 高频Story体验/并发后台任务前置 |
| [SR-V05 / #66](https://github.com/hrygo/SpeechRail/issues/66) | P1 | C5条件特征缓存 | 优化项，不阻塞固定音色MVP |
| [SR-V06 / #67](https://github.com/hrygo/SpeechRail/issues/67) | P1 | C6多维质量 | 专属动态音色自动发布前置 |
| [SR-V07 / #68](https://github.com/hrygo/SpeechRail/issues/68) | P2 | C7身份保持的表达实验 | 可选增强，不阻塞中性固定身份 |
| [SR-V08 / #69](https://github.com/hrygo/SpeechRail/issues/69) | P1 | 已有普通ASR收口契约/组合回归 | W-V02安全聚合；不要求新增API |
| [SR-V09 / #70](https://github.com/hrygo/SpeechRail/issues/70) | P1 | 版本化发音词典/SpokenText映射 | 术语、人名、数字读音；不阻塞基础媒体MVP |
| [SR-V10 / #71](https://github.com/hrygo/SpeechRail/issues/71) | P1 | 结构化音色目录与最小披露视图 | 动态选角与安全发现；避免客户端解析私有ref_text |
| [SR-V11 / #72](https://github.com/hrygo/SpeechRail/issues/72) | P1 | 长文本planner与跨句韵律连续性 | 长叙述自然度/一致断句；基础短句可先用 |
| [SR-V12 / #73](https://github.com/hrygo/SpeechRail/issues/73) | P2 | 可选TTS文本-音频时间轴sidecar | 字幕/口型/精确回放增强；不阻塞首版句级时间轴 |

### C8 — PronunciationSet 与 SpokenText 映射

SpeechRail 管通用发音规范化，不管理业务 DisplayText。词典按语言和 revision 版本化，输出 deterministic SpokenText + span mapping；否定、数字、单位、URL、缩写和混合语言需守恒。是否存在模型原生 phoneme/SSML 是独立 capability，未知时不能静默接受。

### C9 — 结构化 Voice Catalog 与最小披露

voice catalog 应区分“合成选择需要的公开目录元数据”和“参考正文/来源证明等私有详情”。结构化 descriptor 只描述合成表现与声明标签，不做真实人的敏感属性或声纹身份推断；与 C1 能力、C2 revision 分开。

### C10 — TTS Planner / Prosody Contract

历史 #18 已完成 REST/Realtime/preview 的 planner 基础。本阶段只追踪 planner_version、实际断句策略、跨 chunk 韵律连续性证据及 Realtime 文档/实现一致性。没有 vendor 上下文能力时如实采用确定性 pause/crossfade，而不是冒充模型上下文。

### C11 — Optional TTS Timing Sidecar

对已生成音频可选提供 chunk/word 等分级时间映射；没有可靠证据时为 unavailable。若复用现有 FixedTextAligner，必须解决 24k TTS 与 16k aligner 的坐标映射，并放在受治理的可选后处理，不阻塞首 PCM。该 sidecar 不代表设备已播放。

现有[#34响度](https://github.com/hrygo/SpeechRail/issues/34)和[#44架构演进](https://github.com/hrygo/SpeechRail/issues/44)继续负责既有范围；不重复建响度修复或全局架构epic。所有Issue是待办，不代表创建后功能已可用。

## 5. 责任、版本和联调

| 环节 | SpeechRail负责 | WorldofMysteries负责 |
|---|---|---|
| 输入 | 实际ASR、服务item/sequence、工作队列 | 采集/AEC、发言结束、input_turn/Advice |
| 输出 | 模型合成、参数执行、服务取消/terminal | seal/disclosure、播放generation、设备停止 |
| 音色 | Provider制品、版本/参考/质量证据 | Persona/Binding/场景选角/匿名身份 |
| 缓存 | 模型参考条件及worker生命周期 | take/音轨、pin/授权、干声/效果分离 |
| 观测 | queue/compute/send与服务版本 | first audible/stop/交付游标/每回合体验 |

先锁定API contract和最小能力版本，再写服务端契约/回归，消费者使用captured fake response验证退化路径；最后在用户批准的真实服务/设备上验收。服务升级不在请求路径发生。独立发布/回滚，两仓互不触发无授权代码写入或模型操作。

## 6. 源码依据

均固定SpeechRail `28755de8`，具体行为以上游当前代码和契约为准：

- [voice字段与参数能力](https://github.com/hrygo/SpeechRail/blob/28755de8cc51046f25ce75c7869fe1bacd34752d/src/speechrail/domain/tts.py)
- [voice发现/注册/内存幂等/质量run](https://github.com/hrygo/SpeechRail/blob/28755de8cc51046f25ce75c7869fe1bacd34752d/src/speechrail/http/routes/system.py)
- [HTTP TTS准入与StreamingResponse](https://github.com/hrygo/SpeechRail/blob/28755de8cc51046f25ce75c7869fe1bacd34752d/src/speechrail/http/routes/audio.py)
- [已有PCM验证与deadline](https://github.com/hrygo/SpeechRail/blob/28755de8cc51046f25ce75c7869fe1bacd34752d/src/speechrail/application/tts_delivery.py)
- [已有资源governor](https://github.com/hrygo/SpeechRail/blob/28755de8cc51046f25ce75c7869fe1bacd34752d/src/speechrail/runtime/resource_governor.py)
- [Base generate与decoded-waveform cache](https://github.com/hrygo/SpeechRail/blob/28755de8cc51046f25ce75c7869fe1bacd34752d/src/speechrail/backends/qwen3_tts_worker.py)
- [Realtime公共边界](https://github.com/hrygo/SpeechRail/blob/28755de8cc51046f25ce75c7869fe1bacd34752d/contracts/realtime-openai.md)
