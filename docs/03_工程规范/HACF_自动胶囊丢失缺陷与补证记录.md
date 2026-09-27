# HACF 自动胶囊丢失缺陷与补证记录

> 记录时间：2026-09-27  
> 记录人：AGT-ARB  
> 触发场景：固定五轮迭代 T0–T7 收口后创建 PR 时，本地 `scripts/capsule_audit.py` 预演判 11 条 BLOCKING  
> 结论性质：**流程缺陷已从源码确认**，非执行者疏忽

## 1. 现象

以 `origin/main..HEAD`（109 文件 / 50 提交）为变更集运行本地 Capsule 审计：

```bash
python3 scripts/capsule_audit.py --base-ref origin/main --head-ref HEAD
```

判定 **FAIL**，11 条 `[BLOCKING] 越界`，全部落在三个目录：

- `engine/ai/`（2 个文件）
- `engine/application/`（8 个文件）
- `engine/infrastructure/migrations/`（1 个文件）

`main` 存在 `main-protection` ruleset，`Capsule Gate` 为必需检查，故该 PR 无法合入。

## 2. 根因（源码级确认）

不是这 4 个任务越权，而是**自动 pack 的胶囊在结构上注定无法进入提交**。三个环节串联：

| 环节 | 位置 | 行为 |
|---|---|---|
| ① 自动 pack | `scripts/collab_pipeline.py:226` | `start --role --task-id` 在工作区执行 `agent_capsule.py pack`，生成 `.agents/capsules/<TASK>.json`；**全脚本无任何 `git add`**，该文件是未跟踪状态 |
| ② 合入门禁放行 | `scripts/collab_pipeline.py:274-284` | 脏检查**显式排除** `.agents/capsules/`、`.agents/receipts/`、`.hacf/`，未提交胶囊不阻塞 integrate；合入只取已提交内容 |
| ③ 工作区回收 | `scripts/collab_pipeline.py:404-412` | `integrate --auto-clean` 执行 `git worktree remove --force`，未跟踪胶囊随工作区一并销毁 |

因此：**除非执行者在编码期间手动 `git add .agents/capsules/<TASK>.json` 并提交，胶囊必然丢失**，而流程对此没有任何提示或校验。

### 与既有摩擦的关系

台账 `.hacf/tmp/B-GOLDEN-ITERATION-progress.md` 已记录过同源摩擦：`pack` 在 main 工作区生成的未跟踪胶囊与分支跟踪的同名文件（仅 `title`/`created_at` 元数据不同）导致 fast-forward 被拒，需 `mv` 走。两次症状不同、成因同源：**胶囊的落盘责任被默认推给执行者，但 SOP 未把它列为必做步骤**。

## 3. 受影响任务清单

以下 4 个任务的 Work Receipt、门禁日志、`scope_audit` 均在仓库且干净通过，**唯独胶囊 JSON 从未提交**（`git log --all --diff-filter=AD` 全历史查无此文件）：

| 任务 | 角色 | Receipt 判定 | 授权写域（据 receipt `scope_audit`） |
|---|---|---|---|
| `B-FIVE-TURN-APPLICATION` | AGT-AI | `passed`，`violations: []` | `engine/ai/`、`engine/application/`、`engine/tests/` |
| `B-PER-TURN-ADVICE` | AGT-AI | `passed`，`violations: []` | `engine/application/`、`engine/tests/` |
| `B-MEMORY-RECALL` | AGT-AI | `passed`，`violations: []` | `engine/application/`、`engine/tests/` |
| `B-MEMORY-READ` | AGT-DATA | `passed`，`violations: []` | `engine/infrastructure/`、`engine/tests/` |

### 授权范围与角色矩阵的一致性核验

对照 `scripts/agent_capsule.py` 的 `ROLE_DEFAULTS`：

- `AGT-AI.write = ["engine/ai/", "engine/application/", "engine/tests/"]`
- `AGT-DATA.write = ["engine/infrastructure/", "engine/tests/"]`

与上述 4 枚胶囊 receipt 记录的写域**逐一吻合**，也与 `AGENTS.md` §4.1 所有权矩阵一致。即：这 4 个任务的授权本身正确，缺的只是凭证载体。

## 4. 补证方案与代价

### 方案 A（已采纳）：按原角色重新 pack + verify

对这 4 个任务以原角色重新执行 `pack` + `verify`，产出绑定当前 diff 的凭单，使 Capsule Gate 恢复覆盖。

**必须明确的代价：**

1. `capsule_digest` 是胶囊文件的 sha256（`hacf_policy.py:207-208`）。新 pack 的文件因 `created_at`、`base_sha`、`context_snapshot` 不同，摘要**必然不等于**旧 receipt 记录的 `bfdb395f…` / `ee0812c8…` / `44f9c68f…` / `dbe5bde5…`。
2. 审计对 `capsule_digest` 不一致判为 **ADVISORY（`hard=False`，不阻断）**（`capsule_audit.py:240-244`），因此 Gate 可通过，但凭据链上会留下这一处显式不匹配。
3. 性质上这是**用今天的范围声明追认昨天的提交**，属于事后补证，不是"找回原件"。原件已随工作区销毁，不可恢复。

**为什么仍判定为可接受：** 补出的范围与 `ROLE_DEFAULTS` 及原 receipt 记录完全一致，未发生任何扩权；且 4 个任务的门禁日志与范围裁决证据均真实存在且干净。补证恢复的是**授权链的完整性**，不掩盖任何事实。

### 已否决的替代方案

- **照现状推 PR 让 CI 失败**：Gate 判 BLOCKING 时 PR 同样无法合入，终点仍回到方案 A 或 C，只多一轮 CI 反馈。
- **手工伪造胶囊文件**：越过 `pack` 工具直接构造治理凭证，不可接受。

## 5. 待修流程缺陷（另开胶囊）

`integrate --auto-clean` 丢弃未跟踪胶囊这一缺陷**尚未修复**，后续任务仍会重演。建议在 `scripts/` 写域另开 AGT-ARB 胶囊，至少实现其一：

1. `integrate` 在 auto-clean 前检查工作区是否存在未跟踪胶囊，存在则拒绝回收并提示；或
2. `start` 自动 pack 后立即 `git add` 该胶囊，使其进入版本控制；或
3. `integrate` 合入前把工作区胶囊强制提交为独立 commit。

在修复前，执行者须手动提交 `.agents/capsules/<TASK>.json`，此点应补入 SOP。

## 6. 证据边界

本记录只说明**治理凭证链的补证过程与流程缺陷**。代码正确性由各任务自身的门禁凭单证明（T7 收口见 `docs/06_实施基线/2026-09-27_Golden_Five_Turn_GUI_Observation_Record.md`，绑定 `f72f379`），本记录不重复也不替代该证据。
