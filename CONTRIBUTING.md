# 贡献指南 · Contributing

本项目采用 **HACF 2.0（人机协同研发框架）**：任何改动都以「任务胶囊 + 隔离工作区 + 机器验签 + 双层门禁」的方式进入 `main`。完整规范见 [`AGENTS.md`](AGENTS.md)。

## 1. 环境基线

| 组件 | 版本 |
|---|---|
| macOS | 26+（Apple Silicon arm64） |
| Xcode / Swift | Xcode 27 / Swift 6.4（`MACOSX_DEPLOYMENT_TARGET=26.0`） |
| Python | 3.14.7（标准 GIL CPython） |
| 包管理 | `uv` |
| AI Runtime | AgentScope 2.0.8（lockfile 精确固定） |

## 2. 不可违背的前提

修改前请先阅读 [`AGENTS.md`](AGENTS.md) 第 2 节的 15 条核心不变量。高频红线：

- `engine/domain/` 严禁 import AgentScope、SQLite 驱动或云厂商 SDK；
- `engine/ai/` 严禁直接操作 SQLite 写事务，AI 只能产出 Proposal；
- `macos-app/` 严禁直连数据库，只通过 UDS IPC NDJSON 通信；
- 跨语言数据结构变更必须同步 `contracts/schemas/` 下的 JSON Schema 与 Pydantic / Swift 模型。

边界由 `scripts/check_architecture_fitness.py` 静态校验，本地与 CI 都会执行。

## 3. 标准作业流程 (SOP)

```bash
# 1. 任务切片派发（生成强类型自包含任务胶囊）
python3 scripts/agent_capsule.py pack --role <ROLE> --task-id <TASK_ID> --title "<TITLE>"

# 2. 事务型并行隔离工作区
python3 scripts/collab_pipeline.py start --branch feat/<branch> --role <ROLE> --task-id <TASK_ID>

# 3. 授权范围核验 + sha256 验收签名
python3 scripts/agent_capsule.py verify --capsule .agents/capsules/<TASK_ID>.json

# 4. 跑批门禁并 Fast-Forward 原子合入 main
python3 scripts/collab_pipeline.py integrate --branch feat/<branch> --auto-clean
```

7 大专精角色的职责与授权目录见 [`AGENTS.md`](AGENTS.md) 第 4 节；`.github/CODEOWNERS` 是目录所有权的硬防线。

## 4. 本地门禁

提交前必须本地全绿：

```bash
bash scripts/gate_runner.sh        # Stage 1 架构适应度 + Stage 2 pytest + Stage 3 swift test
```

云端由 `.github/workflows/` 复跑同一套门禁，聚合结论为 `All Quality Gates Passed`。

## 5. 提交与 PR 规范

- 提交信息使用 Conventional Commits：`feat(scope): ...`、`fix(scope): ...`、`docs(scope): ...`、`ci(scope): ...`；
- 一个 PR 只解决一个任务胶囊，禁止超出 `authorized_scope` 的顺带改动；
- PR 必须按 `.github/PULL_REQUEST_TEMPLATE.md` 逐项自检，附上胶囊验签结果与门禁输出；
- `docs/` 与 `contracts/` 的权威改动需同步更新受影响文档，避免规范漂移。

## 6. 文档与证据

- 规范主入口：[`docs/README.md`](docs/README.md)；
- 文档与实测冲突时以实测为准，并在 PR 中说明差异；
- 时效性结论（版本、服务状态、性能）需标注核实日期。
