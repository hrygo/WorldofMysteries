# Persistent World Alpha 推进与验收计划 v1.0

> 决策日期：2026-09-18。用户已确认方向；**本文件不是实现完成记录**。
> 源码审查基准：`main @ c0c18ae31d76dac54b981e7855de87024f8d9e09`。
> 总验收：[Issue #43](https://github.com/hrygo/WorldofMysteries/issues/43)。
> 目标：用户完成一次经历，关闭再打开，人物与世界仍记得，且记忆能进入下一次已授权上下文。

## 1. 范围与事实源

沿用 [PRD](../00_产品/诡秘世界_PRD_产品基线_v1.0.md)、[可执行基线](Executable_Baseline_v1.0.md)、[技术纵向切片](../03_工程规范/Technical_Vertical_Slice_v1.0.md) 与 [Golden Runtime 规范](../07_工程启动/golden_001_runtime/README.md)。本计划只调整近期执行顺序，不取消任何产品不变量或发布门禁。

唯一首个场景为 [Golden 001《不存在的预约》](../../fixtures/golden_001/README.md)：固定人物、地点、五轮输入与事实断言。不得另造剧情替代回归基准。固定模型输出只用于工程验证，不代表真实模型文学能力已经验收。

推进状态仍由 [PROJECT_STATE.json](../PROJECT_STATE.json) 提供；工程任务仍在 [Engineering_Tasks_v1.0.yaml](../07_工程启动/Engineering_Tasks_v1.0.yaml)。不建立第二套任务执行器或新的门禁框架。

### 1.1 审查起点（不是 macOS 实测）

| 位置 | 基准中的事实 | 推进要求 |
|---|---|---|
| `macos-app/WorldOfMysteries/EngineIPCClient.swift` | 生产路径为骨架回显 | 真实进程/UDS 证据，不用状态字段自证连接 |
| `engine/application/session_orchestrator.py` | 只有协议接口 | 真实编排第一轮，然后扩展五轮 |
| `engine/infrastructure/database_manager.py` | 只有协议接口 | 持久事务、幂等、Outbox 与恢复 |
| `macos-app/WorldOfMysteries/ContentView.swift` | 建议提交仅切换动效 | 请求送达、错误恢复、提交结果绑定 |
| `.github/workflows/nightly-golden-audit.yml` | Golden 名称的步骤执行 `test_scaffolding.py` | 骨架检查与实际五轮证据分开；接入真实测试后才能宣告 Golden 通过 |
| 美术 #40 / #41 | 正式交付仍开放 | 保留批准来源；批准、精修、运行时 QA、正式入库分别验收 |

历史测试报告保留在状态文件的 `historical_gate_reports`；未提供当时绑定 SHA 的旧报告不补造 SHA，不投射为当前全绿。

## 2. 交付次序与依赖

| 阶段 | 可体验成果 | 退出条件 |
|---|---|---|
| A：真实一轮 | App → Engine → Advice → Resolver/Validate → Commit → UI | 真实 UDS、磁盘事务与提交结果可追溯；并非只有握手演示 |
| B：五轮与回来 | 五轮 → Episode → 关闭 → 重开 → Story Book / 人物记忆 | G001–G012、逐轮事实、结算、幂等、故障恢复和重建均有证据 |
| C：真实人物与声音 | 真实模型、自主决策、基础语音与降级 | 模型仅 Proposal；知识边界、语音失败、取消与回放不破坏事实 |
| D：独立体验 | 无开发者指导完成开始—经历—退出—返回 | 目标 Mac 体验记录、核心路径正式资产与既有发布门禁证据 |

执行依赖：`M1 + M2 + M3 + M5-PREP → M5（确定性 Golden Mock）→ M4（真实模型集成）→ M6（语音/独立体验）`。其中 `M3` 同时包含其依赖的跨角色 Application 集成，不把编排遗漏到真实模型阶段。

这里的 M1–M6 指 `PROJECT_STATE.json` 的导航里程碑；可执行基线中的 M0–M9 是原技术章节编号，两者不做机械同号对应。跨文档验收统一以能力、工作流 ID 与 Gate 名称定位。

**可并行的是准备与限定实现，不是宣告验收提前完成：**服务端、客户端、数据内核与 QA 断言可同时准备；角色权限、共享文件和资源租约仍按现有 HACF 约束。真实模型接口/版本准备也可并行，但不是确定性 Golden 的阻断依赖。

## 3. 首批已登记任务

| 任务 | 角色与范围 | 当前状态 / 依赖 | 验收关联 |
|---|---|---|---|
| [#44 M1-ENGINE-IPC](https://github.com/hrygo/WorldofMysteries/issues/44) | AGT-DATA：Engine infrastructure 与对应测试 | READY；服务端最小真实生命周期 | A / GATE-PROTOCOL |
| [#45 M1-APP-IPC](https://github.com/hrygo/WorldofMysteries/issues/45) | AGT-MAC：App 与客户端测试 | 准备 READY；联合验收依赖 #44 | A / GATE-PACKAGE |
| [#46 M2-DATA-KERNEL](https://github.com/hrygo/WorldofMysteries/issues/46) | AGT-DATA：事务/Outbox/恢复 | READY；与 #44 使用不重叠实现文件 | A–B / GATE-DATA |
| [#47 M5-GOLDEN-MOCK](https://github.com/hrygo/WorldofMysteries/issues/47) | AGT-QA：测试与夹具 | M5-PREP READY；完整验收等待真实实现 | B / GATE-GOLDEN-MOCK |

AGT-ARB承担协调，不越过默认角色边界直接改写 Domain、Engine infrastructure 或 App。后续 `M3` 的 Reducer/Validator 由 AGT-DOM、Application 编排与 Context Compiler 由 AGT-AI 分别切片；第一轮集成即需要它们，不等真实模型上线才补编排。真实模型、语音与完整体验任务在前置成果明确后细化，不预建空 PR。

Issue 中声明的角色不是已经启动的 Agent 进程；READY 不是 IN_PROGRESS。实际编码前重新核对基准并生成任务胶囊，不拿已有陈旧胶囊冒充新授权。涉及 contracts、迁移、锁文件、构建/签名、.github 或门禁档案时，先履行 AGT-ARB 审核与显式扩权。

## 4. 验收矩阵

以下全部为待执行验收；本规划 PR 不勾选产品通过状态。

| 验收项 | 所需证据 | 不接受的替代物 |
|---|---|---|
| 独立 Engine / IPC | 两进程真实 socket 往返、请求关联、超时、退出/重启 | 同进程函数回显、只设 `isConnected=true` |
| Advice 的实际影响 | 请求 → 人物意图 → 行动 → 合法 StateDelta → 已提交 revision | 只有动效，或另一段措辞 |
| 人物自主性 | 接受、部分接受或拒绝的可理解行动；无变化有原因 | 用户猜测变为世界事实、随机无解释拒绝 |
| 五轮事实 | 固定输入逐轮运行真实实现，并比较 expected committed state | 读取 expected JSON 后原样回传、永久 skip |
| 知识边界 | Secret 04 保持 hidden，公共观察不泄漏；授权先于语义召回 | 只检查提示词是否写了“不泄漏” |
| 原子结算 | Episode/Memory/Knowledge/Relationship/WorldEvent 同事务 | 单表成功、内存状态一致 |
| 幂等与故障 | 规范八个 kill Engine 检查点、重复请求、投影前崩溃恢复 | 重复执行产生额外 revision、重新抽签 |
| 关闭与重开 | World/人物/记忆/关系/Episode 一致，后续上下文读取历史 | 重启后按同一提示词重新生成 |
| Story Book / 语音 | 历史 NarrativeBlock/资产回放；TTS 失败文字降级 | 重播时重新裁决，失败回滚已提交事实 |
| 可重建投影 | 删除 retrieval.db 后重建等价，授权边界不变 | 从 retrieval.db 反向恢复不存在的权威事实 |
| 独立体验 | 目标 Mac 上记录开始、介入、完成、返回及困惑点 | 源码截图、仅在开发者机器执行成功 |

八个故障点使用 Golden Runtime 规范：`after advice`、`after action intent`、`after resolver before commit`、`immediately after commit`、`after beat plan`、`after narrative`、`during finalization transaction`、`after finalization commit before projection`。

基准目标是零知识越界、零重复提交、零部分结算、重启后权威状态一致。延迟、失败率、首用完成情况先测量并记录环境、样本和分布；本计划不编造现有指标或承诺未测性能。

## 5. 体验与美术的近期取舍

主要用户路径收敛为：世界/局势入口 → 当前人物 → Advice → 故事与结果 → Story Book → 再次进入。人物信息先服务当前局势，不为页面齐全扩展无 handler 的入口。演示与真实会话明确区分，组件画廊不承担主要用户路径。

保留语音作为主要体验方向。文本用于早期验证及语音失败降级，不将持久世界延期为“以后再补”；基础语音包含最终转写、取消、打断、重播与失败处理。

[#40](https://github.com/hrygo/WorldofMysteries/issues/40) 与 [#41](https://github.com/hrygo/WorldofMysteries/issues/41) 保持开放。已批准来源不重新构图；按既定 Master、衍生图、G3–G5、provenance、Asset Catalog 要求交付。先完成闭环必经界面资产，但不取消其余十五件 Artifact 的承诺，也不把图片全部齐套设为引擎开发的前置。

[#12](https://github.com/hrygo/WorldofMysteries/issues/12) 的正式 Artifact handlers 保留；它不是 Golden 001 的必需前置，不能以此扩展本次首个场景。完整二十二途径、多城市、多人物扩展、后台 NPC 模拟、复杂世界线与新治理框架不进入当前关键路径。

## 6. 交付与证据规则

- 区分设计完成、代码完成、集成完成、实际验证、用户可用；不以任一中间状态替代后续状态。
- 保留 `GATE-PACKAGE / GATE-PROTOCOL / GATE-DATA / GATE-AI / GATE-GOLDEN-MOCK`，以及现有受保护档案与 required checks。Mock 先运行不意味着取消 GATE-AI。
- 证据绑定源码 SHA、执行平台、命令、退出码与覆盖范围。Linux 检查不替代 macOS/Xcode/干净目标机验收；源码守卫不等于运行时测试。
- 当前 nightly 的骨架检查应继续保留。真实 Golden 测试就绪后由授权角色接入；不得只改步骤标题或放宽断言来取得通过。
- 单个任务按仓库要求生成胶囊，在有意义且已完成适用检查的增量后创建 Draft PR；同一任务在同一 PR 原子迭代，不直接写 main、不擅自 merge。
- 本次 PR 仅更新五份计划/状态文档及对应任务胶囊元数据。使用独立胶囊绑定当前任务，避免审计入口回退扫描历史胶囊；不伪造 Work/Integration Receipt，不改 .hacf、.github 或审计程序来绕过门禁。
- Issue #43 的产品验收清单不因本规划 PR 合并而关闭。首个可展示成果以真实“一轮提交”衡量，最终演示必须包含“关闭，再回来”。
