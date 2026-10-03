---
name: wom-collaborator
description: >-
  《诡秘世界》日常轻量研发协作：用户目标、按变更面验证、PR 与 CI、按需工作区隔离。
  仅显式治理任务使用 HACF 胶囊、范围裁决与凭单。
---

# 《诡秘世界》轻量研发协作

2026-10-03 起采用 [ADR-009](../../../docs/01_总体架构/ADR-009_HACF日常流程轻量化.md)。
执行约定以 [AGENTS.md 第 4 节](../../../AGENTS.md#4-日常研发流程hacf-轻量模式) 为准。

## 日常任务

1. 查清用户目标、当前实现与实际影响，保留用户数据和他人改动。
2. 一个功能可以在同一分支跨目录同步契约、实现和测试；角色表示专长，不扩大用户授权。
3. 按变更面验证；涉及治理、工具链或跨域变更时执行完整质量门禁。
4. PR 说明问题、结果、实际验证与风险。质量结论以 CI、构建和评审为依据，
   功能完成还需对应接线、真实服务或用户体验证据。
5. 并行写入或工作区不干净时使用独立 worktree、独立环境和短路径运行资源；
   回收前核实干净且内容已落地，不强删未知改动。

日常任务不要求 `pack`、胶囊、Work Receipt、Integration Receipt、本地 `integrate`
或按角色目录拆分 PR。`Capsule Gate` 保留历史检查名，默认仅校验门禁档案与 registry。

```bash
python3 scripts/gate_profile.py resolve
python3 scripts/gate_profile.py run --profile <ID>
python3 scripts/capsule_audit.py --base-ref origin/main
```

## 显式治理任务

仅当用户或任务明确选择严格多执行者治理时，采用
[旧 HACF 2.1 SOP](../../../docs/03_工程规范/高效人机协同研发体系实施方案_v1.1.md)
和 `capsule_audit.py --mode governed`。保留七种角色与历史胶囊/凭单供追溯，
不扫描历史凭证来授权新任务。胶囊不可回写，凭单只能如实记录测试结果。

产品不变量、模块依赖边界和跨语言契约一致性在两种模式中都有效。
门禁档案变更仍需同步 registry 并接受评审；用户授权是实施与远端操作的依据。
本机执行使用 RTK；共享文档与示例使用原生命令。
