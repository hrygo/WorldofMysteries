# 诡秘世界 · World of Mysteries

> 以 Canon（原著历史）为不可变底座、持续世界状态为现实、人物长期身份与记忆为主体、语音驱动互动叙事为主要体验的**单人持久世界**应用（前置工程）。

<p>
  <a href="https://github.com/hrygo/WorldofMysteries/actions/workflows/ci.yml"><img src="https://github.com/hrygo/WorldofMysteries/actions/workflows/ci.yml/badge.svg" alt="CI 状态" /></a>
  <img src="https://img.shields.io/badge/macOS-26.0%2B-000000.svg?logo=apple&logoColor=white" alt="macOS 26.0+" />
  <img src="https://img.shields.io/badge/Swift-6.4-F05138.svg?logo=swift&logoColor=white" alt="Swift 6.4" />
  <img src="https://img.shields.io/badge/Python-3.14.7-3776AB.svg?logo=python&logoColor=white" alt="Python 3.14.7" />
  <img src="https://img.shields.io/badge/AgentScope-2.0.8-1f6feb.svg" alt="AgentScope 2.0.8" />
  <img src="https://img.shields.io/badge/SQLite-4--database%20isolation-003B57.svg?logo=sqlite&logoColor=white" alt="SQLite 四库隔离" />
</p>

---

## 1. 一句话定义

《诡秘世界》是一套以 Canon 为历史底座、以持续世界状态为现实、以人物长期身份与记忆为主体、以语音驱动互动叙事为主要体验的单人持久世界应用。

世界不会因一篇故事结束而重置；人物不会因一次模型调用重新生成；模型不能直接修改世界事实。

## 2. 关联仓库

本仓库是《诡秘世界》的**应用本体**（macOS 宿主应用 + Local Engine + 数据内核）。它的 Canon 内容生产面——22 条成神途径 × 序列 9→0 的正典核验、单卡六维设计与分层卡面生产——在**独立仓库**维护：

| 仓库 | 职责 | 地址 |
|---|---|---|
| `hrygo/WorldofMysteries` | 本仓库：《诡秘世界》应用本体（宿主应用 / Local Engine / 数据内核） | https://github.com/hrygo/WorldofMysteries |
| `hrygo/lotm-card-art` | 卡牌制作工具：序列卡槽正典、六维语义契约与分层卡面生产线 | https://github.com/hrygo/lotm-card-art |

边界：卡牌正典事实源（途径、序列、配方、扮演、晋升与限制）在卡牌仓库维护，本仓库只**单向消费**其结论，不重复维护第二份、不反向写入；两仓库之间不建立代码依赖。详见 [`AGENTS.md`](AGENTS.md) 第 3 节。

---

## 3. 工程形态

| 层次 | 技术基线 |
|---|---|
| macOS 宿主应用 | SwiftUI / Swift 6.4 / macOS 26+ / Apple Silicon arm64，SPM 构建 |
| Local Engine Service | Python 3.14.7（标准 GIL CPython）+ AgentScope 2.0.8 + `uv` 依赖管理 |
| 数据内核 | SQLite 本地多模型四库物理隔离：`canon.db` / `world.db` / `retrieval.db` / `runtime.db` |
| 进程通信 | UDS IPC + NDJSON，32-bit length prefixed framing（App 不直连数据库） |
| 语音交互 | OpenAI Audio API 规范适配器，默认对接本地 SpeechRail，支持兼容第三方热拔插 |
| 协同框架 | HACF 2.0（任务胶囊切片 + Git Worktree 事务隔离 + sha256 机器验签） |

```text
Canon ─▶ Domain Truth (World · Character · Memory · Story · Outcome Resolver)
              │
        Session Orchestrator
              ├─▶ Context Compiler ─▶ AI Gateway (AgentScope) ──▶ Typed Proposal ─┐
              └─▶ Deterministic Core ───────────────────────────────────────────────┤
                                                                                    ▼
                                          Resolver / Validators ──▶ COMMIT ──▶ Narrative / Audio / Voice ──▶ User
```

## 4. 核心不变量

系统无条件遵守 15 条不变量，其中最有约束力的三条：

1. **AI 仅产出 Proposal，Domain Engine 负责 Commit** —— 任何 LLM / Agent 禁止直接写入领域数据库；
2. **零知识越界 (Zero Knowledge Leak)** —— `Character Reasoner` 严禁接收超出该角色已知边界的信息；
3. **提交即命运** —— `Narrative Compiler` 与 `Audio / Voice Engine` 严格位于 `COMMIT` 之后，表达层失败不得反向篡改已提交事实。

完整 15 条清单与逐项判定标准见 [`AGENTS.md`](AGENTS.md) 第 2 节。

## 5. 仓库结构

```text
contracts/    跨语言协议与 Schema 唯一事实源（28 个 JSON Schema）
engine/       Local Engine Service：domain / application / infrastructure / ai / tests
macos-app/    SwiftUI 宿主应用与 IPC 客户端、DomainContracts DTO、Swift Testing 测试
fixtures/     Golden Scenario 固件（golden_001 5 轮状态断言资产）
scripts/      治理与门禁脚手架（capsule / pipeline / fitness / 报告）
.agents/      多 Agent 协同元数据：7 大专精角色提示词与任务胶囊
.github/      CI/CD 工作流、Issue/PR 模板、CODEOWNERS、Dependabot
docs/         完整设计文档与工程基线规范（主入口 docs/README.md）
```

## 6. 快速开始

环境要求：macOS 26+（Apple Silicon arm64）、Xcode 27 / Swift 6.4、Python 3.14.7、`uv`。

```bash
# 全量本地三阶段门禁（架构适应度 + Python + Swift）
bash scripts/gate_runner.sh

# 分阶段单独执行
python3 scripts/check_architecture_fitness.py
cd engine && uv run pytest -q
cd macos-app && swift test
```

## 7. 质量保障

双层防御：本地极速拦截（`scripts/gate_runner.sh`，秒级）+ 云端权威守门（GitHub Actions）。

| 工作流 | 作用 |
|---|---|
| `.github/workflows/ci.yml` | Stage 1 架构适应度与 Schema、Stage 2 Python、Stage 3 Swift，聚合为 `All Quality Gates Passed` |
| `.github/workflows/capsule-audit.yml` | 核验 PR 未超出角色 `authorized_scope` 与任务胶囊签名 |
| `.github/workflows/pr-gate-reporter.yml` | 在 PR 自动发表质检报告卡片 |
| `.github/workflows/nightly-golden-audit.yml` | Golden Scenario 夜间回归 |

## 8. 人机协同开发 (HACF 2.0)

```bash
# 1. 任务切片派发
python3 scripts/agent_capsule.py pack --role <ROLE> --task-id <TASK_ID> --title "<TITLE>"

# 2. 并行无锁工作区
python3 scripts/collab_pipeline.py start --branch feat/<branch> --role <ROLE> --task-id <TASK_ID>

# 3. 验签与原子合入
python3 scripts/agent_capsule.py verify --capsule .agents/capsules/<TASK_ID>.json
python3 scripts/collab_pipeline.py integrate --branch feat/<branch> --auto-clean
```

7 大专精角色（`AGT-ARB` / `AGT-DOM` / `AGT-DATA` / `AGT-AI` / `AGT-VOICE` / `AGT-MAC` / `AGT-QA`）的职责与授权目录见 [`AGENTS.md`](AGENTS.md) 第 4 节。

## 9. 文档索引

| 模块 | 路径 |
|---|---|
| 工程交付基线（主入口） | [`docs/README.md`](docs/README.md) |
| 总体架构与 ADR | [`docs/01_总体架构/`](docs/01_总体架构/) |
| 领域引擎设计 | [`docs/02_领域引擎/`](docs/02_领域引擎/) |
| 工程规范与协议契约 | [`docs/03_工程规范/`](docs/03_工程规范/) |
| Golden Scenarios 回归基准 | [`docs/04_Golden_Scenarios/`](docs/04_Golden_Scenarios/) |
| 工程启动与 P0 门禁 | [`docs/07_工程启动/`](docs/07_工程启动/) |

---

**状态**：工程交付基线 v1.0 · 未执行的技术 Gate 不因文档存在而被视为已通过。
