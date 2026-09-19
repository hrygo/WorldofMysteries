# CI 变更面感知与效率优化设计

## 状态

待评审设计。设计日期：2026-09-19。

## 背景与问题

当前 `.github/workflows/ci.yml` 对每个 `pull_request` 和 `main` push 都启动 Python 与 Swift 两个昂贵平台 job。实测一次纯文档 PR 仍运行完整 Swift/Xcode 流程，workflow 用时约 5 分 36 秒；最近一次成功核心 CI 约 2 分 38 秒，其中 Swift job 约 2 分 04 秒。Stage 1 静态检查仅约 6 秒，因此主要优化机会是避免无关平台 job，而不是拆散快速静态检查。

当前 Swift cache 还存在语义错配：workflow 缓存 `macos-app/.build`，但 `swift test` 使用 `${RUNNER_TEMP}/wom-spm-scratch`；`macos-app/Package.swift` 没有外部依赖。该 cache 不覆盖实际测试 scratch，也没有值得保留的依赖复用面。

## 目标与非目标

### 目标

1. 纯文档/协同元数据 PR 不启动 Python 和 Swift macOS runner。
2. 仅改 Python/Engine 的 PR 不启动 Swift job；仅改 macOS App 的 PR 不启动 Python job。
3. 协议、治理、CI、脚本及无法安全分类的路径继续触发完整双栈验证。
4. 保留 branch protection 公开检查名 `All Quality Gates Passed` 与 `Capsule Gate`，不要求仓库管理员同步新的 required-check 名称。
5. 变更面检测失败时 fail-closed：不允许因检测异常而静默跳过门禁。
6. 删除无效的 SPM cache 与重复的 `uv lock --check`，保留 `uv run --locked` 和现有 uv cache。

### 非目标

- 不拆分或重命名 HACF required workflows。
- 不改变门禁 profile、门禁命令、分支保护规则或测试断言语义。
- 不缓存 Xcode `DerivedData`；其路径包含 runner 临时目录，且跨 Xcode/SDK 复用的收益与失效风险尚未有实测依据。
- 不把 nightly、bundled-engine 或 component-gallery workflow 合并进核心 CI。

## 设计

### 1. 变更面分类器

新增 `scripts/ci_changed_scope.py`，仅使用 Python 标准库，接收 NUL 分隔的变更路径并写入 GitHub Actions `$GITHUB_OUTPUT`。输出最小集合：

- `run_python=true|false`
- `run_swift=true|false`
- `scope=meta|python|swift|full`

分类规则按“宁可多跑、不可漏跑”设计：

| 路径 | Python job | Swift job |
| --- | ---: | ---: |
| `docs/**`、`.agents/**`、Markdown 元数据 | 否 | 否 |
| `engine/**`、`engine/uv.lock`、`engine/pyproject.toml`、`fixtures/**` | 是 | 否 |
| `macos-app/**` | 否 | 是 |
| `contracts/**` | 是 | 是 |
| `scripts/**`、`.hacf/**`、`.github/**`、根级构建配置 | 是 | 是 |
| 未知路径、空输入、解析错误 | 是 | 是 |

`ci.yml` 的 `change-scope` job 负责 checkout 完整历史、计算当前事件的 diff，并将路径流交给分类器。PR 使用 base...head 三点 diff，并优先执行 base SHA 中受信任的分类器版本；base 分支尚未提供分类器时直接写入 full 选择，不执行 PR 工作树中的分类器。main push 使用 before..head 两点 diff；首次 push 或无法解析 ref 时直接进入 full 模式。聚合 job 还会校验 `scope` 与两个布尔输出的四种合法组合，不一致时 fail-closed。

### 2. 核心 CI job 拓扑

- `architecture-and-contracts` 始终执行，作为便宜且稳定的仓库级快速检查。
- `python-engine` 增加 `needs: [change-scope, architecture-and-contracts]` 与 job-level `if`，仅在 `run_python=true` 时创建 runner。
- `swift-macos-app` 使用相同模式，仅在 `run_swift=true` 时创建 runner。
- `all-gates-passed` 保持原 job name、`if: always()` 和 required-check 语义。它先要求 `change-scope` 与架构 job 成功，再按分类器输出判断是否需要 Python/Swift job；被明确分类为不需要的 job 为 skipped 时视为合法，不满足条件但意外失败仍阻断。

不使用 workflow-level `paths` 过滤核心 CI，因为 GitHub 对被整体跳过的 required workflow 保留 Pending 状态，可能阻塞 PR 合并；使用 job-level `if` 保留 required aggregate check 的稳定结果。

### 3. 缓存与重复检查

- 删除 `ci.yml` 中 `actions/cache@v6` 的 SPM `.build` step；Swift 测试继续使用隔离的 `${RUNNER_TEMP}/wom-spm-scratch`。
- 删除 `uv lock --check`，保留 `uv run --locked --extra dev pytest -v`，由同一个 uv invocation 完成 lock freshness 校验与环境同步。
- 保留 `astral-sh/setup-uv@v10.1.0` 的内置 cache、现有并发取消和所有 timeout。
- `pr-gate-reporter.yml` 去掉无变更内容的 `edited` 触发，只保留 PR 状态/提交变化相关事件。

### 4. 可观测性与兼容性

`change-scope` 在 job summary/log 中打印 scope、变更文件计数和最终选择；不把仓库路径原文写入 `$GITHUB_OUTPUT`，避免多行文件名破坏输出格式。分类器的未知路径与异常测试必须覆盖 fail-closed 行为。

更新 `docs/03_工程规范/GitHub_Actions_流水线与端到端质检基线_v1.0.md`：删除“SPM cache 命中后 <6s”和“整体 CI <1.5 分钟”的未经当前运行数据支撑表述，记录变更面选择性执行和可复核的基准口径。

## 验收标准

1. 分类器单测覆盖 meta-only、Python-only、Swift-only、contract/full、unknown、空输入和非法 NUL/编码输入。
2. workflow 静态测试确认两个 required job name 不变、aggregate 使用 `always()`、平台 job 使用 job-level `if`，且不存在 workflow-level `paths` 过滤核心 CI。
3. `python3 scripts/check_required_checks.py`、`python3 scripts/gate_profile.py check` 通过。
4. 本地运行分类器测试与相关 Python governance tests 通过。
5. 运行 `bash scripts/gate_runner.sh` 对应门禁；最终报告区分本地验证与尚未发生的云端 Actions 验证。
6. 变更不修改当前用户已有的未提交文件，且 `git diff --check` 通过。

## 风险与回退

- 主要风险是路径规则遗漏导致漏跑平台门禁。unknown/full 默认和治理路径双栈策略降低该风险；分类器单测锁定规则。
- 主要兼容性约束是 required check 名称。保留现有 `name` 字段，并让 aggregate 显式处理 skipped job。
- 回退方式是还原 `ci.yml` 的 job conditions、恢复 SPM cache step 和 `uv lock --check`；分类器脚本可独立删除，不改变领域代码。

## 参考

- [GitHub Actions workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [GitHub Actions job conditions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-jobs-with-conditions)
- [GitHub dependency caching](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching)
- [uv locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/)
- [`ci.yml`](../../../.github/workflows/ci.yml)
- [`gate_profile.py`](../../../scripts/gate_profile.py)
