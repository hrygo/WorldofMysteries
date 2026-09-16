# Pull Request / Task Handoff Checklist

> 任何人类或 Agent 在提交分支合并或任务交接前，必须严格完成以下逐项自检：

## 1. 基础信息
- **执行角色**: [AGT-ARB / AGT-DOM / AGT-DAT / AGT-AI / AGT-VOX / AGT-MAC / AGT-QA / HUMAN]
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

## 4. 任务胶囊与机器签名凭单 (Task Capsule & Attestation)
- **任务胶囊路径**: `.agents/capsules/<TASK_ID>.json`
- **机器签名校验和**: `sha256:xxxxxxxx` (由 `agent_capsule.py verify` 自动签发)
- [ ] 已确认修改文件 100% 局限在角色授权目录内（未触发 Scope Breach）
- [ ] 胶囊状态已跃迁为 `VERIFIED`

## 5. 本地极速门禁自测证据
在发起 PR 或执行 `collab_pipeline.py integrate` 前，必须通过三阶段门禁：
```bash
# 运行全量三阶段本地门禁
bash scripts/gate_runner.sh

# 或通过胶囊统一验证与签发
rtk python3 scripts/agent_capsule.py verify --capsule .agents/capsules/<TASK_ID>.json
```
- [ ] `check_architecture_fitness.py` PASS (架构适应度零违规)
- [ ] Python `uv run pytest` PASS (25 项测试全绿)
- [ ] Swift `swift test` PASS (8 项并发测试全绿，0 warnings, 0 data races)

## 6. GitHub Actions CI 门禁声明
- [ ] 确保云端 CI (`.github/workflows/ci.yml`) 3 个 Stages 全绿
- [ ] 确保 PR 作用域审计 (`.github/workflows/capsule-audit.yml`) 验证通过
- [ ] 仅允许 Fast-Forward (`--ff-only`) 洁净合流至 `main`
