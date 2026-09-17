# Batch 26 — Visual System Closure

> 状态：FINAL CLOSURE  
> 基线：`main@5661a15a3d4e25fe3287dae9e5b483f6f4a6abd9`  
> Gate：`MACOS_APP_P0`

## 1. 目的

本批不新增视觉功能，只完成视觉系统工程交付的终态闭环：

1. 把 #31–#34 的真实合并状态写回 Living Plan；
2. 固化“最终 head 全部 required gates 成功后可自行合并”的当前项目授权原则；
3. 明确当前视觉系统工作已完成，后续只有在领域数据/独立工作流前置条件成立时才开启新范围；
4. 确保仓库恢复入口不再包含 stale stacked / pending 文案。

## 2. 已完成链路

- Foundation #21–#25：DONE
- Wave B #26：DONE
- Wave C #27：DONE
- Wave D #28：DONE
- Wave E #29：DONE
- Visual QA Backfill #31：DONE
- Wave F #32：DONE
- Wave G #33：DONE
- Wave H #34：DONE

PR #30 为主线漂移时主动关闭的过渡 PR，其有效工作已在 #31 重建并完成，不属于遗留。

## 3. 最终质量基线

- readable text contrast >= 4.5:1；
- long/important approved text pair >= 7:1；
- important non-text affordance >= 3:1；
- body >=13pt；metadata >=11pt；
- 960×640 minimum usable window；1180×760 default initial window；
- Inspector 280/320/420pt；
- no structural overlap；
- no minimumScaleFactor shrink-to-fit；
- no negative padding in content-layout fixes；
- native SwiftUI window/Inspector semantics；
- Reduce Motion / Increased Contrast / Differentiate Without Color / Reduce Transparency / Keyboard Focus contracts remain active。

## 4. 自动防回归

- `VisualQAContractTests.swift`
- `VisualQASourceGuardTests.swift`
- `VisualContrastContractTests.swift`
- `VisualTypographyContractTests.swift`
- `VisualWindowLayoutContractTests.swift`
- `VisualAdvancedInteractionContractTests.swift`
- Asset Catalog / navigation / icon semantic contracts

## 5. 合并原则

当前项目已授权：

- 最终 head 完整 required checks 全部 success 后，可自行 merge；
- merge 必须使用已验证的 expected head SHA；
- 不得跳过/绕过失败门禁；
- 失败时修实现或有依据地修契约，不为绿 CI 降低质量标准；
- merge 后必须回读 main / PR / remaining open PRs。

## 6. 本批文件范围

- `.agents/capsules/MAC-VISUAL-SYSTEM-CLOSURE-R2.json`
- `docs/05_UI/visual-assets/README.md`
- `docs/05_UI/visual-assets/Batch_26_Visual_System_Closure.md`

无生产 Swift、Engine、DB、IPC、schema、`.github`、`.hacf` 改动。

## 7. Capsule R2 说明

Closure R1 首次 Capsule Audit 在 docs-only PR 上被 gate 以 profile metadata 判定拒绝；R2 不修改门禁定义，而是将 capsule/gates 的 `risk_class` 统一到目标分支 `MACOS_APP_P0` registry 的 `medium`，并保留相同权威 `profile_digest`。R1 从最终树移除，历史保留审计痕迹。

## 8. Completion definition

本 PR 最终 `MACOS_APP_P0` 全绿并合并后：

- 当前视觉系统所有工作 PR 已合并；
- Living Plan 与远端事实一致；
- 仓库无本轮视觉系统 open PR；
- 未来 production Inspector / standalone window / placeholder data binding 视为新产品范围，而非当前遗留。
