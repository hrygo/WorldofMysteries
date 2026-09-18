# Pull Request / Task Handoff Checklist

> 任何人类或 Agent 在提交分支合并或任务交接前，必须严格完成以下逐项自检：

## 1. 基础信息
- **执行角色**: [AGT-ARB / AGT-DOM / AGT-DATA / AGT-AI / AGT-VOICE / AGT-MAC / AGT-QA / HUMAN]
- **关联里程碑**: [M0 - M10]
- **所属工作流 (Workstream)**: [WS-CONTRACT / WS-DATA / WS-AI / WS-DOMAIN / WS-PACKAGING / WS-VOICE 等]

## 2. 架构不变量守卫核验 (Invariants Checklist)
- [ ] **不变量 5 (Proposal 唯一性)**: AI 模块绝无直接调用数据库写入操作。
- [ ] **不变量 6 (零知识越界)**: Context 严格经过 Compiler 授权过滤，无泄漏未授权秘密。
- [ ] **不变量 9 (提交即命运)**: Narrative / Audio / UI 重试绝不反向篡改已提交的 StoryState。
- [ ] **不变量 10 (只读 Canon)**: 任何操作绝未尝试写回 `canon.db`。
- [ ] **不变量 12 (App 进程隔离)**: `macos-app/` 仅通过 UDS IPC 通信，无直接 SQLite/DB 引用。

## 3. 契约与跨语言一致性
- [ ] 若改动了数据结构，是否已在 `contracts/schemas/` 优先更新 JSON Schema？
- [ ] 是否已同步生成/更新 Python Pydantic 与 Swift Codable DTO？
- [ ] 是否通过了 `contracts/tests/test_roundtrip.py` 双向一致性测试？

## 4. 任务契约与凭单证据 (Task Capsule & Receipt Evidence)
- **任务契约路径**: `.agents/capsules/<TASK_ID>.json`（不可变，verify 不回写）
- **胶囊摘要**: `sha256:xxxxxxxx`（凭单绑定值）
- **门禁档案**: `gates.profile` = `____`，`gates.profile_digest` = `sha256:xxxxxxxx`
- **Work Receipt**: `.agents/receipts/<TASK_ID>/<head_sha>.json`
- [ ] 已确认修改文件 100% 局限在 `capsule.scope.write` 内（未触发 `SCOPE BREACH`）
- [ ] 若有高风险面改动（`contracts/`、`.hacf/`、`.github/`、`migrations/`、lock/构建文件），已由 AGT-ARB 授予 `privileged_grants` 且 `risk_class >= high`
- [ ] 凭单 `diff_digest` 覆盖当前变更集（与 CI 复算值一致即可；rebase / 合入最新 `main` / 改写提交信息不会使其失效，`head_commit` 仅供追溯）
- [ ] 若本 PR 代码变更**全部**落在 `.github/workflows/`、`.github/dependabot.yml`、`engine/uv.lock`、`macos-app/Package.resolved`，已确认走自动化维护通道（免胶囊与凭单，由 CI 三阶段门禁守门）
- [ ] 凭单 `coverage_gaps` 已知悉（如有）并在评审中说明

## 5. 本地极速门禁自测证据
在发起 PR 或执行 `collab_pipeline.py integrate` 前，必须通过受保护门禁档案：
```bash
# 运行全量三阶段本地门禁（受保护档案 FULL_P0）
bash scripts/gate_runner.sh

# 角色专精档案（可选）：DOMAIN_P0 / DATA_KERNEL_P0 / AI_GATEWAY_P0 / VOICE_P0 / MACOS_APP_P0
bash scripts/gate_runner.sh DOMAIN_P0

# 范围裁决 + 签发 Work Receipt（绝不回写胶囊）
python3 scripts/agent_capsule.py verify --capsule .agents/capsules/<TASK_ID>.json
```
- [ ] `check_architecture_fitness.py` PASS (架构适应度零违规)
- [ ] Python `uv run --locked --extra dev pytest` PASS（0 failed，含 HACF 治理测试）
- [ ] Swift `swift test` PASS（0 failures，0 warnings，0 data races）

> 这里只写判定标准，不写测试条数：条数每次新增用例都会变，写死会立刻过期（以命令退出码与
> `gate_runner.sh` 输出为准）。

> 说明：本地凭单只提供**可复算摘要证据**（非密码学签名）。门禁权威结论以 CI required checks
> （`ci.yml` 三阶段 + `capsule-audit.yml` 证据审计）为准；PR 卡片不宣称测试结论。

## 6. GitHub Actions CI 门禁声明
- [ ] 确保云端 CI (`.github/workflows/ci.yml`) 3 个 Stages 全绿
- [ ] 确保 PR 作用域审计 (`.github/workflows/capsule-audit.yml`) 验证通过
- [ ] 仅允许 Fast-Forward (`--ff-only`) 洁净合流至 `main`
