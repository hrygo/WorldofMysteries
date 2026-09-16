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

## 4. 本机极速门禁自测证据
请在提交前执行并在 PR 中附带以下命令的成功输出：
```bash
./scripts/gate_runner.sh
```
- [ ] `check_architecture_fitness.py` PASS
- [ ] Python `pytest` PASS (0 errors)
- [ ] Swift `swift test` PASS (0 errors, 0 warnings)
