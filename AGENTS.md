# AGENTS.md

> **项目名称**：《诡秘世界》（World of Mysteries）  
> **工程形态**：SwiftUI macOS App (arm64, macOS 26+) + 同机独立 Local Engine Service (Python 3.14.7 CPython standard GIL build + AgentScope 2.0.8)  
> **数据内核**：SQLite 本地多模型架构（`canon.db`, `world.db`, `retrieval.db`, `runtime.db`）  
> **核心规范根目录**：[`docs/`](docs/)（主入口：[`docs/README.md`](docs/README.md)）

---

## 1. 核心架构与系统总览

《诡秘世界》是一套以 Canon 为历史底座、持续世界状态为现实、人物长期身份与记忆为主体、语音驱动互动叙事为主要体验的单人持久世界应用。

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
           Audio / Voice Engine
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
│   ├── schemas/            # *.schema.json (JSON Schema 规范)
│   └── protocol/           # engine_ipc.schema.json 等 IPC 通信协议
├── engine/                  # Local Engine Service (Python 3.14.7 + AgentScope 2.0.8)
│   ├── domain/             # 领域核心：无外部 SDK/DB 依赖纯逻辑 (World, Character, Lore, Story...)
│   ├── application/        # 用例编排、事务管理 (Session Orchestrator, Context Compiler)
│   ├── infrastructure/     # SQLite 持久化、Outbox、IPC 服务端、Asset 存储
│   ├── ai/                 # AgentScope Adapter, Model Router, Prompt Registry
│   └── tests/              # 单元测试与领域测试
├── macos-app/               # macOS 宿主应用 (SwiftUI, macOS 26+, arm64)
│   ├── App/                # 视图与状态管理
│   ├── IPC/                # Engine 进程生命周期、Typed IPC 客户端
│   └── Tests/              # UI 与客户端测试
├── content-pack-tools/      # 设定集校验、打包与验证工具
├── fixtures/                # Golden Scenario 固件 (golden_001 等)
├── scripts/                 # 构建、环境探测与打包脚本
└── docs/                    # 完整设计文档与基线规范
```

### 模块依赖边界约束 (Ownership Boundaries)
- `engine/domain/`：**严禁** import AgentScope、SQLite 驱动（如 sqlite3 / aiosqlite）或任何云厂商 SDK。
- `engine/ai/`：作为适配层接入 AgentScope，但不得直接操作 SQLite 写事务。
- `macos-app/`：**严禁** 依赖 Python 运行时内部类型或直接读取 `world.db`。
- `contracts/`：跨语言交互的唯一协议与 Schema 源头，Swift 与 Python 均由其代码生成或严格校验。

---

## 4. 关键规范参考索引

在进行具体任务前，请优先阅读并严格参照以下设计基线：

| 模块 / 需求 | 规范文档路径 | 核心要点 |
|---|---|---|
| **工程主线门禁** | [`docs/07_工程启动/`](docs/07_工程启动/) | `Go_NoGo_Gates_v1.0.yaml` 规定的 P0 门禁（`GATE-PACKAGE`, `GATE-PROTOCOL`, `GATE-DATA`, `GATE-AI`, `GATE-GOLDEN-MOCK`） |
| **总体架构 & ADR** | [`docs/01_总体架构/`](docs/01_总体架构/) | `ADR-001` (本地引擎拓扑), `ADR-002` (SQLite数据架构), `ADR-003` (AgentScope边界) |
| **领域引擎实现** | [`docs/02_领域引擎/`](docs/02_领域引擎/) | `World`, `Character`, `Story`, `Lore`, `Memory_Knowledge`, `Audio_Voice` 各 Engine 规范 |
| **工程与协议契约** | [`docs/03_工程规范/`](docs/03_工程规范/) | `Context_Compiler`, `Engine_API_Contracts`, `Data_Architecture`, `macOS_App_Platform_Baseline`, `Swift6_Xcode27_Best_Practices`, `Runtime_Orchestration` |
| **回归测试基准** | [`docs/04_Golden_Scenarios/`](docs/04_Golden_Scenarios/) | `golden_001` 5 轮状态断言与端到端期望 |
| **IPC 协议规范** | [`docs/07_工程启动/IPC_Protocol_v1.0.md`](docs/07_工程启动/IPC_Protocol_v1.0.md) | 基于 NDJSON / Typed IPC 的错误恢复与请求应答模型 |

---

## 5. 开发与编码操作准则

1. **环境与运行约束**：
   - 目标架构为 Apple Silicon (macOS 26+ / arm64)。
   - Python 版本锁定为 **3.14.7**（标准 GIL CPython 构建），AgentScope 版本精确锁定为 **2.0.8**。
   - 使用 `uv` 作为 Python 依赖与包管理工具。
2. **终端与测试执行优化**：
   - 终端命令执行遵循 RTK 规则，涉及 git、pytest、cargo 等命令时显式使用 `rtk` 前缀（如 `rtk git status`, `rtk uv run pytest`）。
3. **代码与架构图谱分析**：
   - 涉及符号定义、调用链追踪（Call Graph）或重构影响分析时，优先调用 `codebase-memory-mcp` 工具（项目 ID：`Users-hrygo-Documents-WorldofMysteries`）。
4. **修改协议与 Schema**：
   - 任何对数据结构、IPC 协议的修改必须同步更新 `contracts/` 下的 JSON Schema 与 Pydantic/Swift 对应模型，禁止私自篡改破坏向下兼容性。
