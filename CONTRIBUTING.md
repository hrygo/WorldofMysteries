# 贡献指南 · Contributing

本项目默认采用 **HACF 轻量模式**：功能分支开发、按改动面验证、PR、CI 与评审。日常任务无需胶囊或凭单；决策见 [ADR-009](docs/01_总体架构/ADR-009_HACF日常流程轻量化.md)，执行约定见 [`AGENTS.md`](AGENTS.md) 第 4 节。

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
- 跨语言数据结构变更必须同步 `contracts/schemas/` 下的 JSON Schema 与 Pydantic / Swift 模型；
- **原著版权红线**：严禁向仓库提交《诡秘之主》原著小说章节全文、大段正文复制、官方动漫影视商业美术或未经授权的有声书音频；仅允许以结构化契约和最简元数据形式进行系统验证（详见 [`NOTICE.md`](NOTICE.md)）。

边界由 `scripts/check_architecture_fitness.py` 静态校验，本地与 CI 都会执行。

## 3. 日常作业流程

1. 明确目标和影响，在功能分支完成一项可评审的功能；允许跨目录同步修改契约、实现和测试。
2. 按改动面运行相关测试，必要时执行完整受保护门禁。
3. 提交 PR，说明结果、验证与实际风险，由 CI 与评审守门。
4. 并行开发或已有工作区不干净时建立独立 worktree 与环境；回收前核对干净和内容落地。

角色表示专长，不能扩大用户授权，也不要求按角色拆 PR。只有明确选择严格治理的任务才采用
旧胶囊 SOP 与 `capsule_audit.py --mode governed`；历史凭证保留供追溯。

## 4. 本地门禁

按改动面选择本地验证；治理、工具链或跨域变更执行全量：

```bash
bash scripts/gate_runner.sh                       # 全量：架构适应度 + pytest + swift test + Xcode App 构建
python3 scripts/gate_profile.py resolve           # 按改动面给出建议档案，避免每轮都跑全量
python3 scripts/gate_profile.py run --profile <ID>
```

云端由 `.github/workflows/` 复跑同一套门禁。main 的必需检查为 `All Quality Gates Passed`
与 `Capsule Gate`，定义在 [`.hacf/required-checks.json`](.hacf/required-checks.json)：
`Capsule Gate` 仅检查门禁配置一致性。检查名是公开接口，由 `scripts/check_required_checks.py` 在 CI 守卫，
`scripts/sync_branch_protection.py`（默认 dry-run）负责与 ruleset 同步。

## 5. 提交与 PR 规范

- 提交信息使用 Conventional Commits：`feat(scope): ...`、`fix(scope): ...`、`docs(scope): ...`、`ci(scope): ...`；
- 一个 PR 解决一个连贯目标，保留用户与他人改动，避免无关重构；
- PR 按 `.github/PULL_REQUEST_TEMPLATE.md` 说明问题、结果、验证和实际风险，无需胶囊摘要或凭单；
- `docs/` 与 `contracts/` 的权威改动需同步更新受影响文档，避免规范漂移。

## 6. 文档与证据

- 规范主入口：[`docs/README.md`](docs/README.md)；
- 文档与实测冲突时以实测为准，并在 PR 中说明差异；
- 时效性结论（版本、服务状态、性能）需标注核实日期。
