---
name: wom-navigator
description: >-
  《诡秘世界》工程态势罗盘与架构调度中枢技能。当用户询问“当前项目状态和进展”、“下一步应该推进的方向”
  或“下面应该给谁派发任务”时使用此技能。提供精确的事实源查询、关键路径依赖分析与任务胶囊一键派发。
---

# 《诡秘世界》工程态势罗盘与调度导航技能 (wom-navigator)

本技能为人类架构师与主控 Agent 提供实时的工程态势感知、科学的演进路线决策与自动化的任务派发凭单。

---

## 1. 核心指令映射与作业流

当收到用户的宏观三连问时，严格依据 `scripts/project_status.py` 与 `docs/PROJECT_STATE.json` 事实源作答，严禁脑补推测：

| 用户意图 / 问询 | 执行动作 | 底层事实依据 | 输出规范 |
|:---|:---|:---|:---|
| **“当前项目状态和进展”** | `rtk python3 scripts/project_status.py status` | `docs/PROJECT_STATE.json` (`current_phase`, `gates_health`) | 呈现当前运行阶段、已完成里程碑、质量门禁现状（AST/Python/Swift） |
| **“下一步应该推进的方向”** | `rtk python3 scripts/project_status.py next` | `docs/PROJECT_STATE.json` (`critical_path`) | 呈现下一推进目标、科学依赖论证、硬性交付物列表与预定专精角色 |
| **“下面应该给谁派发任务”** | `rtk python3 scripts/project_status.py dispatch` | `docs/PROJECT_STATE.json` (`critical_path.dispatch`) | 呈现目标角色代号、授权目录、禁触红线及一键切片/隔离启动命令 |

---

## 2. 状态推进与事实源自愈维护

当一个专精角色完成任务并合入 `main` 后，执行以下步骤维护工程罗盘事实源：

1. **更新里程碑状态**：
   在 `docs/PROJECT_STATE.json` 中将已完成的 Milestone 标记为 `COMPLETED`，更新 `completed_phases` 与关键路径指针；
2. **运行全量回归验证**：
   ```bash
   rtk bash scripts/gate_runner.sh
   ```
3. **核查态势输出**：
   ```bash
   rtk python3 scripts/project_status.py status
   ```
