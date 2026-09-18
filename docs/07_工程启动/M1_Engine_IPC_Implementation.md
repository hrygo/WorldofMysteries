# M1 IPC foundation — implementation ledger

Task: `M1-IPC-FOUNDATION`. Refs #43, #44, #45. Base: `main@501d46fa3a6262b0ed501d96807377c3a13a50e4`.

## Approved boundary

The user approved strict contract unification and a dedicated parent-child credential pipe, conditional on no additional end-user configuration, account, network dependency, cost or permission steps. This is not approval of automatic merge or of new gameplay/engine decisions. Preserve committed world facts. The scope of this coordinated prerequisite is recorded in its new capsule; no existing capsule or protected gate is modified.

## Increment 1 — contract

- Canonical schema in `contracts/protocol/`; documentation path is a reference only.
- Request/response/event shapes, structured errors, identifiers and nonnegative stream sequence/revision are enforced in Schema, Python and Swift.
- Error and success payloads are exclusive; absent optional fields are omitted instead of sent as null.
- Shared positive/negative fixture corpus drives Python and Swift tests. Preview constructors remain source-compatible, but malformed values cannot be encoded or decoded on the wire.
- Handshake payload declares the private, per-launch credential; no credential value is logged.

## Evidence at this increment

- 112 focused Python/contract tests passed on Python 3.13.5 in the Linux workspace (not the locked Python 3.14.7 environment).
- 92 corpus decisions passed using the actual production Swift envelope compiled with Swift 6.2.1; accepted Swift output was revalidated against Schema and Pydantic.
- Architecture static checks and capsule schema passed.
- This does not claim full SwiftUI/Xcode tests, target Mac performance, packaging, real service implementation, Golden 001 or database persistence.

## Increment 2 — real system transport

- Added a real independent UDS server, private bootstrap pipe and per-connection authentication.
- System health reports transport readiness separately from unavailable world/model/voice capability; unknown methods fail closed.
- Bounded framing, strict JSON, fragmented/coalesced input, correlated FIFO replies and concurrent clients.
- Private runtime/socket permissions, exclusive startup lease, confirmed stale-socket recovery and inode-checked cleanup.
- Normal shutdown, signal shutdown with active/partial clients, crash/restart and old-token rejection have actual subprocess tests.
- Aligned integral JSON numbers and handshake constraints across the contract models. The shared corpus now has 94 cases; numeric wire spellings are tested without pre-normalization.
- Initial macOS CI found an empty-payload compatibility regression in the existing Artifact adapter test. Empty objects now remain absent typed business results; malformed nonempty payloads still fail. The existing test is unchanged and a focused regression test was added.

### Local evidence

189 focused Python/contract/transport assertions passed on Python 3.13.5/Linux, including real independent-process tests. The 94-case production Swift codec/reverse roundtrip and the empty-payload regression probe passed with Swift 6.2.1/Linux. These are not the pinned full runtime or target App acceptance. The initial commit's Capsule Gate and Python CI passed; its Swift test failure motivated the compatibility fix. New-head CI must be read separately.

### Remaining product integration

App lifecycle integration, signed bundled Python, automatic first-run/reconnect on the target Mac, real story handlers and persistence remain subsequent tasks. No new user operations are added by the internal design, but end-user-invisible startup/performance has not been accepted. Keep #43–#45 open. No merge is authorized.

## PR #50 · 报告证据链修复增量（2026-09-18）

用户要求将自动报告的根因修复追加到同一个 PR。本增量基于已合入计划主线的
`f9f664adfdc4b55d5d501c3e12d7b751af18a76e`，不覆盖原有 IPC 实现或历史胶囊。
限定报告子任务使用 [PR50-EVIDENCE-REPORT 胶囊](../../.agents/capsules/PR50-EVIDENCE-REPORT-R2.json)，
按现有覆盖式范围审计与原 IPC 胶囊共同约束 PR；受保护门禁与产品契约保持不变。

### 根因与修复

- 凭单表格的表头/分隔行原来只在“有凭单”分支生成。改为统一表格构造器，
  非空、空、读取失败三个状态均输出完整表格；发布前执行结构校验。
- JSON 损坏曾被静默丢弃；非法结构、编码、文件读取和目录遍历错误现在保留相对来源与
  安全诊断，不再冒充“未生成凭单”或“零缺口”，也不回显原始敏感载荷与主机路径。
- 动态数据中的竖线、换行、反引号、链接/HTML 语法按文本编码，不能破坏行列或注入内容。
- 展示本 PR 全部任务胶囊，按路径去重汇总每个任务的凭单；单个任务已有凭单不能掩盖另一任务缺证。
- 报告快照使用 PR 事件的 head/base SHA，和胶囊创建时基线分开展示。
- 自动评论使用固定标记、完整分页和机器人身份匹配；更新前复核 PR head/base 与开启状态，
  避免旧运行覆盖新报告，或误改人工评论。旧版机器人评论原位升级，不以新增评论掩盖问题。

### 测试与证据边界

渲染回归位于 [test_pr_report.py](../../engine/tests/test_pr_report.py)，通过锁定依赖图中已有的
Markdown 解析器生成真实 HTML 并检查表头、数据行与单元格。发布回归位于
[test_pr_report_publication.py](../../engine/tests/test_pr_report_publication.py)，运行实际 Node 发布模块，
以 API 替身覆盖分页、所有权、旧 head/base、关闭状态和写入前状态变化；测试不写 GitHub。
两份测试均由既有 Python 门禁收集，不跳过、不放宽原有测试。

报告只进行可读取形状检查和排版，不取代完整工程 Schema、摘要绑定或 Capsule Gate。
凭单原始 `verdict`、CI required checks、产品验收继续分开。没有凭单只表示当前检索范围内缺少
可读取记录，不代表没有运行过测试，更不能通过手写 `passed` 补齐。
真实 Work Receipt 仍必须由受保护验证流程生成；本增量不伪造 IPC 或产品验收凭单。
