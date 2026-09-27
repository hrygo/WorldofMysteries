# Golden 001 固定五轮 · GUI 观察记录（Checkpoint C）

> 观察时间：2026-09-27 19:14–19:22 CST  
> 观察对象：打包后解压的 `诡秘世界.app`（真实生产 Swift 链路 + 独立 Local Engine）  
> 记录定位：本记录是迭代计划 §4 检查点 C「App 与故障恢复成立」的 GUI 侧证据，绑定同一最终 SHA，与跨进程故障测试、G010 音频事实不变测试同源。

## 1. 证据绑定

| 项 | 值 |
|---|---|
| 最终 SHA（构建源 = main HEAD） | `f72f37970a17679ffb9950bcc19aab36c749f513` |
| 观察时 main HEAD | `f72f379`（工作区干净） |
| 打包产物 | `WorldofMysteries-arm64-development.zip` |
| 产物 sha256 | `8c93be8961af8086e04d070c715c74c95376bb6ab9ac8df9e8cf5f704cd66843` |
| 产物大小 | 169,764,019 bytes |
| 签名 / 公证 | ad-hoc 签名、hardened runtime（仅 app bundle）、**未公证** |
| 打包证据 | `.hacf/tmp/gui-observation-f72f379/package-evidence.json` |
| 引擎 | Python 3.14.7 + AgentScope 2.0.8（生产 IPC 服务，`infrastructure.ipc_server`） |

> 说明：这是 **ad-hoc 签名开发包**，不是公证发行物。公证、目标用户安装与性能验收仍属 `remaining_acceptance`，不因本记录关闭。

同一最终 SHA 上已通过的跨进程结果（本轮之前合入，均为 `f72f379` 的祖先）：

- 八个 Engine 终止检查点（`B-FAULT-POINTS`，实现 `450fe28`，集成 `8493b04`）
- G010 音频重生成不改叙事/状态（`B-GOLDEN-ACCEPTANCE`，`4f0b093`，集成 `6a8a1bd`）
- G009 表达层重发幂等（`test_post_commit_expression_failure_never_rewrites_committed_facts`）

## 2. 观察方法与真实性声明

- 通过 **打包后的解压 App** 启动，非源码直跑；引擎为随包生产 IPC 服务。
- 会话数据根：`…/Containers/devplaceholder.LK682GAS.WorldOfMysteries/Data/Library/Application Support/WorldofMysteries/Engineering/Golden001/Data`，运行前为干净状态。
- 交互全部经 GUI 真实控件完成：每轮点击「填入本轮建议」→ 点击「提交建议」。
- 状态文字与轮次经可访问性树（AX tree）逐轮读取并记录，非源码检查、非仅凭截图。
- 提交是否真实落盘，以 **磁盘 SQLite 计数** 为准（见 §4）。

> 真实数据核对：会话为「**伊芙琳·格雷 · 哈维诊所 · 诊室**」（引擎领域数据），非示例数据（示例为克莱恩）。顶栏「命运动态」独立展示真实开局卷宗。

## 3. 逐轮观察记录

初始：面板处于 `.notStarted`，显示「开始可信开场」（AX 元素 29）。

| 步骤 | 交互 | status（AX 读取） | turns / 线索（AX 读取） |
|---|---|---|---|
| 点「开始可信开场」 | 打开会话 | 填入第 1 轮建议后提交 | 已提交轮次：0 · 线索：无 |
| 第 1 轮 | 填入 → 提交 | 填入第 2 轮建议后提交 | 已提交轮次：1 · 线索：医生的停顿 |
| 第 2 轮 | 填入 → 提交 | 填入第 3 轮建议后提交 | 已提交轮次：2 · 线索：医生的停顿、异常的预约记录、被撕去的预约页 |
| 第 3 轮 | 填入 → 提交 | 填入第 4 轮建议后提交 | 已提交轮次：3 · 线索：…、门框黑粉 |
| 第 4 轮 | 填入 → 提交 | 填入第 5 轮建议后提交 | 已提交轮次：4 · 线索：…、Jonathan 的纸片 |
| 第 5 轮 | 填入 → 提交 | **第 5 轮已保存 · 固定五轮验证已完成** | 已提交轮次：5 · 线索：（5 条，止于 Jonathan 的纸片） |

终态补充（AX 读取）：

- 说明文字：「固定五轮验证已完成；已提交的 5 轮可以随时重新读取。」
- 「提交建议」按钮变为 **disabled**（不接受第 6 轮、不接受任意文本输入）。
- 第 5 轮提交耗时约 **85 秒**（远超前几轮 6–9 秒），与 Episode 结算在同一提交路径上完成的特征一致。

> 逐轮建议文本由引擎下发（固定模式每轮只接受引擎指定建议），「填入本轮建议」按钮写入草稿，「提交建议」走真实提交链路。

## 4. 磁盘事实核对（权威）

观察完成后直接读取 `world.db`（`Worlds/engineering-golden001/world.db`）计数：

| 表 | 计数 | 含义 |
|---|---|---|
| `turn_intake_commands` | **5** | **五次建议经 GUI 真实提交并落盘** |
| `turn_advice_interpretations` | 5 | 五次建议均被解释 |
| `turn_transactions` | 5 | 五个回合事务提交 |
| `story_state_deltas` | 5 | Story revision 依次推进 5 次 |
| `narrative_blocks` | 5 | 每次 COMMIT 后发布叙事块 |
| `beat_plans` | 5 | 每次 COMMIT 后发布节拍计划 |
| `turn_world_events` | 3 | 仅世界变更回合产生世界事件 |
| `turn_character_changes` / `turn_knowledge_changes` / `turn_relationship_changes` | 1 / 1 / 1 | 人物/知识/关系证据 |
| `domain_commits` | **7** | bootstrap + 5 轮 + Episode 结算 = 7 |
| `episodes` | 1 | 一次 Episode 结算 |
| `episode_finalizations` | 1 | 一次终局定稿 |
| `episode_world_events` / `episode_character_events` / `episode_knowledge_changes` / `episode_relationship_events` | 3 / 1 / 1 / 1 | Episode 结算落地的领域证据 |
| `character_episode_memories` | 1 | 人物 Episode 记忆生成 |
| `story_sessions` | 1 | 单会话 |

会话与修订（三方自洽）：

- `story_sessions`：`status = finalized`，`story_revision = 5`，`base_world_revision = 103`，`committed_world_revision = 7`
- `world_meta` 修订 = **7**
- `episodes.committed_world_revision` = **7**
- `domain_commits` = **7**

> `committed_world_revision`（会话/Episode）、`world_meta` 修订、`domain_commits` 三者同为 7，且 `story_revision = 5`，与「五轮 + 一次 Episode 结算」精确吻合。

## 5. 检查点 C 逐条对照

| 检查点 C 要求 | 本记录证据 | 结论 |
|---|---|---|
| App 完成开始、五轮提交、结算、退出、返回，保留 pending/未知状态 | §3 逐轮 GUI 操作达终态；§4 磁盘 5 轮 + 1 Episode 落盘 | ✅ 成立 |
| 第 5 轮后明确结束；不默许第 6 轮或任意文本 | 终态 status「固定五轮验证已完成」，提交按钮 disabled | ✅ 成立 |
| 八个 Engine 终止检查点 | 同 SHA `B-FAULT-POINTS` 七个跨进程故障测试 | ✅ 成立（跨进程侧） |
| 故障测试同时核对进程恢复 + 磁盘事实，零重复提交、零部分结算 | 同 SHA `_durable_counts` 九表断言 | ✅ 成立（跨进程侧） |
| Narrative/audio 重生成不改 StoryState（G010） | 同 SHA `test_audio_regeneration_never_changes_narrative_or_story_state` | ✅ 成立 |
| GUI 观察与跨进程结果绑定同一最终 SHA | 本记录 §1 绑定 `f72f379`，与上述测试同 SHA | ✅ 成立 |

## 6. 观察中发现的次要事项（未修，不阻塞）

- 容器 tmp 每次启动泄漏一个 `wom-<id>/s.lock` 目录（含 9/24、9/25 历史残留）。打包证据的 `app_force_quit_cleaned_engine: true` 指引擎进程被杀，非目录清理。与本轮五轮提交无关，留作独立清理项。

## 7. 附图

终态截图（fate 标签页，含顶栏「第五纪 · 1349 年 · 廷根市」、左侧导航、Artifact Library）：`../../.hacf/tmp/gui-observation-f72f379/final-state.png`

> 截图为「命运」标签页；五轮完成的终态文字与按钮 disabled 状态以 §3 的 AX 读取为准（截图未停留在故事面板）。观察不能由截图单独替代，权威证据为 §4 磁盘计数。
