# Voice-First Runtime v2.0 — 验收矩阵与证据口径

日期：2026-09-19。状态：**拟执行验收规范，本文件不表示任何用例已运行**。关联[技术方案](../03_工程规范/voice/Voice_First_Technical_Design_v2.0.md)、[实施任务](Voice_First_Implementation_Plan_v2.0.md)。

## 1. 四层证据必须分别出具

| 层级 | 可以证明 | 不能代替 |
|---|---|---|
| A 确定性合成/Mock | 状态机、协议边界、取消、数据一致性、缓存键 | 真模型音质/延迟、真实设备 |
| B 固定真实 SpeechRail | 实际模型/参数/取消行为、采样格式、输出质量 | 扬声器已输出、端到端游戏提交 |
| C macOS 真机玩法 | AEC、设备变化、用户输入、播放、端到端时延 | 正式下载包信任、公证与跨机器适配 |
| D 发布制品 | 精确安装包、沙盒权限、签名、迁移/恢复 | 所有未来设备/输入的数学零故障 |

每个报告包含 code SHA、artifact/tree、协议版本、模型/variant/制品 revision、声音版本、平台/设备/路由、冷暖状态、负载、测试样本数、工具版本、原始指标摘要与已知不足。缺字段填 unknown，不补推断值。代码 CI 不等于声学批准。

SpeechRail 自动化/真实模型请求按其 AGENTS 授权执行；UI 自动化会占用界面，必须另有明确授权。此方案只提交文档与 Issue，没有运行它们。

## 2. 自动化回归矩阵（测试名称建议，待实现）

| ID | 操作/故障注入 | 必须断言 | 阶段 |
|---|---|---|---|
| V-IN-01 | partial 多次改写 | UI 更新，不发 PlayerAdvice | A |
| V-IN-02 | 一次输入发生 rollover，final 逆序到达 | 按 item 媒体次序组成一个 Final；等全部终态 | A/B |
| V-IN-03 | 重连重用 item 字符串、旧 connection 数据迟到 | epoch 隔离，不混入新轮次 | A |
| V-IN-04 | final ACK 丢失后重试同 input_turn | 幂等返回/状态查询，世界不二次提交 | A/C |
| V-IN-05 | “先不要…等等，改为…”及名字歧义 | 不提前行动，必要时显式确认 | B/C |
| V-IN-06 | ASR无confidence/无valid audio | unknown/失败，不伪造1.0 | A/B |
| V-IN-07 | 转录提示词含未公开真实身份 | 进入ASR前即拒绝/过滤 | A |
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
