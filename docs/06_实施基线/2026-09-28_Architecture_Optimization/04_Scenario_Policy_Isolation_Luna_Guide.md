# AO-04 场景规则与 Golden 隔离 — Luna 实施方案

> 日期：2026-09-28；原始源码基准：`ca68d485a15bacf46ade5e703abde00598ec5251`。
> 状态：待实施；无硬依赖，建议 AO-03 后实施以避免同时修改 runtime/facade/settlement。
> 本文新增接口和测试场景均为拟新增；不开放生产第二场景，不迁移用户存档。验证未执行。

# 1. 问题结论

交付可替换的场景规则与 Worker 选择边界，使固定五轮成为一个场景实现，而不再定义通用会话服务的最大轮数、建议模板和结算条件。

验收使用一个不同结束条件的测试场景证明接口独立性。不要借此开发内容编辑器、Genesis、无限回合或任意用户场景加载。

# 2. 当前实现与根因

| 现有路径 / 符号 | 当前耦合 | 保留/修改 |
|---|---|---|
| `engine/ai/golden_five_turn.py`：`GoldenFiveTurnFactory` | 同时提供规则、固定输入、模型替身和表达模板 | 保留 Golden 内容及 oracle 独立性，拆出规则 adapter |
| `engine/ai/live_turn_workers.py`：`LiveFirstTurnFactory` | 必须持有 Golden 工厂，委托 max_turn/policy/domain_validation | 改为依赖场景端口 |
| `engine/application/story_session_facade.py`：`StoryFirstTurnPort` / `_validate_new` | 一个 factory 同时承担业务规则与模型创建 | 注入 scenario 和 workers 两个端口 |
| `engine/infrastructure/episode_settlement.py`：`FINAL_TURN=5` | 通用装配直接依赖第五轮 | Golden adapter 提供结束判定 |
| `engine/application/story_public_view.py`：`StoryPublicViewProjector` | 接收 max_turn 控制 can_submit | 接收服务端计算的继续/结束决定 |
| `engine/application/story_initialization.py`：`TrustedScenarioBundle` / `StorySessionBootstrap` | 冻结可信内容与初始化身份 | 保留，避免换新版内容重解释旧会话 |
| `contracts/protocol/story_session_control.schema.json` | scenario_id 与 mode 固定枚举/常量 | 本包保留，生产入口仍仅 Golden |

根因不在文件名含 FirstTurn，而在“规则与模型执行被一个 factory 混合提供”。只改类名不算完成。

# 3. 目标行为

- 通用 facade、live Worker 和任务执行器均不 import Golden 实现。
- Golden 仍严格五轮、接受原固定模板、保留原数值裁决与终局证据。
- 结束条件由场景明确裁决，不由模型决定，不用 `turn >= 5` 散落判断。
- 测试场景可在满足特定已提交线索条件后结束，并设最大安全轮次；不改通用编排即可通过。
- 场景身份与规则版本由可信内容绑定，IPC 不接受任意 Python 类、磁盘路径、规则代码或客户端指定终局。

# 4. 推荐解决方案

拟新增 `engine/application/scenario_policy.py`，最小端口：

```text
ScenarioIdentity(scenario_id, content_digest, rules_revision)
TurnPolicyDecision(allowed_to_submit, terminal, reason)

ScenarioPolicyPort:
  identity(bootstrap) -> ScenarioIdentity
  decision(session, committed_evidence) -> TurnPolicyDecision
  expected_input(bootstrap, session) -> str | None
  resolution_policy(bootstrap, session) -> ResolutionPolicy
  validation_context(bootstrap, session) -> DomainValidationContext
  finalization_recipe(bootstrap, committed_session) -> recipe | None

TurnWorkerFactory:
  interpreter_for(bootstrap, turn_number)
  proposer_for(bootstrap, turn_number, allowed_signatures)
  narrative_compiler(bootstrap)
```

端口属于 Application，规则使用纯 Domain 类型；实现只允许读取可信数据。生产 `GoldenScenarioPolicy` 拟放 `engine/infrastructure/scenarios/golden_policy.py`，负责把已有 Golden 规则/模板适配到接口，允许该适配层依赖旧工厂以最小迁移，通用代码不依赖它。

本包不移动全部规则数据或重写内容包。先消除业务主路径的具体类依赖；Golden factory 的固定 worker 与场景 adapter 可共享其现有内部规则构造，不能复制第二套数值规则。

持久版本绑定优先使用已有 bootstrap 的内容摘要/版本字段：在可信注册表中将已知旧摘要映射到固定 `rules_revision`；新内容包显式声明规则版本。若 bootstrap 当前模型无容纳字段，在已有持久 payload 内增加带版本的可选 metadata 并同步内部内容校验，不新增世界表。历史缺字段只允许匹配已知 Golden 摘要，不回退“最新版”。

# 5. 详细实施步骤

1. 在 Golden 测试固定现有输入、StateDelta、终局 Episode 和 max_turn 行为。
2. 定义 scenario 与 worker 两个端口，新增 Golden adapter；现有 Golden 规则仍为唯一来源。
3. 修改 `LiveFirstTurnFactory` 构造参数与调用方法，从 scenario 注入允许签名和校验上下文；去掉对 Golden 类型的 `isinstance` 限制及成员依赖。
4. 修改 facade：scenario 决定输入合法性、可继续性及裁决 policy；workers 只创建执行者。
5. 修改 public projector：由可信 scenario decision 控制 can_submit，保持现有 wire shape；不能仅依赖 App 自己算轮次。
6. 修改 settlement / AO-03 finalization handler：使用 finalization_recipe 和 decision，结束后从已提交证据构建产物；移除通用 `FINAL_TURN` 引用，保留 Golden adapter 内的五轮常量。
7. `StoryRuntime._build_facade` 是注册表选择的唯一生产位置；未知内容 digest/rules_revision 拒绝开场或进入只读恢复，不静默选 Golden。
8. 增加测试专用场景 adapter，通过内部 service 注入，不通过放宽公开 schema 暴露。

# 6. 关键实现说明

独立测试场景采用“已提交 `exit_clue` 后终局，最大 3 轮”的规则，数据放拟新增 `engine/tests/fixtures/scenarios/conditional_exit/`。该名称仅测试合约示例，不属于 Canon 内容。确保至少一例第 2 轮结束，一例尚未满足条件但达到安全上限，由可信规则给出明确结束理由。

固定输入校验与自由输入解释分开：

- fixed method：scenario 必须提供 expected_input，完全匹配；无固定输入支持则拒绝该 method。
- live method：允许自由原话，但必须有真实 Worker capability；无模型时不将自由原话映射为固定动作。
- 两种方法都使用同一 scenario resolution/validation，不因 live 放宽裁决。

rules_revision 不只是追踪标签，它参与任务 recipe 和恢复绑定。内容更新不能改变已开会话规则；若需要升级会话，另立显式迁移，不在本包做。

不改旧 public `mode=golden_deterministic` 是有意控制范围；面板对 live 输入的文案纠正可以说明“固定场景规则”，但不把未定义新模式塞进旧枚举。公开多场景协议另立扩展包。

# 7. 测试方案

| 文件 | 用例 |
|---|---|
| `engine/tests/test_scenario_policy.py`（拟新增） | 两种结束条件、规则版本匹配、无 expected_input 的 fixed 拒绝 |
| `engine/tests/test_golden_five_turn_application.py` | Golden 五轮所有 oracle 不变 |
| `engine/tests/test_story_session_facade.py` | 注入第二场景无需改 service；live/fixed 都受同一规则 |
| `engine/tests/test_story_public_view.py` | can_submit 与领域结束状态一致 |
| `engine/tests/test_story_runtime.py` | 注册表白名单、未知版本拒绝、旧 bootstrap 恢复 |
| `contracts/tests/test_story_session_control.py` | 生产公开入口仍拒绝非 golden_001 |
| AO-03 `test_post_commit_worker.py`（若已合入） | finalization recipe 从场景取得，旧 job revision 保持可识别 |

# 8. 验收标准

工作区根目录；未执行：

```bash
python3 scripts/gate_profile.py check
python3 scripts/gate_profile.py run --profile FULL_P0 --cwd . --log-dir .hacf/logs/ao-04
```

- [ ] Golden 的输入限制、五轮结果、提交计数与 Episode 内容不变。
- [ ] 第二测试场景不同结束条件通过，通用 facade 不加场景 if 分支。
- [ ] live Worker 不依赖 Golden 类，规则值没有复制。
- [ ] 旧存档绑定旧内容与规则版本，未知版本失败关闭。
- [ ] 生产公开白名单未扩大，现有 Schema/Swift DTO 无无意变化。
- [ ] FULL_P0 与新增规则测试通过。

# 9. 风险与注意事项

原子回退：代码与可信规则注册表一起回退，不能将已创建新规则会话交给不认识它的版本。本包生产仍仅 Golden，因此无必要数据库 migration；若实施发现必须改存储结构，先修订本方案和迁移评审，不能自行扩大。

AO-03 是否已合入只影响执行位置：有 worker 时改变 handler 注入；无 worker 时改变原 settlement 注入。两者禁止同一分支双写。

不做任意用户内容、规则 DSL、动态插件、世界线编辑器、公开第二剧情、通用多世界管理。

# 10. Luna 执行清单

- [ ] 固化 Golden 回归并核实当前运行装配。
- [ ] 建立最小 scenario/worker 端口与唯一 Golden adapter。
- [ ] facade、live factory、projector、settlement 改为依赖端口。
- [ ] 测试场景证明条件结束，不开放生产入口。
- [ ] 规则版本绑定与旧 bootstrap 恢复完成。
- [ ] FULL_P0 / 凭单完成，记录未扩展的公开协议边界。
