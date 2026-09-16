---
name: wom-collaborator
description: >-
  《诡秘世界》HACF 2.1 人机协同研发核心驱动技能。指导多专精 Agent 与人类架构师执行任务切片（AgentCapsule）、
  事务型并行隔离工作区（CollabPipeline + 资源命名空间租约）、受保护门禁档案（Gate Profile）、
  范围裁决与仲裁扩权、Work/Integration Receipt 证据链与 GitHub Actions 双层防御合流。
---

# 《诡秘世界》HACF 2.1 人机协同研发核心技能 (wom-collaborator)

本技能为所有参与《诡秘世界》（World of Mysteries）开发的人类架构师与专精 AI Agent 提供标准化的协同推进作业指引。

> **版本**：HACF 2.1（2026-09-16 起）。决策依据
> [`ADR-004`](../../../docs/01_总体架构/ADR-004_协同层门禁主权与凭证分离_v1.0.md)、
> 实施方案 [`v1.1`](../../../docs/03_工程规范/高效人机协同研发体系实施方案_v1.1.md)。
> 已废除的 2.0 机制：共享 `.venv` 软链、胶囊携带验收命令、向胶囊回写签名、`forbidden_patterns` 空转。

---

## 1. 五条不可违背的协同原则

1. **门禁主权**：验收命令只存在于 `.hacf/gates/*.json`（受保护，摘要记录于 `registry.json`）。
   胶囊只引用 `gates.profile` 与 `gates.profile_digest`，任务**不得**自带验收命令。
2. **契约与凭证分离**：`.agents/capsules/*.json` 是不可变契约，任何 `verify` 都不得回写它；
   验收结果单独落盘为 `.agents/receipts/<TASK_ID>/<head_sha>.json`。
3. **内容隔离**：每个 Worktree 使用**独立** `engine/.venv`（`uv sync --locked --extra dev`）；
   严禁软链主仓 venv（会让 editable `.pth` 被跨工作区重写）。
4. **资源隔离**：源码隔离由 `git worktree` 提供，运行时隔离由 `.hacf/workspace.json` 租约提供
   （TMPDIR / SPM scratch / 测试库 / IPC socket / 端口段）。
5. **证据优先于叙述**：摘要为 sha256 内容摘要而非密码学签名；
   门禁结论只来自 CI required checks，任何报告卡片不得宣称未经复算的通过状态。

---

## 2. 7 大专精 Agent 角色与边界

| 角色代号 | 角色中文名 | 授权写域（write） | 高风险面告警 |
|:---|:---|:---|:---|
| **`AGT-ARB`** | 架构仲裁者 | `docs/`, `contracts/`, `scripts/`, `.hacf/`, `.github/`, `.agents/` | 唯一可改门禁档案与 registry 的角色 |
| **`AGT-DOM`** | 领域逻辑编织者 | `engine/domain/`, `engine/tests/` | 禁止 import SQLite / AgentScope / 云 SDK |
| **`AGT-DATA`** | 数据内核管家 | `engine/infrastructure/`, `engine/tests/` | 迁移文件需仲裁扩权；`canon.db` 只读 |
| **`AGT-AI`** | AI 运行时网关 | `engine/ai/`, `engine/application/`, `engine/tests/` | 禁止直接写库事务 |
| **`AGT-VOICE`** | 语音引擎大师 | `engine/domain/audio_voice.py`, `engine/infrastructure/audio/`, 音频测试 | 禁止反向篡改已提交 StoryState |
| **`AGT-MAC`** | macOS App 极客 | `macos-app/WorldOfMysteries/`, `.../WorldOfMysteriesTests/` | 禁止直连数据库、禁止改 `engine/**` |
| **`AGT-QA`** | 自动化质检官 | `engine/tests/`, `macos-app/WorldOfMysteriesTests/`, `fixtures/golden_001/` | 只写断言，禁止改实现 |

**高风险面（非 ARB 均需显式 grant）**：`contracts/`、`.hacf/`、`.github/`、`engine/**/migrations/`，
以及 `uv.lock`、`pyproject.toml`、`Package.swift`、`project.pbxproj` 等构建与工具链面。
触碰时 `risk_class` 至少为 `high`。

---

## 3. 标准作业流程 (SOP)

### 步骤 1：任务切片（不可变契约）
```bash
python3 scripts/agent_capsule.py pack \
    --role <ROLE_ID> --task-id <TASK_ID> --title "<TASK_TITLE>" \
    --focus "关键词1,关键词2"          # 可选：按任务焦点排序 AST 切片
```
- 产物 `.agents/capsules/<TASK_ID>.json`，含 `base`（base_sha / target_sha / context_snapshot）、
  `scope`（read/write/forbidden/privileged_grants）、`gates`（profile + digest）、`context`、`acceptance`；
- 需要触碰高风险面时追加 `--grant-privileged "<glob>" --risk-class high`（扩权将随 PR 进入评审）。

### 步骤 2：开启隔离工作区
```bash
python3 scripts/collab_pipeline.py start \
    --branch feat/<branch> --role <ROLE_ID> --task-id <TASK_ID>
```
- 工作区位于 `../wom-worktrees/<branch>`，自动创建独立 `.venv` 与资源租约
  （`start --skip-venv` 仅用于不跑 Python 门禁的场景）；
- 切换目录后先 `python3 scripts/agent_capsule.py show --capsule ...` 复核边界与切片。

### 步骤 3：本地门禁
```bash
bash scripts/gate_runner.sh              # 默认 FULL_P0（全量三阶段）
bash scripts/gate_runner.sh DOMAIN_P0    # 角色专精档案（按需）
```
档案清单：`FULL_P0` / `DOMAIN_P0` / `DATA_KERNEL_P0` / `AI_GATEWAY_P0` / `VOICE_P0` / `MACOS_APP_P0`。

### 步骤 4：范围裁决与签发 Work Receipt
```bash
python3 scripts/agent_capsule.py verify \
    --capsule .agents/capsules/<TASK_ID>.json --cwd "$(pwd)"
```
- 依次执行：上下文陈旧性校验 → 四类边界裁决（violation / escalation）→ 受保护门禁 → 签发凭单；
- 越界或需扩权时退出码 1，并记录失败凭单；**胶囊不会被修改**；
- 目标分支已前进时判定 `stale_context` 并拒绝（除非 `--allow-stale` 调试）。

### 步骤 5：集成与合入
```bash
python3 scripts/collab_pipeline.py integrate --branch feat/<branch> --auto-clean
```
- 顺序：工作区门禁 → `expected_main_sha` compare-and-swap 复核 → `--ff-only` 合入 →
  post-merge smoke → 签发 `Integration Receipt`（唯一可授权合入的凭证）→ 清理工作区与分支；
- 合入前后目标分支不一致时必须 rebase 并重跑，不得绕过。

### 步骤 6：云端权威守门
1. `capsule-audit.yml`：边界裁决 + 门禁档案主权（以目标分支 registry 为权威）+ 凭单证据完整性；
2. `ci.yml`：架构适应度 / Pytest（`--locked`）/ Swift 6 三阶段；
3. `pr-gate-reporter.yml`：只复述凭单事实的证据摘要卡片；
4. 代码类 PR 无胶囊或无凭单将被阻断（文档类变更按元数据处理）。

---

## 4. 常见反模式（触发即返工）

| 反模式 | 后果 |
|:---|:---|
| 在 `verify` 前手改 `.agents/capsules/*.json` | 凭单 `capsule_digest` 不匹配，CI 拒绝合入 |
| 把命令写进胶囊或让 `true` 充当验收 | 已被移除该字段；命令主权在受保护档案 |
| 用符号链接共享主仓 `.venv` | 环境写入竞争，跨工作区污染 |
| 在 Worktree 内改 `contracts/`、`.hacf/`、`migrations/` 而不扩权 | `SCOPE_ESCALATION_REQUIRED`，凭单判失败 |
| 直接 `git merge` 绕过 `integrate` | 失去 CAS 复核、post-merge smoke 与合入凭单 |
| 把本地日志/压缩输出当作机器证据 | 证据层只认退出码、原始输出摘要与凭单 |

---

## 5. 终端执行准则

- 本机命令遵循 RTK 路由规则（`rtk git ...`、`rtk uv run ...`）；持久化产物与 CI 中使用可移植原生命令；
- 严禁绕过 `scripts/gate_runner.sh`（受保护档案执行器）强行合并代码；
- 门禁档案变更必须由 `AGT-ARB` 执行 `python3 scripts/gate_profile.py refresh-registry` 并附架构评审。
