# AGENTS.md

> **项目名称**：《诡秘世界》（World of Mysteries）  
> **工程形态**：SwiftUI macOS App (arm64, macOS 26+) + 同机独立 Local Engine Service (Python 3.14.7 CPython standard GIL build + AgentScope 2.0.8)  
> **数据内核**：SQLite 本地多模型四库物理隔离架构（`canon.db`, `world.db`, `retrieval.db`, `runtime.db`）  
> **语音交互**：OpenAI Audio API 规范适配器，默认对接本地 SpeechRail (WebSocket/REST)，支持任意兼容第三方热拔插  
> **协同框架**：HACF 轻量模式（CI 与评审为主，任务凭证按需） + GitHub Actions 工业级双层防御流水线
> **核心规范根目录**：[`docs/`](docs/)（主入口：[`docs/README.md`](docs/README.md)）
>
> **关联仓库（卡牌制作工具）**：[`hrygo/lotm-card-art`](https://github.com/hrygo/lotm-card-art) —— Canon 内容生产面（22 条成神途径 × 序列 9→0 的正典核验、六维语义契约与分层卡面生产）；本仓库单向消费其结论，不重复维护、不反向写入。

---

## 1. 核心架构与系统总览

《诡秘世界》是一套以 Canon（原著历史）为不可变底座、持续世界状态为现实、人物长期身份与记忆为主体、语音驱动互动叙事为主要体验的单人持久世界应用。

```text
                         Lore / Canon
                              │
                              ▼
┌─────────────────────────────────────────────────────────┐
│                    Domain Truth                         │
│  World Engine · Character Engine · Memory & Knowledge  │
│  Story Engine · Outcome Resolver · Validators           │
└───────────────────────────┬─────────────────────────────┘
                            │
                   Session Orchestrator
                            │
                  ┌─────────┴─────────┐
                  ▼                   ▼
           Context Compiler      Deterministic Core
                  │                   │
         Authorized Context           │
                  ▼                   │
        Mysterious AI Gateway         │
                  │                   │
             AgentScope 2.0.8           │
        ┌─────────┼─────────┐         │
        ▼         ▼         ▼         │
   Model Call  Bounded Agent Tools    │
        └─────────┬─────────┘         │
                  ▼                   │
             Typed Proposal ──────────┘
                  │
          Resolver / Validators
                  │
                COMMIT
                  │
                  ▼
         Narrative / Performance
                  │
                  ▼
           Audio / Voice Engine (SpeechRail / OpenAI API)
                  │
                  ▼
                User
```

---

## 2. 绝对不可违背的核心不变量 (Invariants)

在为此项目编写、修改代码或进行架构设计时，**必须无条件遵守以下 15 条不变量**：

1. **世界先于故事**：世界状态独立演化，不因单次故事结束而重置。
2. **角色先于剧情**：角色具有稳定的身份、特质与目标，不会因单次模型调用重新生成。
3. **Canon 约束历史**：Canon 定义已发生的既定历史事实，不锁死未发生的开放未来。
4. **Advice ≠ Command**：玩家的干预（Advice）仅为意图建议，角色有自己的动机判断。
5. **AI 仅产出 Proposal，Domain Engine 负责 Commit**：任何 LLM / Agent 绝对禁止直接写入领域数据库。
6. **零知识越界 (Zero Knowledge Leak)**：`Character Reasoner` 严禁接收超出该角色已知边界与当前观察事实的信息。
7. **语义授权先行**：`Context Compiler` 负责裁决“有资格获知什么”；AgentScope 仅负责“执行模型上下文”。
8. **领域记忆与 Agent 记忆彻底分离**：AgentScope Runtime Memory 仅作为单次调用/执行辅助，领域事实与角色记忆的唯一事实源是 Domain Database。
9. **提交即命运**：`Narrative Compiler` 与 `Audio / Voice Engine` 严格位于 `COMMIT` 之后。表达层重试、TTS 失败或 UI 崩溃不得反向篡改已提交事实。
10. **用户世界绝不污染 Canon**：`user_world` 写入独立数据库，严禁反向写回 `canon.db`。
11. **权威持久与可重建分离**：`world.db` 承担权威强事务持久化；`retrieval.db` 仅为异步投影，删除后必须可 100% 幂等重建。
12. **App 进程不直连数据库**：SwiftUI App 仅通过类型化本地 IPC 与 Local Engine 交互，不直接读写 Domain SQLite。
13. **无全量后台模拟**：默认不运行后台全量 MMO 式 NPC 自主模拟，采用事件驱动与局部活跃窗口。
14. **世界时钟叙事推进**：世界时间由叙事与回合事件推进，不直接硬绑定现实物理时间。
15. **显式世界线分叉**：任何重大 Worldline 分叉必须显式登记与隔离。

---

## 3. 代码库组织规范 (Repository Layout)

```text
repo/
├── contracts/               # 跨语言协议与 Schema 唯一事实源
│   ├── schemas/            # 27 个产品领域 Schema (*.schema.json：实体、信封、Proposal 等)
│   ├── protocol/           # 1 个 IPC 通信协议 (engine_ipc.schema.json)
│   └── engineering/        # 研发编排协议 (task_capsule / work_receipt / gate_profile)，与产品契约分开版本化
├── .hacf/                   # HACF 受保护门禁档案 (gates/*.json + registry.json) 与工作区资源租约
│   ├── gates/              # 受保护门禁档案：命令主权在此，胶囊与角色默认值均不得内嵌命令
│   └── workspace.json     # 每个 Worktree 的运行时资源命名空间租约 (TMPDIR/SPM/DB/socket/端口段)
├── engine/                  # Local Engine Service (Python 3.14.7 + AgentScope 2.0.8)
│   ├── domain/             # 领域核心：无外部 SDK/DB 依赖纯逻辑 (Fan-in: 6, Fan-out: 0)
│   ├── application/        # 用例编排、事务管理 (Session Orchestrator, Context Compiler)
│   ├── infrastructure/     # SQLite 持久化 (四库隔离)、Outbox、UDS IPC 服务端、Audio 适配层
│   ├── ai/                 # AgentScope Adapter, Model Router, Prompt Registry
│   └── tests/              # 单元测试与领域测试 (pytest)
├── macos-app/               # macOS 宿主应用 (SwiftUI, macOS 26+, arm64)
│   ├── WorldOfMysteries/   # 视图与状态管理、IPC 客户端、DomainContracts DTO
│   └── WorldOfMysteriesTests/ # 客户端单元测试与并发测试 (Swift Testing)
├── fixtures/                # Golden Scenario 固件 (golden_001 5 轮状态断言资产)
├── scripts/                 # 治理、自动化流水线与门禁脚手架
│   ├── agent_capsule.py    # 不可变任务契约切片 + 四类范围裁决 + Work Receipt 签发 CLI
│   ├── collab_pipeline.py  # 事务型并行工作区流水线 (独立 env + 资源租约 + CAS 合入 + 集成凭单)
│   ├── gate_profile.py     # 受保护门禁档案解析/执行与 registry 摘要校验
│   ├── hacf_policy.py      # 边界裁决与凭单内核 (sha256 内容摘要，不冒充密码学签名)
│   ├── capsule_audit.py    # PR 范围、门禁主权与凭单证据审计 (CI 权威入口)
│   ├── check_architecture_fitness.py # 架构适应度 AST 检查
│   ├── generate_pr_report.py # PR 证据摘要卡片 (只复述凭单事实，不宣称测试结论)
│   └── gate_runner.sh      # 受保护门禁启动器 (薄封装，无内嵌命令)
├── .agents/                 # 多 Agent 协同元数据与模板
│   ├── prompts/            # 7 大专精 Agent 角色提示词模板 (01 到 07)
│   ├── capsules/           # 不可变任务契约 JSON (verify 严禁回写)
│   └── receipts/           # Work / Integration Receipt（可选治理模式的历史凭证）
├── .github/                 # GitHub 原生协同与自动化 CI/CD 体系
│   ├── workflows/          # ci.yml, capsule-audit.yml, pr-gate-reporter.yml, nightly-golden-audit.yml
│   ├── ISSUE_TEMPLATE/     # 01_agent_task.yml, 02_architecture_spike.yml, config.yml
│   ├── CODEOWNERS          # 7 大专精角色目录所有权硬防线
│   ├── dependabot.yml      # 自动化依赖与 Actions 版本追踪
│   └── PULL_REQUEST_TEMPLATE.md # 门禁自检与凭单证据核验清单
└── docs/                    # 完整设计文档与工程基线规范
```

### 关联仓库 (Related Repositories)

- **本仓库** `hrygo/WorldofMysteries`：应用本体（macOS 宿主应用 + Local Engine + 数据内核 + HACF 协同框架）。
  - 地址：https://github.com/hrygo/WorldofMysteries
- **卡牌制作工具** `hrygo/lotm-card-art`：Canon 内容生产面（22 条成神途径 × 序列 9→0 的序列卡槽、六维语义契约、分层卡面生产与素材 provenance）。
  - 地址：https://github.com/hrygo/lotm-card-art
- **边界约束**：
  - 卡牌正典事实源（途径、序列、配方、扮演、晋升、限制与批准状态）只在卡牌仓库维护；本仓库**不得**重复维护第二份，也**不得**反向写入或据本仓库界面改动其卡牌契约与批准记录（不变量 10「用户世界绝不污染 Canon」的仓库级对应）。
  - 两仓库**不共享代码依赖**：不互相 import、不互相引用本地文件路径；文档与记录中的跨仓库引用一律使用上面的 GitHub 地址。
  - 本仓库消费卡牌内容只发生在「内容注入」边界上，不得把具体卡牌设定硬编码进 `engine/domain/`。

### 模块依赖边界约束 (Ownership Boundaries)
- `engine/domain/`：**严禁** import AgentScope、SQLite 驱动（如 sqlite3 / aiosqlite）或任何云厂商 SDK。
- `engine/ai/`：作为适配层接入 AgentScope，但**严禁**直接操作 SQLite 写事务。
- `macos-app/`：**严禁** 依赖 Python 运行时内部类型或直接读取 `world.db`，严格通过 UDS IPC NDJSON 通信。
- `contracts/`：跨语言交互的唯一协议与 Schema 源头，Swift 与 Python 均由其严格生成与校验。
- `.hacf/gates/`：**门禁命令主权的唯一所在**。任何脚本、胶囊、角色默认值**严禁**内嵌验收命令；
  经用户授权覆盖档案后必须执行 `python3 scripts/gate_profile.py refresh-registry` 并附架构评审。
- `.agents/capsules/`：不可变任务契约，`verify` **严禁**回写；验收结果一律写入 `.agents/receipts/`。
- `docs/` 及所有 Markdown：**严禁**泄露开发机绝对路径（如 `file:///Users/...` 或 `/Users/...`），文档与文件链接一律只允许使用相对于项目根目录或当前文档的相对路径。
- **仓库根目录（Root Cleanliness）**：**严禁**随意在项目根目录生成、倾倒临时文件、中间报告、调试日志或脚本（如 `pr_report.md`、`*.log`、`*.tmp` 等）。所有自动化工具、流水线与 Agent 作业产物必须严格收拢至指定子目录：
  - 流水线/门禁临时报告：统一写入 `.hacf/tmp/`；
  - 运行与测试日志：统一写入 `.hacf/logs/` 或 `logs/`；
  - 运行时套接字与状态：统一写入 `.hacf/run/` 或 `run/`；
  - 临时脚手架与本地调试数据：统一放入 `scratch/` 或 `.agents/scratch/`。
- **工作区运行时租约（`.hacf/workspace.json`）**：`tmpdir` 与 `ipc_socket` 必须留在短路径命名空间
  （`/tmp/wom-ws-<branch-hash>/`，可用 `WOM_WORKSPACE_RUNTIME_BASE` 覆盖父目录），不得改回工作区目录内。
  macOS 的 AF_UNIX `sun_path` 上限为 104 字节（实测可用 103），而工作区路径本身已有 60+ 字符；把 TMPDIR
  放回工作区内会让 IPC 测试整片失败，而 CI 因没有租约文件、TMPDIR 保持系统默认反而恒绿——这种「本地假红」
  比失败更难排查。`spm_scratch` / `test_db_dir` / `log_dir` 不受该限制，仍留在工作区内便于取证；
  `abort` 与 `integrate --auto-clean` 负责回收短命名空间。短命名空间不在工作区目录内，
  **不会随工作区删除而消失**：不显式回收，`/tmp/wom-ws-*` 会独立残留（合并后回收见 §4.2 第 6 步）。

---

## 4. 日常研发流程（HACF 轻量模式）

> 2026-10-03 起，依据 [ADR-009](docs/01_总体架构/ADR-009_HACF日常流程轻量化.md)，
> 本节取代旧 HACF 2.1 的日常强制 SOP。旧文档、角色模板与胶囊说明仅供显式治理模式使用。

### 4.1 默认流程

1. 查清用户目标、现状、影响与必要回退；一个功能可以在同一分支跨目录完成。
2. 开发并按改动面验证；需要时使用 `gate_profile.py resolve` 与受保护档案。
3. PR 描述说明问题、结果、验证与实际风险；CI 和评审决定是否可合入。
4. 并行写入或主工作区不干净时使用独立 worktree、独立环境与短路径运行资源。
   普通单人任务不强制隔离工作区；回收前确认工作区干净且内容已落地，不强删未知改动。

日常任务**不要求**任务胶囊、Work Receipt、Integration Receipt、按角色目录拆任务、
本地 `integrate` 预演或凭单独立提交。授权来自用户，角色不能扩大授权。
用户数据保护、第 2 节的 15 条不变量、第 3 节的产品模块依赖边界及跨语言契约要求保持有效。

### 4.2 质量门禁

- `All Quality Gates Passed`：架构与契约、Python、Swift 和真实 Xcode App 构建，按变更面执行。
- `Capsule Gate`：保留历史检查名以兼容分支保护；默认仅校验门禁档案与 registry 一致性，
  不读取历史胶囊、不要求任务凭单，不以 Agent 自述的目录授权阻断日常 PR。
- 门禁配置、CI、契约和数据迁移等高风险变更先分析影响与回退，按用户已授权范围实施；
  不再通过新造角色或胶囊 grant 代替人类授权。档案变更仍须同步 registry 并接受评审。
- 测试通过不等于功能已完成；真实接线、真实服务与用户体验按对应验收要求核实。

```bash
python3 scripts/gate_profile.py resolve
python3 scripts/gate_profile.py run --profile <ID>
python3 scripts/capsule_audit.py --base-ref origin/main
```

### 4.3 可选治理模式

用户或任务明确选择严格多执行者治理时，才使用旧 `pack → start → commit → verify → receipt`
流程和 `capsule_audit.py --mode governed`。7 个角色代号、胶囊/凭单 Schema 与历史证据保持可用，
角色目录授权只在该模式内裁决；参考 [HACF 2.1 旧实施方案](docs/03_工程规范/高效人机协同研发体系实施方案_v1.1.md)。
不得为普通任务自动恢复旧流程，不批量删除历史证据或已有工作区。

---

## 5. GitHub CI 与评审

日常研发按改动面运行本地验证，云端 CI 提供合入必需检查。运行耗时以实际日志为准。

| 工作流 | 日常职责 |
|---|---|
| `ci.yml` | 架构与契约、Python、Swift 与 Xcode App 构建；按变更面选择平台作业 |
| `capsule-audit.yml` | 门禁配置一致性检查；保留 `Capsule Gate` 名称，不强制任务凭证 |
| `pr-gate-reporter.yml` | 仅带人工添加的 `hacf-evidence` 标签时生成凭单报告 |
| `nightly-golden-audit.yml` | Golden 夜间回归 |

受保护 `main` 仍通过 PR 与必需检查合入；日常流程不要求本地集成预演或额外凭单。

### GitHub Actions 现代工程基线准则
- **官方 Actions 运行时**：必须基于 Node 24 运行时（现行基线：`actions/checkout@v7`、`actions/setup-python@v7`、`actions/cache@v6`、`astral-sh/setup-uv@v10.1.0`、`actions/github-script@v9`、`actions/upload-artifact@v7`；Node 20 时代的旧主版本已全部淘汰）；
  `astral-sh/setup-uv` 自 v8 起**不再发布大版本标签**（供应链加固），必须锁不可变全版本标签；写 `@v10` 会解析失败，依赖 Dependabot 自动跟进补丁版本；
- **最小权限原则**：工作流顶层默认强制配置 `permissions: contents: read`；
- **强制超时熔断**：所有 Job 显式声明 `timeout-minutes: 5 ~ 25`，杜绝 Runner 卡顿消耗；
- **平台基线对齐**：目标平台与构建环境严格对齐 **macOS 26+ (Apple Silicon arm64)**，Runner 统一写 `macos-latest`
  （Apple Silicon arm64 上的最新稳定镜像），**不写 `macos-<版本>` 之类的固定标签**，以免与 GitHub 镜像轮转脱节；
  `macos-app/Package.swift` 声明 `.macOS("26.0")`，镜像一旦低于该基线，Stage 3 的 `swift test` 会直接失败，
  不会静默降级；
- **依赖自愈追踪**：通过 `.github/dependabot.yml` 每周一自动审查 Actions 与项目依赖。

---

## 6. 关键规范参考索引

在进行具体任务前，请优先阅读并严格参照以下设计基线：

| 模块 / 需求 | 规范文档路径 | 核心要点 |
|---|---|---|
| **工程主线门禁** | [`docs/07_工程启动/`](docs/07_工程启动/) | `Go_NoGo_Gates_v1.0.yaml` 规定的 P0 门禁 |
| **总体架构 & ADR** | [`docs/01_总体架构/`](docs/01_总体架构/) | `ADR-001` (本地拓扑), `ADR-002` (数据架构), `ADR-003` (AI Runtime), [`ADR-004`](docs/01_总体架构/ADR-004_协同层门禁主权与凭证分离_v1.0.md) (协同层门禁主权与凭证分离), [`架构专家评估报告`](docs/01_总体架构/架构专家评估与系统优化报告_v1.0.md), [`系统核心深模块演进设计方案`](docs/01_总体架构/系统核心深模块演进设计方案_v1.0.md) |
| **领域引擎实现** | [`docs/02_领域引擎/`](docs/02_领域引擎/) | `World`, `Character`, `Story`, `Lore`, `Memory_Knowledge`, `Audio_Voice` (OpenAI 适配与 SpeechRail) |
| **工程与协议契约** | [`docs/03_工程规范/`](docs/03_工程规范/) | `Context_Compiler`, `Engine_API_Contracts`, `Data_Architecture`, `macOS_App_Platform_Baseline`, `Swift6_Xcode27_Best_Practices` |
| **人机协同与 CI/CD** | [`docs/03_工程规范/`](docs/03_工程规范/) | [`高效人机协同研发体系实施方案 v1.1`](docs/03_工程规范/高效人机协同研发体系实施方案_v1.1.md)（显式治理模式旧基线；日常流程以 [ADR-009](docs/01_总体架构/ADR-009_HACF日常流程轻量化.md) 为准）, [`GitHub Actions 质检基线`](docs/03_工程规范/GitHub_Actions_流水线与端到端质检基线_v1.0.md), [`GitHub 原生工作流规程`](docs/03_工程规范/GitHub_原生人机协同工作流作业规程_v1.0.md) |
| **回归测试基准** | [`docs/04_Golden_Scenarios/`](docs/04_Golden_Scenarios/) | `golden_001` 5 轮状态断言与端到端期望 |
| **关联仓库（卡牌制作工具）** | [`hrygo/lotm-card-art`](https://github.com/hrygo/lotm-card-art) | Canon 内容生产面：序列卡槽正典、六维语义契约与分层卡面生产（本仓库单向消费，见第 3 节） |

---

## 7. 开发与编码操作准则

1. **环境与运行约束**：
   - 目标架构为 Apple Silicon (macOS 26+ / arm64)；
   - Python 版本锁定为 **3.14.7**（标准 GIL CPython 构建），AgentScope 版本锁定为 **2.0.8**；
   - 使用 `uv` 作为依赖与包管理工具。
   - **解释器口径**：脚本、门禁与治理 CLI 一律跑在 Python 3.14.7（`python3` / `uv run`）。
     `/usr/bin/python3` 是系统自带的 3.9，无法解析仓库脚本里的 3.12+ 语法（f-string 内嵌同类引号会直接
     `SyntaxError`），用它执行 `scripts/*.py` 会得到误导性的失败。
2. **终端与测试执行优化（两个场景，规则相反，勿混用）**：
   - **本机实际执行**命令时遵循 RTK 路由规则：`git` / `pytest` / `swift` / `python3` 等命令加 `rtk` 前缀
     （如 `git status`、`uv run pytest`）；RTK 不支持或需要原始输出语义时直接执行并说明原因。
   - **写入持久化产物**（本文档、`docs/`、`.agents/`（prompts 与 skills）、PR / Issue 模板、CI 配置、示例命令）
     一律使用**可移植原生命令**（`python3`、`git`、`uv run`、`bash`），不写 `rtk` 前缀：这些产物会在其他机器、
     CI 与 GitHub Web 上被照抄，本机 wrapper 在那里不存在。判据只有一条——命令是「本机当场执行」还是
     「被记录/照抄」。
3. **代码与架构图谱分析**：
   - 涉及符号定义、调用链追踪（Call Graph）或重构影响分析时，优先调用 `codebase-memory-mcp` 工具（项目 ID：`Users-hrygo-Documents-WorldofMysteries`）。
4. **修改协议与 Schema**：
   - 任何对数据结构、IPC 协议的修改必须同步更新 `contracts/schemas/` 下的 JSON Schema 与 Pydantic/Swift 对应模型，禁止私自篡改破坏向下兼容性；
   - 研发编排协议（`contracts/engineering/`：task_capsule / work_receipt / gate_profile）与产品领域契约分开版本化，禁止混入产品 namespace。
5. **受保护门禁与凭单**：
   - 验收命令只能定义在 `.hacf/gates/*.json`；新增/调整门禁需同步 `python3 scripts/gate_profile.py refresh-registry`；
   - 显式治理模式中 `verify` 只签发 `.agents/receipts/` 下的凭单，严禁回写胶囊；日常 PR 无需凭单，合入依据用户授权、CI 与评审。
   - **脚本与测试里调用 git 前必须清掉钩子注入的 `GIT_DIR` / `GIT_INDEX_FILE` / `GIT_WORK_TREE` /
     `GIT_COMMON_DIR` / `GIT_OBJECT_DIRECTORY`**：pre-commit 钩子（`gate_runner.sh`）会把这些变量注入
     测试进程，`git -C <临时仓库>` 也会被它们劫持回真实仓库——夹具的裁决会落到真仓库上，曾实际损坏隔离
     工作区索引。判定口径：进程内 `subprocess` 调用 git 一律显式传净化后的 `env`。
6. **专精 Agent Skills 协同规范**：
   - **项目级专精业务 Skills ([`.agents/skills/`](.agents/skills/))**：
     - **`wom-navigator`**：工程态势罗盘与架构调度中枢，响应“当前项目状态和进展”、“下一步推进方向”与“任务指派”，联动 `scripts/project_status.py` 事实源；
     - **`wom-collaborator`**：日常轻量协作入口，指导按变更面验证与按需工作区隔离；显式治理任务才使用胶囊与凭单；
     - **`wom-invariants-guard`**：15 项核心不变量守护者，提供逐项违例判定标准、反模式排查清单与 AST 架构适应度静态扫描；
     - **`wom-domain-weaver`**：纯领域核心业务编织，指导 World/Character/Story 状态机与确定性 Outcome Resolver（纯函数 Reducer 模式）；
     - **`wom-data-steward`**：四库物理隔离管家，指导 SQLite 多模型隔离架构、Transactional Outbox 异步事件与 100% 幂等重建；
     - **`wom-macos-craft`**：macOS 原生客户端极客，指导 SwiftUI 界面交互、Swift 6 严格并发与 `WorldSession` 响应式叙事流消费。
   - **全局通用工程 Skills (`~/.gemini/config/skills/`)**：
     - **Swift 6 并发安全**：使用 `swift-concurrency` 指南消除数据竞态与 actor 隔离问题；
     - **SwiftUI 架构与设计**：使用 `swiftui-expert-skill` 遵循规范的状态与视图分层设计；
     - **Python 异步与测试**：Local Engine 核心开发严格遵守 `async-python-patterns` 与 `python-testing-patterns`；
     - **架构治理与安全重构**：跨模块解耦与深模块设计遵循 `improve-codebase-architecture`；
     - **代码知识图谱智能**：利用 `code-intelligence` 进行高阶 Cypher 查询与调用链路追踪；
     - **现代 Swift 测试**：macOS 客户端测试严格基于 `swift-testing-pro` 宏体系。
7. **文档与 Markdown 链接规范（零绝对路径泄露）**：
   - **相对路径唯一原则**：仓库内所有 Markdown 文档（包括 `docs/`、`README.md`、`AGENTS.md`、`.agents/` 等）中引用内部文件或目录时，**一律只允许使用相对于项目根目录或当前文档的相对路径**（例如：[`docs/README.md`](docs/README.md)、[`docs/05_UI/design_tokens.json`](docs/05_UI/design_tokens.json) 或 [`../01_总体架构/`](../01_总体架构/)）；
   - **严禁绝对路径泄露**：严禁在任何仓库 Markdown 文档中出现或生成开发机本地文件系统的绝对路径或绝对 URI（例如：`file:///Users/...`、`/Users/...`、`/home/...`、`C:\...` 等包含本地用户名或本机盘符的路径），杜绝开发机个人环境隐私泄露，确保文档在不同开发者机器、CI 与 GitHub Web 渲染下的强可移植性；
   - **跨仓库规范引用**：关联外部仓库（如卡牌制作工具 [`hrygo/lotm-card-art`](https://github.com/hrygo/lotm-card-art)）一律使用公开规范的 GitHub 远程 URL，严禁依赖本地跨目录绝对或相对文件路径。
8. **App 运行时测试的进程纪律（单实例 + 测试后无残留）**：
   - **唯一 App 进程**：任何以 macOS App 为被测对象的验证——手工点开验收、集成测试、美术 / 场景运行时取证脚本——
     在同一时刻只允许存在**一个**该 App 实例。`open` 会把请求转交给已在运行的实例；双实例会让 `screencapture`
     抓到另一份拷贝的窗口，并让两份 App 各自拉起一个 Local Engine 子进程同时读写同一份用户数据，证据因此不可信。
   - **探测口径**：按 `<App 名>.app/Contents/MacOS/<可执行文件>` 匹配整个进程表（`ps -Ao pid=,command=` 或
     `pgrep -f`），不按单一绝对路径匹配——`/Applications` 里的同名拷贝与构建产物同时存在，才是「双实例」的真实来源。
   - **不得静默清理不属于本次运行的进程**：启动前发现既有实例即中止并列出 pid，人工退出（⌘Q）后重跑；
     任何清理只针对自己启动、且命令行仍指向该包拷贝的 pid。
   - **测试后必须走到退出断言**：优先正常退出（`osascript -e 'tell application id "<bundle id>" to quit'`），
     超时才 `TERM` 兜底；异常、`Ctrl-C`、`SIGTERM` 也要经 `atexit` / 信号处理走同一条清理路径；结束时仍有残留
     必须报错并保留 pid 证据，不静默放行；同时回收本次写入的临时产物、偏好改动与辅助功能改动。
   - 参照实现：[`docs/05_UI/artwork/tools/capture_scene_runtime_evidence.py`](docs/05_UI/artwork/tools/capture_scene_runtime_evidence.py)
     （`ensure_no_instance` / `launch_app` / `quit_app` / `assert_no_residue` / `install_cleanup_handlers`）。
9. **阻塞问题的尝试预算与及时汇报**：
   - **禁止无差异死磕**：同一阻塞点默认最多进行 **3 轮有实质差异的尝试**；仅重复相同命令、相同参数、相同调用链或无新证据的轮询，不计为新方案，也不应持续执行。
   - **提前停止条件**：若第 1～2 轮已经明确属于外部环境、权限、平台能力、上游服务或缺失输入导致的硬阻塞，应立即停止继续消耗时间与 Token，不必机械尝试到第 3 轮。
   - **达到预算仍未解决必须汇报**：简明给出「当前问题」「已尝试方案及结果」「关键错误/证据」「当前判断」「建议的下一步」；需要人工、本机或额外授权时明确指出，不得把未解决状态包装成已完成。
   - **继续尝试的前提**：只有出现新的证据、新的可行路径或用户明确要求继续深挖时，才在原阻塞点上继续；否则先推进不受该阻塞影响的独立工作，避免单点问题吞噬整个任务预算。
   - **轮询同样受预算约束**：CI、远端任务、外部服务状态不得高频无意义轮询；连续若干次状态无变化时应降低检查频率或先汇报当前状态，而不是用重复查询消耗上下文与 Token。
