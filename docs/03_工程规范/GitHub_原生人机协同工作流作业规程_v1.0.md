# GitHub 原生人机协同工作流作业规程 (v1.0)
## —— 基于 Issue 派发、胶囊切片、双层防御与 PR 自动化审查

> **状态**：工程协作 SOP 基线 · 生产就绪  
> **适用对象**：人类架构师、专精 AI Agent（7 大角色）、QA 质检工程师  
> **协作中心**：GitHub Issues (需求派发) + Git Worktree (本地并发) + GitHub Actions (权威守门) + PR Review Card (防伪验签)  

---

## 1. 架构工作流全景图 (End-to-End Workflow)

```text
[人类架构师 / Arbiter]
        │ 1. 提交结构化任务 Issue (选择角色/不变量)
        ▼
┌────────────────────────────────────────────────────────┐
│               GitHub Issues (任务调度中枢)             │
│   .github/ISSUE_TEMPLATE/01_agent_task.yml             │
└───────────────────────────┬────────────────────────────┘
                            │ 2. 认领并启动本地隔离事务
                            ▼
┌────────────────────────────────────────────────────────┐
│            本地开发工作区 (Local Machine)              │
│   rtk python3 scripts/collab_pipeline.py start ...      │
│   rtk python3 scripts/agent_capsule.py pack ...         │
├────────────────────────────────────────────────────────┤
│   - 独立 Git Worktree 无锁并发                         │
│   - 自动符号链接 engine/.venv (零秒就绪)                │
│   - AST 图谱切片提取最小必要符号 (< 500 Token)          │
└───────────────────────────┬────────────────────────────┘
                            │ 3. 编码完毕，本地验收签名
                            ▼
┌────────────────────────────────────────────────────────┐
│         本地机器验收 (Local Verification Gate)         │
│   rtk python3 scripts/agent_capsule.py verify           │
│   - 静态扫描 git diff 防越界修改                       │
│   - 自动执行三阶段本地全量测试                         │
│   - 自动签发 sha256 机器防伪凭单 (Status: VERIFIED)    │
└───────────────────────────┬────────────────────────────┘
                            │ 4. 推送分支并开启 Pull Request
                            ▼
┌────────────────────────────────────────────────────────┐
│             GitHub Actions 云端双层防线                │
├────────────────────────────────────────────────────────┤
│ 1. capsule-audit.yml: 权限边界硬核阻断与防伪验签       │
│ 2. ci.yml: 3-Stage 全量自动化流水线 (Ubuntu & macOS M1) │
│ 3. pr-gate-reporter.yml: 自动生成 PR 审查报告卡片      │
└───────────────────────────┬────────────────────────────┘
                            │ 5. 保护分支规则核验通过
                            ▼
┌────────────────────────────────────────────────────────┐
│               主分支 main (绝对绿色演进)               │
│          仅允许 Fast-Forward (--ff-only) 洁净合流       │
└────────────────────────────────────────────────────────┘
```

---

## 2. 标准作业程序 (SOP: Step-by-Step Guide)

### 第一步：需求发布与任务指派 (Task Dispatch)
1. 访问 GitHub 仓库的 **Issues -> New Issue**；
2. 选择 **🤖 Agent 研发任务派发 (Agent Task Dispatch)**；
3. 选择承接角色（如 `AGT-DOM`）、填写唯一任务 ID（如 `M2-DATA-KERNEL`）、关联里程碑，并勾选必须遵守的架构不变量；
4. 提交后，该 Issue 将自动打上 `agent-task` 标签并指派给对应 Owner。

### 第二步：本地工作区拉起与胶囊切片 (Workspace Setup)
开发者或 Agent 在本地终端执行一条命令拉起完全隔离的并发环境：
```bash
# 秒级拉起独立 Worktree，并自动为角色切片生成初始 Task Capsule
rtk python3 scripts/collab_pipeline.py start \
    --branch feat/m2-data-kernel \
    --role AGT-DOM \
    --task-id M2-DATA-KERNEL \
    --title "四库 SQLite 数据内核迁移与连接池实现"
```
**系统将在后台自动完成**：
- 在 `../wom-worktrees/feat-m2-data-kernel` 建立隔离目录；
- 建立软链接共享主项目的 `engine/.venv`；
- 调用 AST 静态分析，提取当前角色授权目录中的核心类与函数符号；
- 生成标准化胶囊文件 `.agents/capsules/M2-DATA-KERNEL.json`。

### 第三步：专注开发与无死锁编码 (Coding)
切入独立工作区进行开发：
```bash
cd /Users/hrygo/Documents/wom-worktrees/feat-m2-data-kernel
```
- **核心准则**：严格在角色的授权目录内编码；严禁触碰 `forbidden_patterns` 定义的文件；
- 所有的修改完全发生在独立工作区，不影响主仓库或其他并发工作区。

### 第四步：本地验证与机器签名验收 (Verification & Signing)
编码完成后，执行本地验收：
```bash
# 验证修改范围，跑批角色专精门禁，并签发防伪签名
rtk python3 scripts/agent_capsule.py verify --capsule .agents/capsules/M2-DATA-KERNEL.json
```
- **静态范围审计**：若有任何文件超出角色的 `authorized_scope`，立即警告或阻断；
- **全量门禁跑批**：自动执行架构 AST 检查与专精单测；
- **签发机器凭单**：全部通过后，胶囊状态跃迁为 `VERIFIED`，并追加时间戳与 `sha256:xxxx` 机器防伪签名。

### 第五步：发起 PR 与 GitHub Actions 自动化审查 (PR Review)
将特性分支推送到 GitHub 并创建 Pull Request：
```bash
git push origin feat/m2-data-kernel
```
- **PR 模板自动填充**：填写 PR 模板，勾选不变量自检项，贴入胶囊签名；
- **GitHub Actions 自动审查卡片**：
  - 云端 `capsule-audit` 验证签名有效性并检查 diff；
  - 云端 `ci.yml` 在 `macos-14` (Apple Silicon) 与 `ubuntu-latest` 运行跨语言全量矩阵测试；
  - `pr-gate-reporter` 自动在 PR 发表/更新实时质检报告卡片。

### 第六步：Fast-Forward 原子合流与自愈清理 (Integration & Teardown)
当云端 CI 全部打上绿色勾（`All Quality Gates Passed`），执行原子合流：
```bash
# 方式 A：通过本地流水线一键合入并自愈清理
rtk python3 scripts/collab_pipeline.py integrate --branch feat/m2-data-kernel --auto-clean

# 方式 B：在 GitHub Web 界面点击 "Rebase and merge" 或 "Squash and merge"
```

---

## 3. 7 大专精 Agent 角色协作矩阵与 CODEOWNERS 映射

| 角色代号 | 角色中文名 | 授权管辖核心目录 | CODEOWNERS 责任人 | 强绑定核心不变量 |
|:---|:---|:---|:---|:---|
| **`AGT-ARB`** | 架构仲裁者 | `docs/`, `contracts/schemas/`, `scripts/` | `@hrygo` | 全部 15 项不变量守卫 |
| **`AGT-DOM`** | 领域逻辑编织者 | `engine/domain/`, `engine/tests/` | `@hrygo` | #1, #2, #4, #5, #6, #8, #9 |
| **`AGT-DATA`** | 数据内核管家 | `engine/infrastructure/database*`, `outbox*` | `@hrygo` | #3, #10 (只读 Canon), #11 (权威与投影分离) |
| **`AGT-AI`** | AI 运行时网关 | `engine/ai/`, `engine/application/` | `@hrygo` | #5 (仅产出 Proposal), #6, #7, #8 |
| **`AGT-VOICE`** | 语音引擎大师 | `engine/domain/audio*`, `infrastructure/audio/` | `@hrygo` | #9 (提交即命运), OpenAI SDK 对接 |
| **`AGT-MAC`** | macOS App 极客 | `macos-app/WorldOfMysteries/` | `@hrygo` | #12 (App 零直连 DB, 纯 UDS 通信) |
| **`AGT-QA`** | 自动化质检官 | `fixtures/golden_001/`, 全部测试套件 | `@hrygo` | 负责三阶段门禁终审与 Golden Scenario |

---

## 4. 总结

通过 GitHub 原生生态（Issue Forms、CODEOWNERS、PR Sticky Reports、Branch Protection）与本地深工具（`AgentCapsule` + `CollabPipeline`）的无缝接合，我们实现了：
1. **任务声明即代码 (Task as Code)**：所有任务均有类型化胶囊与机器签名；
2. **上下文零稀释 (Zero Dilution)**：AST 局部精准切片，彻底消除长上下文遗忘；
3. **架构防线坚不可摧 (Dual-Layer Defense)**：本地拦截 + 云端权威，保障 15 项核心不变量永不退化。
