# Voice-First Runtime v2.0 — 验收矩阵与证据口径

日期：2026-09-19；2026-09-28 按 SpeechRail 4.0（`3a1b02e0`）修订用例，并补录 B 层实机证据。状态：**验收规范**。
关联[技术方案](../03_工程规范/voice/Voice_First_Technical_Design_v2.0.md)、[实施任务](Voice_First_Implementation_Plan_v2.0.md)。

> **本轮出具 A、B、C 三层证据**。V-IN-11 ~ V-IN-20 及既有 A 层用例已有回归覆盖；
> **B 层（固定真实 SpeechRail）证据见 §1.1**，**C 层（macOS 真机）证据见 §1.2**。
> C 层发现并修复了**两个必然触发的缺陷**（采集崩溃、采集静默），
> 并在两条真实路由上完成验证；扬声器实际发声已由互相关证实。
> 未跑即未通过，不得补写推断值。

## 1. 四层证据必须分别出具

| 层级 | 可以证明 | 不能代替 |
|---|---|---|
| A 确定性合成/Mock | 状态机、协议边界、取消、数据一致性、缓存键 | 真模型音质/延迟、真实设备 |
| B 固定真实 SpeechRail | 实际模型/参数/取消行为、采样格式、输出质量 | 扬声器已输出、端到端游戏提交 |
| C macOS 真机玩法 | AEC、设备变化、用户输入、播放、端到端时延 | 正式下载包信任、公证与跨机器适配 |
| D 发布制品 | 精确安装包、沙盒权限、签名、迁移/恢复 | 所有未来设备/输入的数学零故障 |

每个报告包含 code SHA、artifact/tree、协议版本、模型/variant/制品 revision、声音版本、平台/设备/路由、冷暖状态、负载、测试样本数、工具版本、原始指标摘要与已知不足。缺字段填 unknown，不补推断值。代码 CI 不等于声学批准。

SpeechRail 自动化/真实模型请求按其 AGENTS 授权执行；UI 自动化会占用界面，必须另有明确授权。此方案只提交文档与 Issue，没有运行它们。

### 1.1 B 层实机证据（2026-09-28）

执行对象为**运行中的真实 SpeechRail 服务**，非 fixture、非 mock、非源码推断。

| 字段 | 取值 |
|---|---|
| code SHA | `2cab49f4eda1`（发布制品 `speechrail-3.3.1-cp314-cp314-macosx_27_0_arm64-2cab49f4eda1-py3147`） |
| 契约版本 | Realtime `4.0.0`；`effective_capabilities_v1` |
| 服务版本 | `3.3.1`（包版本与契约版本为两套独立编号） |
| 端点 | `http://127.0.0.1:8201/v1`，`ws://…/v1/realtime` |
| 模型 | ASR `asr-1.7b-q8`；TTS `tts-1.7b-custom-q8`（`custom_voice` variant） |
| profile | `quality/quality`；`asr_ready` / `tts_ready` / `diarization_ready` / `realtime_vad.ready` 均为 true |
| 冷暖状态 | `tts_warm=false`，`tts_state=active`（首请求触发升温） |
| 声音 | `aiden`（system voice，`voice_revision=null`） |
| 测试样本数 | 1 次完整 render；2 次裸 session 协商（1 正 1 负） |
| 平台 | macOS 26+ / arm64，本机 loopback |
| 工具版本 | Python 3.14.7，pytest 9.1.1，asyncio mode=auto |

实测结果：

| 检查 | 断言 | 结果 |
|---|---|---|
| 能力协商 | `/v1/speechrail/capabilities` 返回 `schema_version=effective_capabilities_v1`，`websocket_path=/v1/realtime` | ✅ |
| 握手 | `session.created → session.update → session.updated`，phase 达到 `ready` | ✅ |
| 正向 session | `audio/input/format.rate=24000` 被接受，回包同为 24000 | ✅ |
| **负向 session** | `rate=16000`（4.0 前的合法值）被真实服务拒绝，返回 `error` | ✅ |
| 渲染终态 | `status=completed`，`task_id` / `plan_id` 均单值 | ✅ |
| 音频完整性 | 22 chunk × 1920 帧 = 42240 帧 = 84480 字节（`pcm16`，2 字节/帧） | ✅ |
| 连续性 | `sample_offset` 从 0 起严格递增无空洞；`sum(frame_count) == total_frames` | ✅ |
| 采样率 | 渲染时长 1.760 s @ 24 kHz，receipt `pcm_sample_rate=24000`、`channels=1` | ✅ |
| **render receipt** | REST 回读 receipt：`receipt_id` 一致、`status=completed`、`sample_count` 与 `pcm_sha256` 与本地流式摘要逐字节相符 | ✅ |
| 证据边界 | `integrity_boundary=pcm16_after_transport_send` | ✅ |

**B 层能证明的**：真实服务确实说 `effective_capabilities_v1` / Realtime 4.0；24 kHz 单声道 `pcm16` 采样格式真实生效；16 kHz 真实被拒；三段式 `start → append_text → finish_text` 状态机与真实服务互通；`sample_offset` 无空洞；render receipt 的摘要与流式接收一致。

**B 层不能证明的**：扬声器已发声（receipt 边界止于 transport 之后）；端到端游戏提交；AEC 与真机时延。这些属 C 层，**本轮未执行**。

复跑方式（opt-in，默认 skip，不进任何门禁档案）：

```bash
cd engine
WOM_LIVE_BASE_URL=http://127.0.0.1:8201/v1 \
WOM_LIVE_API_KEY=<本机 SpeechRail 凭据> \
  uv run --extra dev pytest tests/test_speechrail_live_contract.py -v
```

未知项：`voice_revision` 为 `null`（system voice 未经用户发布路径），故带
`expected_voice_revision` 的分支与 pinned voice 的 upgrade/rollback 行为本轮**未覆盖**。

### 1.2 C 层实机证据（2026-09-28）

执行对象为**用户环境默认音频路由**，未指定、未切换任何设备（应用侧不选设备）。
首轮在蓝牙耳机路由上执行；为取得 C-04 所需的空间声学耦合，经用户授权后临时将系统默认
输出切至 MacBook 内置扬声器（输入本就是内置麦克风），测毕即恢复。

| 字段 | 取值 |
|---|---|
| 平台 | macOS 26+ / arm64 |
| 路由 A（首轮） | 蓝牙耳机（OpenFit Pro by Shokz），1 ch @ 16 kHz |
| 路由 B（C-04） | MacBook 内置：麦克风 1 ch @ 48 kHz，扬声器 2 ch @ 48 kHz |
| 麦克风权限 | 已授权（TCC authorized） |
| 工具版本 | Swift 6 / Xcode 27 SDK，swift-testing 2084 |
| 用例数 | 4 项（`macos-app/WorldOfMysteriesTests/VoiceDeviceAcceptanceTests.swift`） |

#### C-01 修复：真实麦克风必然触发的 SIGTRAP 崩溃（严重）

首次执行 C 层时，采集用例直接以 `SIGTRAP` 崩溃。崩溃栈：

```
_dispatch_assert_queue_fail
dispatch_assert_queue
_swift_task_checkIsolatedSwift
closure #1 in MicrophoneCaptureSession.start()
AVAudioNodeTap::TapMessage::RealtimeMessenger_Perform()
```

根因：`MicrophoneCaptureSession` 与 `VoiceProcessingAudioGraph` 均标注 `@MainActor`，
其 `installTap` 回调继承 MainActor 隔离。`AVAudioEngine` 把该回调派发到**音频实时线程**，
第一个音频缓冲区到达时触发 Swift 隔离断言并陷入 `SIGTRAP`。

影响：任何接有真实麦克风的用户，一有音频流进来即崩溃。
**A/B 层永远测不到**——CI 从不构造真实 `AVAudioEngine`，该回调永不执行；
`VoiceProcessingDuplexGraphTests` 的注释亦已写明“device-backed half 属于人工验收项”。

修复：把 `installTap` 的调用与闭包体一并移入 `nonisolated` 静态函数，
使闭包在非隔离上下文中创建，不再继承 MainActor。两条采集路径同步修复。
修复后同一用例通过，重复执行稳定。

#### C-02 硬件无关性：应用未挑选用户硬件（符合要求）

代码审计：**无**硬编码设备名，**无** `setPreferredSampleRate` /
`setPreferredInputDevice` / `setPreferredOutputDevice`，**无** 指定 `AudioDeviceCreateID`。
输入侧经 `AVAudioConverter` 由设备原生率重采样至 24 kHz；输出侧经 `mainMixerNode`
由 `AVAudioEngine` 自动转换至设备率。两条路径均与设备率无关。

实机验证：在 16 kHz 蓝牙路由上，采集产出的每一块 PCM 均为 24 kHz / 单声道，
24 kHz 线格式亦被 16 kHz 输出设备正常接受。**用户不需要更换硬件。**

#### C-03 全双工能力随路由而变（两条路由均已覆盖）

| 路由 | 结果 |
|---|---|
| 蓝牙耳机（16 kHz） | `duplex=half_duplex_ptt reason=deviceUnavailable`（两次一致） |
| MacBook 内置（48 kHz） | `duplex=full` |

蓝牙耳机可保持语音处理输入打开，却无法在其上叠加播放；内置麦克风+扬声器则可以。
**这说明半双工是设备属性而非应用缺陷**，与“必须都支持”的要求一致：
正确行为是落到 `VoiceProcessingDuplexProvision.halfDuplexPTT` 而非让本轮失败
（该枚举已存在，本次未改动）。

#### C-04 扬声器实际发声：已验证（路由 B，合成语音互相关）

路由 A 上“播放中 vs 静音的 RMS 差值”不可用：差值在 `-72 dB` ~ `+10 dB` 间跳动，
一次静音基线采到满刻度环境声，多次采到 `6.103515625e-05`（Int16 的 2 个 LSB 量化底噪）。
原因有二：蓝牙耳机麦克风在腔体内而非房间中；AEC 的设计目的正是消除该自回声。

改在路由 B（内置麦 + 内置扬声器，同机身，耦合最强）以 **SpeechRail 合成的真实语音**
（1.520 s，24 kHz 单声道）做归一化互相关，两侧各录一次：

| 指标 | AEC 关 | AEC 开 |
|---|---|---|
| 峰值互相关 \|r\| | **0.4881** | 0.0760 |
| 录音峰值 | −36.92 dBFS | −55.48 dBFS |
| 测得时延 | 458.35 ms | — |
| AEC 衰减 | — | **18.56 dB**（互相关降 16.16 dB） |

`\|r\| = 0.49` 且时延落在数百毫秒量级，与房间声学传播加系统延迟一致：
**播放的语音确实离开扬声器并被麦克风录到**——这正是 B 层明确声明无法证明的那一项。
开启 AEC 后相关性降至 0.076、峰值降 18.56 dB，说明 AEC 确实在抑制该自回声。

用例内仍只报告不断言：路由 A 的耦合强度与 A 层不具可比性，固定阈值会在应用
**必须支持**的硬件上失败。已内置 `at_quantisation_floor` 与 `emission_detected` 标记供复跑判读。

#### C-05 修复：开启语音处理后采集静默输出数字静音（严重）

在路由 B 上首次测得 `quiet_peak = 0.0`。插桩定位：

```
inFmt=48000.0 inCh=9 inFrames=4800 inPeak=0.0058 outFrames=2432 outPeak=0.0 nonzero=0
```

输入缓冲区 `inCh=9` 且 `inPeak=0.0058`（有声），但输出全零。
开启 VoiceProcessingIO 后，输入节点**报告**单声道，而 tap 实际收到的是
**9 通道原始布局**（麦克风 + AEC 参考通道）。原实现按报告格式（单声道）预建
`AVAudioConverter`，喂入 9 通道缓冲区后**静默返回全零帧，不报错**；
且设备切换围栏只比对采样率、不比对通道数，于是放行。

后果：全双工路径下每一轮都录到静音麦克风，却向用户报告成功。
**Mock 永远测不到**——Mock 交出的是格式规整的单声道缓冲区。

修复：
1. tap 显式抽取通道 0（麦克风）构造单声道源，不依赖转换器的多声道映射
   （该映射对 VoiceProcessingIO 布局同样返回静音）；
2. 转换器改为按**实际交付格式**惰性建立，格式变化即重建；
3. 围栏比对完整格式而非仅采样率。

修复后 `nonzero=18307`，真实音频流过全双工采集路径。
`VoiceDeviceAcceptanceTests` 已加入 `nonzero > 0` 断言并附回归说明：
形状正确但全零的缓冲区曾能通过全部既有断言。

#### C 层小结

| 项 | 结论 |
|---|---|
| 真实麦克风崩溃 | **已定位并修复**（SIGTRAP，必然触发） |
| 采集静默输出数字静音 | **已定位并修复**（9 通道布局，全双工路径必然触发） |
| 设备无关（不挑硬件） | ✅ 代码审计 + 两条路由实机验证 |
| 采集重采样至 24 kHz | ✅ 实机（16 kHz 与 48 kHz 两条路由） |
| 24 kHz 线格式播放 | ✅ 实机 |
| 语音处理启用 | ✅ 实机 |
| 全双工 | 路由相关：内置 ✅ / 蓝牙落半双工 PTT（受支持模式） |
| 扬声器实际发声 | ✅ **已验证**（互相关 \|r\|=0.4881，AEC 衰减 18.56 dB） |

复跑方式（opt-in，默认 skip，不进任何门禁档案）：

```bash
cd macos-app
WOM_DEVICE_ACCEPTANCE=1 swift test --no-parallel --filter VoiceDeviceAcceptance
```

**必须串行执行**：连续开关语音处理 I/O 会让蓝牙路由短暂不可用；
这不是 App 缺陷（真实会话不会这样开关），但测试序列需要 `makeGraph` 的有界重试与 settle。

## 2. 自动化回归矩阵（测试名称建议，待实现）

| ID | 操作/故障注入 | 必须断言 | 阶段 |
|---|---|---|---|
| V-IN-01 | partial 多次改写 | UI 更新，不发 PlayerAdvice | A |
| V-IN-02 | 一次输入发生多个 rollover；异步处理导致final乱序 | 按**首见序**收集，等 `commit → 相同 session.update → session.updated` 栅栏及全部成功终态；不是网络WS乱序承诺 | A/B |
| V-IN-03 | 重连重用 item 字符串、旧 connection 数据迟到 | epoch 隔离，不混入新轮次 | A |
| V-IN-04 | final ACK 丢失后重试同 input_turn | 幂等返回/状态查询，世界不二次提交 | A/C |
| V-IN-05 | “先不要…等等，改为…”及名字歧义 | 不提前行动，必要时显式确认 | B/C |
| V-IN-06 | ASR无confidence/无valid audio | unknown/失败，不伪造1.0 | A/B |
| V-IN-07 | 转录提示词含未公开真实身份 | 进入ASR前即拒绝/过滤 | A |
| V-IN-08 | previous_item_id为空；最后commit产生空item | 已有片段保留；空尾段允许，不按文本去重；同item内容冲突的第二个final整轮失败 | A/B |
| V-IN-09 | append/commit失败或item缺失后仍收到barrier `session.updated` | 整轮失败/不完整，不发布部分Final，不推进世界；**不存在超时返回部分文字的成功路径** | A/B |
| V-IN-10 | 关闭栅栏未返回前用户开始下一轮 | 新采样不混入旧连接；采用显式策略，不隐式双提交 | A/C |
| V-IN-11 | 服务只下发 delta/completed/failed，无 committed/cleared/item.created | 仍能按首见序收口；不依赖已下线事件 | A |
| V-IN-12 | 收到 `speechrail.transcription.hypothesis`（含旧revision） | 只作可撤销草稿；正文只取 completed | A |
| V-IN-13 | barrier `session.updated` 的有效配置与请求漂移 | 整轮失败；不得采信该 barrier | A |
| V-IN-14 | envelope `content_index` 非 0 | 拒绝该 envelope，不当作主内容 | A |
| V-IN-15 | 首个 server sequence 为 0 或 1，其后连续 | 接受；非0/1首值或任意 gap 均拒绝 | A |
| V-IN-16 | 未配置 api key | 不发送 `Authorization`，不发送空 Bearer | A |
| V-IN-17 | 升级前被拒（HTTP 401/403，无 close code） | 结构化失败；不伪造 invalid-key 结论 | A |
| V-IN-18 | 取消/错误/超时/成功四种终态 | 全部关闭连接；下一轮必须重连并取得新 epoch | A |
| V-IN-19 | render receipt 缺失/401/404/摘要不符 | 整轮失败并清理临时音频，绝不升格为完整 take | A/B |
| V-IN-20 | 麦克风/PTT/duplex/ASR wire 采样率 | 全部为 24 kHz；非 24 kHz 的 chunk 在 PTT 边界被拒 | A |
| V-CTL-06 | 仅MediaStop/Pause，pending世界工作尚在进行 | 不调用Domain cancel_pending；显式取消是另一用例 | A/C |
| V-CTL-01 | pending turn取消与Writer COMMIT同时发生 | 唯一线性化结果，commit胜出则仅停播放 | A/C |
| V-CTL-02 | 网络cancel阻塞、服务忙 | 本机stop不等待网络或LLM | A/C |
| V-CTL-03 | stop后收到旧generation音频 | 全部丢弃，不重新排队 | A/C |
| V-CTL-04 | “嗯”、咳嗽误打断 | 可恢复；不会无条件产生Advice | B/C |
| V-CTL-05 | 截断动作ACK丢失 | 不盲目重跑事实，查询原turn | A |
| V-MED-01 | 奇数字节chunk、格式中途改变、重复/跳号 | adapter明确拒绝，关闭对应流，不误发布 | A/B |
| V-MED-02 | HEAD/首块前/句中断线、正常FIN但无语义END | provisional失效；可回放完整先前单元 | A/B |
| V-MED-03 | EOF/取消时尾字与drain竞态 | 正常EOF保留尾部，取消不输出迟到尾部 | A/B/C |
| V-MED-04 | UDS假peer、重放ticket、长度溢出、credit耗尽 | fail closed，控制路不被堵塞 | A/C |
| V-MED-05 | 旧SDK只支持v1严格JSON | 不发新字段；明确协商/降级 | A |
| V-ID-01 | 两请求同时首次为同一NPC选角 | CAS唯一绑定，第二者复用获胜者 | A |
| V-ID-02 | 首次声音已输出但回执/应用丢失 | 持久reservation保持原声音 | A/C |
| V-ID-03 | 同voice_id被改instruction/seed/reference | 精确revision不悄悄改变；旧资产不误命中 | A/B |
| V-ID-04 | 角色升格、世界线分叉、时点变化 | 继承当时绑定；新修订不覆盖历史轨 | A/C |
| V-ID-05 | 冻结绑定后模型/registry恢复变化 | capability刷新；无法确认版本则显式降级 | A/B |
| V-SEC-01 | 只改变幕后事实的成对场景 | 公开声音选择/称呼/SFX元信息无差异 | A |
| V-SEC-02 | 面具NPC恰为已熟悉人物 | 未授权时不用熟悉身份声线暴露秘密 | A/C |
| V-SEC-03 | cache已存在后撤权/voice revoke | 访问先于命中，拒绝新消费 | A/B |
| V-SEC-04 | local-only且本地服务故障 | 不产生云请求、不上传音频 | A/C |
| V-PERF-01 | Base voice要求instructions/speed变化 | 出站不发送不支持参数，有effective降级记录 | A/B |
| V-PERF-02 | 读音替换涉及数字/单位/否定 | SpokenText↔DisplayText语义保全 | A/B |
| V-PERF-03 | 高位声场/耳语/过多层叠 | 保留清晰主声；有低刺激模式 | C |
| V-CACHE-01 | 相同文字但不同模型/声音revision/读音版本 | RenderKey不同；实际文件SHA独立 | A |
| V-CACHE-02 | 相同render有两个订阅，一个取消 | 另一订阅不受影响；旧generation不播 | A |
| V-CACHE-03 | 临时文件写完、manifest提交前崩溃 | 可回收孤儿，没有假完整take | A/C |
| V-CACHE-04 | StoryBook pin后LRU/空间紧张 | 不自动删被引用历史；不足明确提示 | A/C |
| V-CACHE-05 | 未选分支/未commit结果进入prefetch | 在合成前拒绝，更不得播放 | A |
| V-QOS-01 | 质检/设计/长ASR与实时会话竞争 | 按策略延期/有界等待，不无限饿死后台 | A/B |
| V-QOS-02 | 优先级不受支持或总量超限 | 受控拒绝/降级，不暗增worker | A/B |
| V-QOS-03 | 声音条件缓存命中但worker重启/模型变更 | 缓存失效；mutable decoder无跨请求泄漏 | A/B |
| V-DEV-01 | 外放对白+雨声+用户“等等” | AEC不自触发，真打断及时 | C |
| V-DEV-02 | USB/蓝牙插拔、采样率/通道变化 | 原音频图恢复，旧stream不混播 | C |
| V-DEV-03 | callback执行预算与内存争用 | 无网络/文件/阻塞；统计underrun与队列界限 | A/C |
| V-REPLAY-01 | 断网重播完整合法历史轨 | 零模型调用；音轨不重新编写 | B/C |
| V-REPLAY-02 | 后期重配音/授权撤销/清理 | 新轨独立，旧事实不改，使用政策明确 | A/C |
| V-STORY-01 | 多轮真实Domain、暂停、重启、Closure | 世界历史连续、无重复Commit、知识未越界 | A/C |
| V-PKG-01 | 精确最终ZIP在真机启动与权限拒绝 | 无降低Library Validation；降级可解释 | D |

每个实现 PR 声明覆盖哪些测试 ID；未实现或平台不可达必须保留空缺，不填pass。新门禁命令仅放入受保护 gate profile。VOICE_P0 原有test_audio_adapter集合不足以覆盖本矩阵。

## 3. 性能统计口径

所有时间以各自进程单调时钟测区间；跨进程关联使用request/unit/epoch，不能直接相减未校准的monotonic时间戳。端到端由同一客户端时钟或已校准回环测量。

事件：`input.speech_start`、`input.last_speech_sample`、`input.endpoint_decided`、`asr.final`、`domain.committed`、`narrative.sealed`、`tts.request`、`tts.first_pcm`、`playback.first_non_silent_output`、`playback.stop_requested`、`playback.stopped`。unknown事件不填零；stage p95不直接相加得到端到端p95。

| 指标 | 初始候选目标 | 注意 |
|---|---|---|
| 点击停止到内置输出停止 | p95 ≤150ms | 蓝牙单列；停止回调不代替实际声学尾音 |
| 发声到聆听视觉反馈 | p95 ≤100ms | 不等待ASR文字 |
| first stable partial | 初期p95 ≤1.5s | unstable预测不计作稳定partial |
| warm sealed首句到可闻语音 | p50 ≤500ms / p95 ≤1s | 报首PCM与非静音分别指标 |
| 完整本地take命中到开声 | p95 ≤150ms | 包含读取与解码；声学实测与估计分开 |
| 用户结束发言到有内容世界回应 | 初期p50 ≤2.5s / p95 ≤5s | 提示音/“正在思考”不计有效回应 |

这些数值来自产品目标，**不是SpeechRail承诺或本次实测**。若当前模型无法达到，记录真实分布并按瓶颈决定优化，不删测试或换统计起点。

样本报告分层：cold/warm、idle/有本地LLM负载、内置/USB/蓝牙、短/长句、Base/CustomVoice/VoiceDesign。每组报告n、失败/取消数量、p50/p95、最大值和缺测占比。RTF=推理时长/生成音频时长，不混用首块延迟。瞬时cache hit ratio不能代替每个成功turn总费用与等待时间。

## 4. 声学与身份质量

建议起始矩阵：12个候选声音×6类中文文本×3次重复；这是计划规模，未执行。类别为短句、长句、疑问/否定、数字单位、授权人名术语、允许的低声/停顿。主要角色附加跨场景、worker restart和不同文本长度。所有参照材料须有许可，公共仓库只保存无敏感文本fixture/指标，不放真实录音。

分别给出参考信号质量、合成文本可懂度、跨文本身份、自然度与表现力、响度/峰值、重复性六项结论。ASR回转录只能提供可懂度证据；speaker encoder仅辅助，并在独立真实数据上校准；固定seed/PCM相等不等于自然或像同一人，不相等也不必然是不合格声音。

人工听测须匹配文本和响度，随机盲序。同场对话测试能否只靠声音区分主要角色；重要词错读、否定丢失、尾字截断为专门用例，不被平均CER掩盖。现有SpeechRail #34继续负责响度算法与声学验收，避免另设相互矛盾门槛。

## 5. 证据保存、隐私与放行

运行日志只含低基数错误类别、阶段计数、时长和脱敏关联ID；不记录凭据、原音频、完整文本、参考embedding或用户路径。原始语音/诊断导出由用户显式选择并单独保管。音频hash与actor关联也视为隐私元数据，不放Prometheus labels。

放行层级：`software_verified` → `service_verified` → `device_accepted` → `release_accepted`。任何缺少独立身份或人工听测的候选只能是`unevaluated`/受限使用，不能仅因为注册201自动PUBLISHED。严重权限、事实回滚、假完整缓存、stop后旧声回流为阻断项。

回滚关闭对应feature flag并停止新流；保留已提交世界与合法历史音轨。保护分支、原始凭单、真实Code/Model/Voice版本共同形成可追溯证据，不生成假签名或伪造自引用测试报告。
