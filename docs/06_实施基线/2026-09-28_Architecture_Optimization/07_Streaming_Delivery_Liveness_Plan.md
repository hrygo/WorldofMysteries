# 流式交付与提交后活性实施方案

> 文档类型：实施方案（已交付）
> 状态：已裁决并交付；实测证据与边界见 [`09_FLASH_选型与边界固化.md`](09_FLASH_选型与边界固化.md)
> 基线：`main` @ `2c006c6`（FLASH-02B 合入后）；交付完成于 `496bf9c`
> 前序：AO-01~AO-06 已合入；FLASH-01（传输层 SSE）、FLASH-02A/02B（超时层级）已合入
> 撰写日期：2026-09-29

---

## 0. 结论摘要

用户诉求「支持流式输出」在本仓库的正确落点**不是新建推送通道**，而是修复一个已确认的客户端活性缺陷：

> 提交后叙事与音频由**后台 worker 异步产出**，而客户端**只读一次**提交后交付视图。
> `pending` / `running` → `ready` 的状态转换**永远不会被客户端观察到**，用户必须手动刷新才能看到音频就绪。

契约、Python 服务端、Swift 客户端三层**均已存在且完整**，缺的只是客户端在契约规定的「该回来的时候再回来」。

本方案**放弃推送式数据面**，理由见 §4；工作量从「三角色 + `contracts/` 高风险面」降为「单角色 + 不动契约」。

---

## 1. 对上一版方案的复核修正

上一版建议「新增 `story.narrative_segment` 事件推送」。经三路只读调研复核，**该建议基于两处错误前提**，现予推翻。

| 上一版前提 | 复核结论 | 证据 |
| --- | --- | --- |
| 「乙」需要新建分段交付通道 | **早已存在**。`work.get` 已返回 `narrative_segments`，其 schema 直接 `$ref` 既有 `expression_segment` | `contracts/protocol/story_post_commit_control.schema.json` |
| 缺口是「数据通道」 | **缺口是客户端活性**。契约本就用 `running` 建模异步，客户端却零轮询 | `macos-app/WorldOfMysteries/StorySessionModel.swift` |

复核过程中另发现三项**上一版未识别的风险与事实**，均加强「不做推送」的结论：

1. **无写锁、无发送队列、无 event 发送入口**。每条连接仅一个 `_handle` task 顺序使用 writer；Python 侧完全不存在给控制连接用的 writer 暴露或广播路径（`engine/infrastructure/ipc_server.py:429`、`engine/infrastructure/ipc_framing.py`）。
2. **错误会被吞**。请求 handler 外层 `except Exception` 会把写入错误转成 `service_unavailable` 后**仍尝试发 response**；脱离 handler 生命周期的 event task 不受 `_tasks` 清理管理（`engine/infrastructure/ipc_server.py:461`）。
3. **客户端 event 容量硬上限**。最多跟踪 16 个 stream，`AsyncThrowingStream` 缓冲 128 条，**溢出即以 `capacityExceeded` 直接断连**（`macos-app/WorldOfMysteries/EngineSocketTransport.swift:43`、`EngineSocketTransport.swift:256`）。

---

## 2. 已确认的事实基础

### 2.1 提交后工作是后台异步的（方案前提）

- `work=None if durable_post_commit else delivery.after_commit` —— durable 路径下同步 `after_commit` 钩子被摘除（`engine/infrastructure/story_runtime.py:667`）。
- `PostCommitWorker` 在 runtime 启动时 `await ... .start()`（`engine/infrastructure/story_runtime.py:531`），内部为带 claim/lease 语义的后台循环（`engine/infrastructure/post_commit_worker.py:263`）。
- 叙事块是 COMMIT 之后**另行持久化**到 `world.db` 的 `narrative_blocks.payload_json`（`engine/infrastructure/migrations/004_world_narrative_blocks.sql`）。

**推论**：提交响应返回时，叙事与音频通常仍为 `pending` / `running`。这不是理论状态，是常态。

### 2.2 音频就绪更晚

`ScenarioAudioPrepareHandler` 只做 seal + `self._voice.publish(unit)` 交接（`engine/infrastructure/scenarios/post_commit_handlers.py:445`），**不等待渲染**；真正的 TTS 在 media 路径（`engine/infrastructure/audio/voice_runtime.py:234`）。因此 `audio_state` 到达 `ready` 的时点显著晚于提交响应。

### 2.3 客户端只读一次

- `refreshPostCommitWork`（`StorySessionModel.swift:459`）单次调用，整包替换 `postCommitWork`。
- 该文件**零 `Task.sleep` / `Timer` / 轮询**。
- 唯一再次刷新是用户手动触发（`macos-app/WorldOfMysteries/StorySessionPanel.swift:241`）。

### 2.4 已发布叙事永不修订（正确性保障）

- post-COMMIT SQL authorizer 只允许对 `narrative_blocks` **INSERT**，不允许 UPDATE/DELETE（`engine/infrastructure/database_manager.py:325`）。
- 重复写入要求 ID 与 payload 完全一致，否则报冲突（`engine/infrastructure/narrative_block_repository.py:97`）。

**推论**：分段交付在提交后是只追加、不修订的。客户端**不需要处理「已呈现内容被改写」**，这是流式方案中最难的一类对账问题在本架构下不存在。

### 2.5 `work.get` 是廉价纯读

模块契约明写：*never claims a job, never rewrites durable state, never seals audio and never calls a provider*（`engine/infrastructure/post_commit_control.py:1`）。实现只有 `read_world` 的 SELECT（`engine/infrastructure/post_commit_control.py:171`、`:262`）。

**推论**：有界轮询安全，不会打爆引擎。

---

## 3. 「流式」在本架构下的诚实上限

模型输出在 COMMIT 之前已完整取得（`engine/ai/authorized_live_execution.py` 先取完整 reply，再校验、再提交）。因此 **token 级流式送达 UI 在不变量 9（提交即命运）下不可能**——那等于把未提交文本显示给玩家。

在不变量 9 之内，可诚实交付的「流式」上限为：

1. **活性**：客户端真正观察到 `pending|running → ready`（修复真实缺陷）
2. **渐进呈现**：叙事按 segment 顺序出现，而非整包一次性出现
3. **音频早启动**：音频就绪即可播，与文本呈现重叠

本方案不把上述内容包装成 token 级流式。

---

## 4. 方案论证：为什么不做推送数据面

| 维度 | 推送 event 数据面 | 契约内 bounded re-read（本方案） |
| --- | --- | --- |
| 改动面 | `contracts/protocol/` 高风险面 + `ipc_server` writer 管线 + 三角色胶囊 | `macos-app/` 单角色，**不动契约** |
| 不变量 9 | 需自证「严格在 COMMIT 之后推」 | **结构性保证**：读的是已提交事实的投影 |
| 服务端并发 | 需引入写锁/发送队列/生命周期管理，且已有错误吞噬陷阱 | 复用既有纯读路径，零新增并发 |
| 背压 | 逐条 `await write_frame` 的 5s drain 超时会传播进 handler；客户端溢出即断连 | 无 |
| 丢帧 / 重连 | 需 sequence 缺口检测 + 对账 + 恢复补偿 | 无，幂等纯读天然自愈 |
| 崩溃恢复 | 推送流丢失，须回落拉取 | 本来就是拉取 |
| 用户收益 | 首次可见文本快约一个轮询间隔 | 同上 |
| 回归风险 | `test_story_runtime.py::_call()` 只读一帧即当 response，引入事件后**会先读到 event 而误判** | 无 |

**结论**：推送数据面以高风险面与并发正确性风险，换取一个轮询间隔的收益，不符合长期利益。

**保留项**：`event` 信封与 Swift 分发作为**已铺好但未启用的 seam** 保留。若将来确需消除轮询，可作为**唤醒信号**（只发「turn X 的叙事已就绪」，不带数据）单独引入，**与本方案解耦**，不作为本次交付内容。

---

## 5. 可执行方案

全部包按 HACF SOP 执行：`pack → start → 红测 → 提交 → verify → 凭据独立提交 → integrate → 回收`。
禁止 push / PR / 合并 / tag / 发布。**每个文件只设一个写入者。**

### FLASH-03A · CLIENT-LIVENESS（AGT-MAC）

**目标**：在契约规定的进行中状态下有界重读，使状态转换真正被观察。

**写入范围**：`macos-app/WorldOfMysteries/StorySessionModel.swift`

**行为**：
- 提交成功或恢复后，若 `settlement_state` / `narrative_state` / `audio_state` 任一为 `pending` 或 `running`，则以有界退避重读 `story.turn.work.get`
- 三者全部落到终态即**立即停止**，不得多打一次
- 达到重试上限即停止，并置可观测的失败态，**不得无限轮询**

**红测（先写，当前应失败）**：
1. `pending → ready` 转换必须被观察到
2. 三者均终态时立即停止，调用次数精确等于必要次数
3. 达到上限后停止并置失败态
4. `blocked` / `unavailable` 是终态，不得当作进行中继续轮询
5. 会话切换 / `generation` 变化时旧轮询必须取消（复用现有 `generation` + `queryAttempt` 守卫模式）

**约束**：不改任何契约；Swift 6 严格并发下 Task 生命周期与取消须显式处理。

### FLASH-03B · RECOVERY-RECONCILE（AGT-MAC）

**目标**：断线 / 重连后收敛到权威快照。

**写入范围**：`macos-app/WorldOfMysteries/StorySessionModel.swift`

**红测**：
1. 断线 → 重连 → 状态一次性收敛，不出现半截叙事
2. 恢复读取必须覆盖轮询中的中间态，不得回退到更旧的快照

### FLASH-03C · PROGRESSIVE-PRESENTATION（AGT-MAC）

**目标**：叙事按 segment 顺序渐进呈现；音频就绪即可启动。

**写入范围**：`macos-app/WorldOfMysteries/StorySessionPanel.swift`（呈现层）

**红测**：
1. 呈现顺序稳定，最终态与快照**逐段一致**（渐进只影响呈现，不得改变权威内容）
2. `speaker_display_name` 缺失时（`expression_segment` 对 `character` 为可选）有确定降级行为

**约束**：不得在 UI 层重新解析文本以推断说话人（契约已明示 App 无需 re-parse）。

### FLASH-03D · E2E-LIVENESS（AGT-QA）

**目标**：端到端证明修复有效。

**写入范围**：`engine/tests/test_voice_turn_e2e.py`

**断言**：一个真实回合中，`pending|running` 被观察到，并最终收敛到 `ready`。

**说明**：这是本方案唯一能证明「修复真实有效」的证据；缺它则前序包只是结构改动。

### FLASH-03E · MODEL-TIMEOUT-CLOSURE（AGT-ARB）

**目标**：把已验证的模型与超时口径固化为可复算产物。

**写入范围**：`docs/`（**不含任何凭据**）

**内容**：
- 记录选定模型 `opencode-go-qwen38-flash` 及其**实测**选型依据（N=10 矩阵）
- 记录「不得关闭思考」的实测结论（关思考 4~5/10，开思考 10/10）
- 记录该 provider **不执行 `minLength:1`** 的事实
- 同步本机 SSOT 的模型路由事实

---

## 6. 验收与门禁

| 包 | 门禁档案 | 关键验收 |
| --- | --- | --- |
| FLASH-03A/B/C | `MACOS_APP_P0` | Swift 6 全量测试 + Xcode 构建 |
| FLASH-03D | 需 opt-in 真实服务 | 真实回合 pending→ready 收敛 |
| FLASH-03E | 最轻档案（元数据） | 文档与实测一致 |

每包独立 Work Receipt + Integration Receipt。全量口径：`FULL_P0` 四阶段。

---

## 7. 证据边界（必须明示的未验证项）

1. **未实测** `pending` / `running` 的真实时长分布。**重试间隔与上限需先测再定，否则是在猜**——列为 FLASH-03A 的前置测量任务。
2. **轮询安全性**依据模块契约与代码审查（纯读、无 provider 调用），**未做压力实测**。
3. 事件通路（`event` 信封）**Python 侧零生产者**，本方案不启用，端到端未验证。
4. 曾有 **1 次真实语音 e2e 失败未归因**（Swift driver 非零退出，未取到 stderr）。**已归因并修复**，成因与修复见 §9.3 第 2、3 项；该次失败本身不再列为未解决项。
5. 三个调研子任务均为只读，**未运行测试**；其结论来自源码读取与全范围文本检索，不依赖图谱索引完整性（索引生成于 2026-09-19，早于当前工作区）。

### 顺带发现的文档偏差（**不在本次修复范围，仅报告**）

`AGENTS.md` 描述 IPC 为「UDS IPC **NDJSON**」，实际实现为 **4 字节大端长度前缀 + UTF-8 JSON 帧**（`engine/infrastructure/ipc_framing.py:1`）。文档与实现不一致，按「以实测判断当前状态」原则记录于此，**由文档所有者裁定是否修订**。

---

## 8. 风险与回退

| 风险 | 概率 | 影响 | 缓解 |
| --- | --- | --- | --- |
| 轮询间隔/上限设定不当 | 中 | 引擎空转或用户等待过久 | 前置实测时长分布；上限可配置 |
| Task 泄漏（会话切换后仍在轮询） | 中 | 幽灵请求 | 复用现有 `generation` 守卫；红测覆盖 |
| 渐进呈现与权威快照不一致 | 低 | 显示错误内容 | 红测强制最终态逐段一致 |
| 多 Task 写 `@Observable` 模型 | 低 | Swift 6 数据竞争 | 消费任务显式 `@MainActor` |

**回退**：每包独立提交与凭单，`integrate` 为本地 ff 合入；任一包验收失败即停止后续包，不影响已合入部分。

---

## 9. 裁决结果

1. **放弃推送数据面**，改做契约内活性修复。已裁决，已交付。
2. **实测前置**：已执行。轮询间隔 1.0s、上限 90s 取自实测（提交后交付就绪 11.3s–22.1s），不是估计值。
3. `AGENTS.md` NDJSON 表述偏差：**仍未修订**，由文档所有者裁定。本轮未触碰该文件。

### 9.1 实际交付包

| 包 | 状态 | 说明 |
| --- | --- | --- |
| FLASH-03A | 已交付 | `durablePostCommit` 默认开启 + 有界轮询 |
| FLASH-03B | 已交付 | 叙事按 segment 渐进呈现（表现层前缀揭示） |
| FLASH-03C | 已交付 | 音频就绪即播，与文本重叠 |
| FLASH-03D | 已交付 | 真实回合证明客户端观察到 `pending → running → ready` |
| FLASH-03E | 已交付 | 选型、超时与边界固化 |

### 9.2 §5 原始包划分与实际交付的差异（如实记录）

原方案的 03B「恢复对账」未单独成包：其行为已被 03A 的 `reloadSession()` 收敛路径与既有
`generation` 守卫覆盖，未产生独立可验收的行为差异，故未强行造包。

原 03D 归属 AGT-QA，实际由 AGT-MAC 承担：夹具的读写归属经 FLASH-03G 治理修订后
（App 跨进程夹具归 App owner），故由 AGT-MAC 在同一写范围内完成。

### 9.3 执行中新发现并已修复的三个缺陷

均非原方案预见，且都不是「测试写得不好」，而是真实缺陷：

1. **引擎只广播 v2 故事方法**，而真实回合夹具仍在断言并调用 v1 方法——该夹具在 durable 默认开启后已无法跑通。
2. **第二个 `AVAudioEngine` 会饿死运行中的采集 tap**。macOS 上它会重配共享音频设备，导致识别器收到纯静音（实测 0 采样）。改用 `AVAudioPlayer` 后，同一 tap 完整收到整句。
3. **App 侧提交日志是全机唯一固定路径**，第二次运行会继承上一次的冻结请求，`startStory()` 静默不生效，故事根本不会开启。`AppState` 现接受可选 `journalRoot`，每次运行隔离。

其中第 2、3 项正是先前那一次「未归因失败」的真实成因：夹具把终止原因丢成一句
`ASR produced no transcript`，且 stderr 未被取回。现已改为打印终止分支的实际取值。
