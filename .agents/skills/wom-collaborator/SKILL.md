---
name: wom-collaborator
description: >-
  《诡秘世界》HACF 2.0 人机协同研发核心驱动技能。指导多专精 Agent 与人类架构师执行任务切片（AgentCapsule）、
  事务型并行隔离工作区（CollabPipeline）、本地三阶段门禁验证、sha256 机器验签与 GitHub Actions 2026 双层防御合流。
---

# 《诡秘世界》HACF 2.0 人机协同研发核心技能 (wom-collaborator)

本技能为所有参与《诡秘世界》（World of Mysteries）开发的人类架构师与专精 AI Agent 提供标准化的协同推进作业指引。

---

## 1. 核心协同理念：深接缝与零上下文稀释

在本项目中，多 Agent 协作**严禁**直接将全量 Markdown 规范与全量代码库无脑复制粘贴给 Agent（防范 Context Dilution）。
必须通过**“强类型任务胶囊（Task Capsule）+ 局部 AST 图谱切片 + 事务型 Git Worktree”**的闭环机制运转。

```text
[任务声明] -> [agent_capsule pack (AST切片)] -> [collab_pipeline start (隔离开发)] -> [agent_capsule verify (防伪签名)] -> [GitHub Actions 权威审验]
```

---

## 2. 7 大专精 Agent 角色与职责边界

在承接或派发任务前，必须准确识别当前执行角色：

| 角色代号 | 角色中文名 | 核心职责 | 授权管辖目录 (Authorized Scope) | 严禁触碰禁区 (Forbidden) |
|:---|:---|:---|:---|:---|
| **`AGT-ARB`** | 架构仲裁者 | 架构拓扑治理、任务切片派发、ADR 决策 | `docs/`, `contracts/schemas/`, `scripts/` | 破坏 15 项核心不变量 |
| **`AGT-DOM`** | 领域逻辑编织者 | 纯领域引擎、状态机、确定性 Outcome Resolver | `engine/domain/`, `engine/tests/` | import SQLite, AgentScope, 云 SDK |
| **`AGT-DATA`** | 数据内核管家 | 四库物理隔离、Outbox 消息箱、连接池与迁移 | `engine/infrastructure/database*`, `outbox*` | 写 `canon.db`，污染 Domain 核心 |
| **`AGT-AI`** | AI 运行时网关 | AgentScope 2.0.8 适配、模型网关、Prompt 模板 | `engine/ai/`, `engine/application/` | 直接执行 SQL 写事务，越界召唤 |
| **`AGT-VOICE`** | 语音引擎大师 | OpenAI Audio API 规范适配、SpeechRail 热拔插 | `engine/domain/audio*`, `infrastructure/audio/` | 反向篡改已提交 StoryState |
| **`AGT-MAC`** | macOS App 极客 | SwiftUI 界面、@Observable 状态、Swift 6 并发 | `macos-app/WorldOfMysteries/` | 直接读写 SQLite 数据库 |
| **`AGT-QA`** | 自动化质检官 | Golden Scenario 5 轮全景回归、三阶段门禁终审 | `fixtures/`, `engine/tests/`, `macos-appTests/` | 绕过门禁弱化断言 |

---

## 3. 标准协作作业流程 (SOP)

### 步骤 1: 任务胶囊切片 (Task Slicing)
人类架构师或 `AGT-ARB` 通过命令行生成自包含任务胶囊：
```bash
rtk python3 scripts/agent_capsule.py pack \
    --role <ROLE_ID> \
    --task-id <TASK_ID> \
    --title "<TASK_TITLE>"
```
- 胶囊自动保存在 `.agents/capsules/<TASK_ID>.json`；
- 脚本自动通过 AST 扫描，仅抓取目标目录的核心符号（< 500 Token），防止上下文膨胀。

### 步骤 2: 开启无锁并行开发事务 (Start Worktree)
为任务拉起完全独立的 Git Worktree：
```bash
rtk python3 scripts/collab_pipeline.py start \
    --branch feat/<branch_name> \
    --role <ROLE_ID> \
    --task-id <TASK_ID>
```
- 系统将在 `../wom-worktrees/feat-<branch_name>` 瞬间初始化隔离工作区；
- 自动建立 `engine/.venv` 符号链接，零秒就绪，共享依赖，零磁盘浪费；
- 开发者/Agent 切换至该目录即可专心编码。

### 步骤 3: 本地验证与机器防伪签名 (Verify & Attest)
编码完成后，在提交前必须执行机器验收：
```bash
rtk python3 scripts/agent_capsule.py verify --capsule .agents/capsules/<TASK_ID>.json
```
- **静态范围审计**：扫描 `git diff`，若出现超出该角色授权目录的文件直接报警；
- **专精门禁跑批**：自动运行当前角色绑定的架构适应度检查与专精单测；
- **签发凭证**：通过后胶囊状态跃迁为 `VERIFIED`，自动写入带时间戳的 `sha256` 机器防伪签名。

### 步骤 4: 云端 CI 权威验证与 Fast-Forward 合流 (Integrate)
推送分支并发起 PR 后，GitHub Actions 将执行权威复验：
1. `capsule-audit.yml` 自动校验 PR diff 范围与胶囊机器签名；
2. `ci.yml` 在 `macos-14` (Apple Silicon) 与 `ubuntu-latest` 运行全量三阶段测试；
3. `pr-gate-reporter.yml` 自动在 PR 发表/更新实时质量报告卡片；
4. 测试全绿后，执行原子合流并自愈清理环境：
```bash
rtk python3 scripts/collab_pipeline.py integrate --branch feat/<branch_name> --auto-clean
```

---

## 4. 终端执行最佳准则
- 终端命令执行必须优先使用 `rtk` 前缀（`rtk git ...`, `rtk uv run ...`, `rtk swift ...`），以压缩 60%-90% 的终端输出，保护上下文窗口。
- 严禁绕过 `scripts/gate_runner.sh` 强行合并代码。
