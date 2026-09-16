# GitHub Actions 流水线与端到端质检基线 (v1.0)

> **状态**：工程交付与持续集成基线规范 · 生产就绪  
> **双层防御**：本地事务工作区 (`collab_pipeline.py`) + 云端 GitHub Actions 权威矩阵  
> **核心目标**：零上下文稀释 · 零越界提交 · 100% 架构不变量机器守卫  

---

## 1. CI/CD 双层防御架构体系 (Dual-Layer Defense)

为保障《诡秘世界》在多人与多 Agent 高度并发场景下的代码质量与架构不变量，工程构建了“本地极速反馈”与“云端权威守门”的双层防御闭环：

```text
┌────────────────────────────────────────────────────────┐
│               本地工作区 (Local Machine)                │
│   开发者 / 专精 Agent 在独立 Git Worktree 并行编码      │
└───────────────────────────┬────────────────────────────┘
                            │ 1. 提交前本地门禁
                            ▼
┌────────────────────────────────────────────────────────┐
│      第一道防线: Local Pre-Merge Gate (< 3 秒)          │
│  - scripts/agent_capsule.py verify (静态范围 + 单测)   │
│  - scripts/collab_pipeline.py integrate (三阶段门禁)    │
│  - 签发 sha256 机器防伪验收签名 (Machine Attestation)  │
└───────────────────────────┬────────────────────────────┘
                            │ 2. 推送分支并开启 PR
                            ▼
┌────────────────────────────────────────────────────────┐
│        第二道防线: GitHub Actions CI (云端权威验证)     │
│  ┌──────────────────────────────────────────────────┐  │
│  │ 1. capsule-audit.yml:                            │  │
│  │    - 提取 PR 修改文件，核验是否超出角色授权目录   │  │
│  │    - 校验 task_capsule 机器防伪签名有效性        │  │
│  ├──────────────────────────────────────────────────┤  │
│  │ 2. ci.yml (3-Stage Gates):                       │  │
│  │    - Stage 1: 架构适应度 AST 检查 & 28 项 Schema  │  │
│  │    - Stage 2: Python 3.14 + uv 25 项全量回归测试 │  │
│  │    - Stage 3: Swift 6 (macOS 26+) 8 项并发测试    │  │
│  └──────────────────────────────────────────────────┘  │
└───────────────────────────┬────────────────────────────┘
                            │ 3. 保护分支规则阻断
                            ▼
┌────────────────────────────────────────────────────────┐
│               主分支 main (绝对绿色演进)               │
│          仅允许 Fast-Forward (--ff-only) 洁净合流       │
└────────────────────────────────────────────────────────┘
```

---

## 2. 工作流流水线规格 (Workflows Specification)

### 2.1 核心质量门禁工作流 (`.github/workflows/ci.yml`)
- **触发条件**：
  - `push` 到 `main` 分支；
  - 针对 `main` 分支的 `pull_request`。
- **并发控制**：开启 `cancel-in-progress: true`，当同一 PR 提交新代码时自动取消陈旧构建，节约算力。
- **Job 编排**：
  1. **`architecture-and-contracts` (ubuntu-latest)**：
     - 运行 `python3 scripts/check_architecture_fitness.py`（静态扫描 Domain 零依赖、App 零直接数据库访问、AI 零直接 SQL）；
     - 循环校验全部 28 个 JSON Schema 语法与格式。
  2. **`python-engine` (macOS 26+ baseline / macos-latest)**：
     - 依赖 `architecture-and-contracts` 通过；
     - 使用 `astral-sh/setup-uv@v5` 开启依赖缓存，基于 `engine/uv.lock` 进行秒级环境复现；
     - 执行 `uv run pytest -v`，覆盖 25 项契约与适配层单测。
  3. **`swift-macos-app` (macOS 26+ baseline / Apple Silicon arm64)**：
     - 依赖 `architecture-and-contracts` 通过；
     - 使用 `actions/cache@v4` 缓存 `macos-app/.build` SPM 编译产物；
     - 激活 Swift 6 严格并发检查，执行 `swift test`，覆盖 8 项跨语言与 Actor 测试。
  4. **`all-gates-passed` (ubuntu-latest)**：
     - 作为 GitHub Branch Protection 的单一聚合检查点（Required Status Check）。

### 2.3 实时质量报告与 Sticky 评论工作流 (`.github/workflows/pr-gate-reporter.yml`)
- **触发条件**：`pull_request` 打开、更新或重开。
- **核心逻辑**：
  1. 调用 `scripts/generate_pr_report.py` 结构化提取任务胶囊状态、执行角色、不变量与防伪机器签名；
  2. 使用 `actions/github-script@v7` (Node 20 驱动) 自动发布或更新 PR 顶部的实时门禁报告卡片，避免重复刷屏。

### 2.4 夜间全景深度回放工作流 (`.github/workflows/nightly-golden-audit.yml`)
- **触发条件**：每日 UTC 02:00 (北京时间 10:00) 定时触发，或支持 `workflow_dispatch` 手动一键触发。
- **核心逻辑**：
  1. 在 `macos-latest` (macOS 26+ baseline) 运行全量契约双向往返验证；
  2. 执行 Golden 001 场景 5 轮状态机深度回放；
  3. 执行 Swift 6 全量测试与架构适应度 AST 扫描；
  4. 使用 `actions/upload-artifact@v4` 归档为期 14 天的审计工件。

---

## 3. GitHub Actions 现代工程基线与安全准则

为严格符合现代 CI/CD 工业级安全与效能规范，全流水线强制贯彻以下准则：

| 规范项 | 工业级标准要求 | 《诡秘世界》实施落地 |
|:---|:---|:---|
| **官方 Actions 生命周期** | 必须全面迁移至 Node 20 / Node 22 运行时，严禁使用已弃用的 v3 | 全面采用 `actions/checkout@v4`, `actions/setup-python@v5`, `astral-sh/setup-uv@v5`, `actions/cache@v4`, `actions/upload-artifact@v4`, `actions/github-script@v7`。 |
| **最小权限原则 (Least Privilege)** | 顶层禁用通配写权限，显式限制只读 | 所有工作流顶层严格配置 `permissions: contents: read`；仅在 PR Reporter 中局部按需开放 `pull-requests: write, issues: write`。 |
| **超时保护 (Timeout Guard)** | 严禁无超时任务，防止 runner 死锁耗费配额 | 所有 Job 均显式声明 `timeout-minutes: 5 ~ 25`，异常卡顿自动自愈熔断。 |
| **Runner 架构匹配** | 淘汰 Intel x86 runner，对齐 Apple Silicon 硬件与 macOS 26+ 平台基线 | 编译与测试统一采用 `macos-latest` (Apple Silicon arm64, macOS 26+) 与 `ubuntu-latest` 组合。 |
| **自动化依赖升级** | 必须具备自动化依赖与 Actions 追踪机制 | 引入 `.github/dependabot.yml`，每周一全自动审查 Actions、Python 及 SPM 依赖更新。 |

---

## 4. 缓存与性能极致优化 (Caching & Performance Optimization)

为避免 macOS 云端 Runner 排队等待与高昂配额消耗，工程落实了深度缓存策略：

| 构件类型 | 缓存机制 | 缓存 Key 规划 | 命中后收益 |
|:---|:---|:---|:---|
| **Python 依赖** | `astral-sh/setup-uv@v5` 内置全局缓存 | `engine/uv.lock` 哈希计算 | 依赖准备耗时从 45s 降至 **< 2s** |
| **Swift SPM 依赖** | `actions/cache@v4` | `${{ runner.os }}-spm-${{ hashFiles('macos-app/Package.resolved') }}` | 编译构建耗时由 40s 压缩至 **< 6s** |
| **AST 架构检查** | 纯 Python 标准库静态分析 | 无外部依赖 | 耗时稳定在 **< 0.5s** |

整体 CI 流水线端到端耗时控制在 **1.5 分钟以内**。

---

## 5. GitHub 仓库分支保护规则推荐 (Branch Protection Recommendations)

在 GitHub 仓库后台设置 `main` 分支保护规则（Settings -> Branches -> Branch protection rules）：

1. **Require a pull request before merging**：
   - 勾选 `Require approvals` (至少 1 位人类架构师或 Arbiter 批准)；
   - 勾选 `Dismiss stale pull request approvals when new commits are pushed`。
2. **Require status checks to pass before merging**：
   - 勾选 `Require branches to be up to date before merging`；
   - 添加以下两项必过检查：
     - `All Quality Gates Passed` (来自 `ci.yml`)；
     - `Audit Task Capsule Scope & Attestation` (来自 `capsule-audit.yml`)。
3. **Require signed commits** (推荐)。
4. **Require linear history**：
   - 强制只允许 Squash and merge 或 Rebase and merge，禁止生成非线性 Merge Commit。
