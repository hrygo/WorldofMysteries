# Premium Art Delivery Workflow v1.0

> 状态：ACTIVE
> 适用范围：`feat/premium-art-production` 长期生产 PR 及其后续同类高品质视觉资产工作。

## 1. 推进原则

本工作流采用 **一个长期大 PR + 多个原子 commit**。中途不以 GitHub Actions 轮询作为主工作循环；CI 只在阶段性里程碑或最终收口时统一检查。

目标是把时间优先投入：高品质插画生产、资产整理、SwiftUI 接入、Visual QA 和 provenance，而不是等待/刷新 CI 状态。

## 2. PR 粒度

`#39 feat(macos): produce premium world and Artifact artwork` 作为 A1–A3 的长期生产 PR，持续累计以下内容：

1. 6/6 World / Scene artwork；
2. 15/15 Artifact premium object artwork；
3. runtime-ready crop / thumbnail / detail variants；
4. Asset Catalog ingestion；
5. typed artwork registry；
6. Ritual / Codex / Fate / Artifact runtime integration；
7. provenance / manifest / QA contract；
8. 最终 milestone CI 与合并。

不因单个图片、单个 imageset、单个 Swift 文件拆出额外 PR。

## 3. 原子 commit 规则

推荐提交序列：

- `art(world): add W1 world hero artwork`
- `art(world): add W2 gray fog artwork`
- `art(world): complete W3-W6 scene set`
- `feat(macos): add typed world artwork registry`
- `art(artifact): add P0 premium artifact set`
- `feat(macos): integrate P0 artifact artwork`
- `art(artifact): complete 15-of-15 artifact set`
- `test(macos): add artwork asset and layout contracts`
- `docs(art): finalize provenance and visual QA`

每个 commit 保持单一语义、可审查、可回滚。

## 4. CI 策略

### 中途

- 正常继续生产与提交；
- 不逐 commit 轮询 Actions；
- 不因为 CI 排队暂停图片生产；
- 只有出现明确阻断通知/已知失败时，才处理对应问题。

### 阶段里程碑

达到以下任一里程碑后统一检查 PR：

- 6/6 World Art 完成并接入；
- Artifact P0 7/7 完成并接入；
- Artifact 15/15 完成并接入；
- A1–A3 最终收口。

检查内容：

1. PR 相对 `main` 的纯增量；
2. Capsule scope / gate profile；
3. Asset Catalog / registry / manifest 一致性；
4. Visual QA；
5. Swift 6 / Xcode App Target；
6. `All Quality Gates Passed`。

失败时用原子 fix commit 修复最终 head，不降低 QA/Contrast/Typography/Asset Contract 标准。

## 5. 自动合并

最终 head 所有 required gates 全绿后，允许按项目授权自动合并；必须使用 verified expected head SHA，并在合并后回读 `main` 与 open PR 状态。

## 6. 高品质交付优先级

优先级固定为：

1. **真正的运行时高品质图片**；
2. 正确的 Canon Visual Brief 与 provenance；
3. runtime crop / quiet zone / focus zone；
4. typed asset integration；
5. Visual QA；
6. milestone CI。

禁止把“继续扩 UI primitive”“写更多说明文档”“频繁轮询 CI”当作替代实际绘图和集成的工作。
