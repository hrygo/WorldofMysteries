# AGENTS.md

> **项目名称**：《诡秘世界》（World of Mysteries）  
> **工程形态**：SwiftUI macOS App (arm64, macOS 26+) + 同机独立 Local Engine Service (Python 3.14.7 CPython standard GIL build + AgentScope 2.0.8)  
> **数据内核**：SQLite 本地多模型四库物理隔离架构（`canon.db`, `world.db`, `retrieval.db`, `runtime.db`）  
> **语音交互**：OpenAI Audio API 规范适配器，默认对接本地 SpeechRail (WebSocket/REST)，支持任意兼容第三方热拔插  
> **协同框架**：HACF 2.1 (人机与多专精 Agent 协同体系，门禁主权 + 契约凭证分离) + GitHub Actions 工业级双层防御流水线  
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
│   └── receipts/           # Work / Integration Receipt (唯一可授权合入的凭证)
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
  覆盖档案后必须由 `AGT-ARB` 执行 `python3 scripts/gate_profile.py refresh-registry` 并附架构评审。
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

## 4. 人机协同研发工作框架 (HACF 2.1)

本项目采用工业级的 **“任务胶囊切片 + 门禁主权 + 事务型并行工作区 + 可复算凭单验收”** 协同模型：

> 摘要为 sha256 **内容摘要**而非密码学签名；抗伪造由受保护分支、CODEOWNERS 评审与 CI 复算共同承担。
> 完整规范见 [`docs/03_工程规范/高效人机协同研发体系实施方案_v1.1.md`](docs/03_工程规范/高效人机协同研发体系实施方案_v1.1.md)
> 与 [`ADR-004`](docs/01_总体架构/ADR-004_协同层门禁主权与凭证分离_v1.0.md)。

### 4.1 7 大专精 Agent 角色矩阵
| 角色代号 | 角色名称 | 核心职责 | 授权管辖目录 |
|:---|:---|:---|:---|
| **`AGT-ARB`** | 架构仲裁者 | 系统拓扑治理、任务派发、扩权审批、冲突仲裁、ADR 决策 | `docs/`, `contracts/`, `scripts/`, `.hacf/`, `.github/`, `.agents/` |
| **`AGT-DOM`** | 领域逻辑编织者 | World, Character, Story 状态机与确定性 Outcome Resolver | `engine/domain/`, `engine/tests/` |
| **`AGT-DATA`** | 数据内核管家 | 四库物理隔离、Outbox 事件发布、迁移脚本与事务队列 | `engine/infrastructure/database*`, `outbox*` |
| **`AGT-AI`** | AI 运行时网关 | AgentScope 2.0.8 适配、Bounded Tools 限制、Prompt 注册表 | `engine/ai/`, `engine/application/` |
| **`AGT-VOICE`** | 语音引擎大师 | OpenAI Audio API 规范适配、SpeechRail 热拔插、指纹缓存 | `engine/domain/audio*`, `infrastructure/audio/` |
| **`AGT-MAC`** | macOS App 极客 | SwiftUI 界面交互、@Observable 数据流、Swift 6 严格并发 | `macos-app/WorldOfMysteries/` |
| **`AGT-QA`** | 自动化质检官 | Golden Scenario 5 轮全景回归、三阶段流水线终审 | `fixtures/`, `engine/tests/`, `macos-app/WorldOfMysteriesTests/` |

> **角色代号是接口**：唯一口径为 `contracts/engineering/task_capsule.schema.json` 的角色枚举 ——
> `AGT-ARB` / `AGT-DOM` / `AGT-DATA` / `AGT-AI` / `AGT-VOICE` / `AGT-MAC` / `AGT-QA`。
> 早期文档里的 `AGT-DAT` / `AGT-VOX` 只是历史别名：`pack --role` 只接受枚举值，写别名会直接 `ValueError`；
> 新增/改名角色必须同时更新枚举、`scripts/agent_capsule.py` 的 `ROLE_DEFAULTS` 与 `.github/CODEOWNERS`。

### 4.2 协同作业标准流程 (SOP)

> **顺序不可颠倒**：`pack`（定基线）→ `start`（隔离工作区）→ 编码并**提交** → `verify`（签发凭单）→
> 凭单作为独立提交带上 → `integrate` / `submit` → **合入后回收工作区**。四条硬规则：
> ① **`target_ref` 是合入目标（默认 `origin/main`），不是当前工作分支**；只有合入目标前进才判定上下文陈旧；
> ② **先提交再验收**：`changes_digest` 取 `base_sha...HEAD` 的**已提交内容**，提交前执行只会得到空摘要；
> ③ `.agents/capsules/` 与 `.agents/receipts/` 不计入摘要（否则「签发凭单 → 提交凭单」会让凭单自我失效），
> 所以凭单必须在验收之后单独提交；
> ④ **合入即回收**：PR 显示 `MERGED` 后立即回收隔离工作区、本地分支与短路径运行时命名空间，
> 不留到「下一个任务开始前」——含独立 `engine/.venv` 的孤立工作区是 GB 级磁盘占用，
> 还会在 `git worktree list` 与 `collab_pipeline.py status` 里长期伪装成活跃工作区。

1. **任务切片派发 (Pack)**：
   ```bash
   python3 scripts/agent_capsule.py pack --role <ROLE> --task-id <TASK_ID> --title "<TITLE>" --focus "<关键词>"
   ```
   *背后深度内聚：只引用受保护门禁档案（`gates.profile` + `profile_digest`），按任务焦点排序 AST 切片，
   记录 `base_sha` / `target_sha` / `context_snapshot`。契约不携带任何验收命令。*
   - **`target_ref` 是合入目标（默认 `origin/main`），不是当前工作分支**：只有合入目标前进才判定上下文陈旧。
     若把特性分支记成目标，提交自己的改动就会触发 `stale_context`、`verify` 永远拒绝签发凭单；
     非默认合入目标用 `--target-ref` 显式指定。
   - `pack` 在 `main` 工作区执行最直观（`start --role --task-id` 的自动 pack 现已采用同一口径）。
2. **并行无锁编码 (Start Worktree)**：
   ```bash
   python3 scripts/collab_pipeline.py start --branch feat/<branch> --role <ROLE> --task-id <TASK_ID>
   ```
   *背后深度内聚：秒级创建隔离目录、**每工作区独立** `engine/.venv`（`uv sync --locked --extra dev`，共享 uv 缓存）、
   资源命名空间租约（TMPDIR / SPM scratch / 测试库 / socket / 端口段）。*
3. **本地验证与凭单 (Verify & Receipt)**：
   ```bash
   # 0. 先提交实质改动：未提交的内容不会进入 changes_digest
   git commit -m "<type>(<scope>): <summary>"
   # 1. 四类边界裁决（read/write/forbidden/privileged）+ 受保护门禁 + 签发 Work Receipt
   python3 scripts/agent_capsule.py verify --capsule .agents/capsules/<TASK_ID>.json --cwd "$(pwd)"
   # 2. 凭单作为独立提交带上（证据文件不计入摘要，不会让凭单失效）
   git add .agents/receipts/<TASK_ID>/ && git commit -m "chore(evidence): attach <TASK_ID> Work Receipt"
   ```
   - **陈旧上下文的处置**：合入目标已前进时，在最新基线上重新 `pack`（生成 `capsule_revision` 修订版）后
     再验收；不要用 `--allow-stale` 绕过，它仅用于调试且会在凭单里留下 `stale_context=true`。
   - **凭单绑定内容摘要，不绑定 commit SHA**：`diff_digest` 与 CI 复算值一致即有效，rebase、合入最新
     `main`、改写提交信息都不会让凭单失效；凭单里的 `head_commit` 仅供追溯。
   - **范围裁决审的是 `base_sha → HEAD` 的完整范围**（已提交内容 + 工作树），不是只看工作树：
     否则「先提交再验收」会让本地范围裁决恒为空集、越界改动只剩 CI 一道防线。
4. **集成预演 (Integrate · 本地)**：
   ```bash
   # 门禁 → expected_main_sha CAS 复核 → 本地 ff 合入 → post-merge smoke → Integration Receipt
   python3 scripts/collab_pipeline.py integrate --branch feat/<branch>
   ```
   *越界或需扩权时退出码 1；高风险面（`contracts/`、`.hacf/`、`.github/`、`migrations/`）须由 `AGT-ARB` 显式 grant。*
   *本地 main 仅作预演：受保护主分支拒绝直接 push，合入必须走 PR。*
5. **提交 PR (Submit)**：
   ```bash
   # 推送分支 → 建（或复用）PR → 可选 auto-merge（必需检查通过后自动合入）
   python3 scripts/collab_pipeline.py submit --branch feat/<branch> --auto-merge
   ```
   *必需检查为 `All Quality Gates Passed` 与 `Capsule Gate`。检查名是公开接口：定义在
   `.hacf/required-checks.json`，由 `scripts/check_required_checks.py` 在 CI 守卫，
   `scripts/sync_branch_protection.py`（默认 dry-run）负责与 ruleset 同步——改名而未同步会让所有 PR 永久 pending。*
   *按改动面收窄本地门禁耗时：`python3 scripts/gate_profile.py resolve` 给出建议档案
   （治理/工具链路径一律全量，纯元数据走最轻档案）。*
   - **维护通道（唯一免胶囊情形）**：当 PR 的代码变更**全部**落在 `.github/workflows/`、
     `.github/dependabot.yml`、`engine/uv.lock`、`macos-app/Package.resolved` 时，`Capsule Gate`
     按自动化维护 PR 放行，不要求胶囊与 Work Receipt（由 CI 三阶段门禁全权守门）。任何其他代码路径
     都必须携带胶囊与凭单；`*.md` 等文档属元数据，不参与代码胶囊判定。
6. **合并后回收 (Cleanup)**：
   ```bash
   # 1. 先证明内容已落地（squash 合入后，分支提交不会出现在 main 历史上）
   gh pr view <branch> --json state,mergedAt,mergeCommit
   # 取 mergeCommit.oid 与本地分支尖端比对：输出为空即该分支内容已全部落在 main
   git diff --stat "<mergeCommit.oid>" "<branch>"
   # 2. 回收本地：工作区（含独立 .venv）+ 本地分支 + /tmp 短命名空间，一条命令三者齐清
   python3 scripts/collab_pipeline.py abort --branch "<branch>"
   # 3. 清掉远端已删除头分支留下的本地引用
   git fetch --prune
   ```
   - **`abort` 是强制回收**：它执行 `git worktree remove --force` 与 `git branch -D`，会丢弃未提交改动与
     未合入提交。动手前确认工作区干净（工作区位于 `../wom-worktrees/<branch-slug>/`，`<branch-slug>`
     是分支名把 `/` 换成 `-`；`git -C ../wom-worktrees/<branch-slug> status --short` 应无输出），
     并以第 1 步的证据确认内容已经落地；证据不足时保留工作区，不做强删。
   - **`git branch --merged` 在本仓库会漏报**：主线走 squash 合入，分支提交不在 `origin/main` 历史上，
     已合入的分支同样不出现在 `--merged` 结果里——靠它判断会把已合入分支当成「未合入」长期留着。
     判定口径只有两条：PR 状态为 `MERGED`，或第 1 步的差分为空。
   - **远端分支不归本地清理**：已合入的远端头分支由仓库的 auto-delete 设置回收，本地只需
     `git fetch --prune` 清掉失效的 `origin/<branch>` 引用；删除仍存在的远端分支属远端状态变更，须单独授权。
   - **只剩本地分支的残留**：工作区已被移除时 `abort` 会直接返回（找不到工作区、不删分支），
     此时按上文证明内容已落地后另行 `git branch -D <branch>`，并核对租约记录的
     `/tmp/wom-ws-<branch-hash>/` 是否已回收。
   - **本地预演路径自带回收，PR 通道没有**：`integrate --auto-clean` 在合入后执行同一套回收
     （工作区 + 分支 + 短命名空间）；走 PR 通道时 `submit` **不做任何回收**，第 6 步是唯一收尾，
     漏掉就会留下孤儿工作区与分支。
   - **收尾自检**：`python3 scripts/collab_pipeline.py status`、`git worktree list`、
     `ls -d /tmp/wom-ws-*` 三处都应只剩活跃任务；已合入的分支不允许停留在任何一处。

---

## 5. GitHub 原生协同与工业级 CI/CD 双层防御体系

工程构建了**本地轻快极速拦截（< 3 秒）**与**云端 GitHub Actions 权威守门（< 1.5 分钟）**的双层防御体系：

```text
本地工作区 (Local)                      GitHub Actions (Cloud CI)
┌───────────────────────────┐         ┌─────────────────────────────────┐
│ collab_pipeline.py        │         │ 1. capsule-audit.yml            │
│ 跑批受保护门禁 + PR 提交   │──Push──>│    核验 PR 未超出 capsule.scope  │
│ 签发摘要凭单 (Receipt)     │         │    门禁档案主权 (目标分支 registry)│
│                           │         │    分级：BLOCKING 才阻断合入      │
└───────────────────────────┘         ├─────────────────────────────────┤
                                      │ 2. ci.yml (3-Stage Gates)       │
                                      │    Stage 1: 架构 AST 检查 & Schema│
                                      │    Stage 2: Python 3.14 (uv 缓存) │
                                      │    Stage 3: Swift 6 + Xcode Build │
                                      ├─────────────────────────────────┤
                                      │ 3. pr-gate-reporter.yml         │
                                      │    只复述凭单事实的证据摘要卡片   │
                                      └─────────────────────────────────┘
                                                       │
                                                       ▼
                                      保护分支主线 (main)：严格 PR 合入（squash / rebase）
```

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
| **人机协同与 CI/CD** | [`docs/03_工程规范/`](docs/03_工程规范/) | [`高效人机协同研发体系实施方案 v1.1`](docs/03_工程规范/高效人机协同研发体系实施方案_v1.1.md)（HACF 2.1 权威基线）, [`GitHub Actions 质检基线`](docs/03_工程规范/GitHub_Actions_流水线与端到端质检基线_v1.0.md), [`GitHub 原生工作流规程`](docs/03_工程规范/GitHub_原生人机协同工作流作业规程_v1.0.md) |
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
   - `verify` 只签发 `.agents/receipts/` 下的凭单，严禁回写胶囊；合入授权以 `Integration Receipt` 为准。
   - **脚本与测试里调用 git 前必须清掉钩子注入的 `GIT_DIR` / `GIT_INDEX_FILE` / `GIT_WORK_TREE` /
     `GIT_COMMON_DIR` / `GIT_OBJECT_DIRECTORY`**：pre-commit 钩子（`gate_runner.sh`）会把这些变量注入
     测试进程，`git -C <临时仓库>` 也会被它们劫持回真实仓库——夹具的裁决会落到真仓库上，曾实际损坏隔离
     工作区索引。判定口径：进程内 `subprocess` 调用 git 一律显式传净化后的 `env`。
6. **专精 Agent Skills 协同规范**：
   - **项目级专精业务 Skills ([`.agents/skills/`](.agents/skills/))**：
     - **`wom-navigator`**：工程态势罗盘与架构调度中枢，响应“当前项目状态和进展”、“下一步推进方向”与“任务指派”，联动 `scripts/project_status.py` 事实源；
     - **`wom-collaborator`**：HACF 2.1 人机协同总枢纽，指导不可变任务契约切片、受保护门禁档案、独立工作区与资源租约、四类范围裁决与仲裁扩权、Work/Integration Receipt 证据链与 GitHub Actions 双层合流；
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
