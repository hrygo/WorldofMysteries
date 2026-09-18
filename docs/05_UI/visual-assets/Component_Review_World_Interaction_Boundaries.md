# 组件审查：世界认知与真实交互边界

审查基线：PR #39，`9fff924f6cb41018238e2470218f67c18ae2d37c`。

目标不是清除全部数值字面量，而是防止控件破坏人物自主性、渐进认知和可理解的交互反馈。
本批不修改 Canon、领域协议、引擎或原画资产，不代表全组件验收完成。

## 已修复的问题

| 组件 | 用户可见的问题 | 修正与验收依据 |
| --- | --- | --- |
| AdviceInputField | 未绑定处理器时仍可提交并清空草稿；回车路径只检查非空。 | 按钮与回车共用交付策略；无处理器、禁用、纯空白均不调用、不清空。 |
| AdviceInputField | 回调同步写入的新草稿被旧提交的清理覆盖。 | 只清理本次交付的原始草稿；替换后的草稿保留。 |
| TarotCardView | Unknown / silhouette 的途径、序列和途径颜色泄露身份，VoiceOver 也可读出。 | 可见文字、辅助文字及途径样式共用发现阶段投影；未识别身份输入不同，输出仍相同。 |
| TarotCardView | “正典已确立”容易被理解为玩家探索改写了 Canon。 | 与 UI 基线 established biography 对齐，改为“生平已建立”。 |
| MysticIconButton | 控件与共享 ButtonStyle 各做一次禁用透明度，叠加后过暗；悬停仍可高亮。 | 禁用透明度仅由共享样式承担；禁用时清除悬停反馈。 |
| MysticIconButton | 外层读取焦点环境却未绑定实际 Button 的焦点。 | 使用 FocusState 绑定实际 Button；图标与点击尺寸复用现有光学尺寸和 density。 |
| MysticStatusDot | 首次显示后 isPulsing 变化不触发动画更新。 | 监听语义状态变化，同时保留 Reduce Motion / Differentiate Without Color 约束。 |

## 验证边界

`WorldInteractionBoundaryTests` 运行真正的草稿交付与发现阶段投影，而不只检索源码关键词。
案例包括未接通操作、禁用、空白、单次交付、回调替换草稿、两种隐藏阶段、三种已识别阶段及切回未知状态。

`VisualControlPrimitiveContractTests` 继续验证视图确实消费这些策略，且没有重复禁用透明度或回退到直接显示隐藏身份。

完整 macOS Swift / Xcode 结果以 PR 对应提交的 CI 为准；本报告不把编译通过等同于键盘、VoiceOver 或画面验收。

## 必须保留的限制

1. Advice 处理器被调用不等于 Engine 已接受或 COMMIT。当前 ContentView 的提交回调仍只驱动演示交互状态；真实交付、失败反馈与确认清理需要后续应用层集成，不能据本批宣称已经完成。
2. 卡牌投影只服从调用方给出的发现阶段，不计算权限，不替代 Context Compiler，也不维护第二份 Canon。
3. 组件的材质、造型和已有尺寸关系保留；没有为了复用数值而把圆角、边框和间距混成同一种 Token。
4. 全量 Token 一致性、透明材质合成对比度、窄窗口布局和辅助功能实测继续逐组件审查，不标记“全系统通过”。

基线参照：[UI 交互基线](../UI_交互基线_v1.0.md)、[Visual QA Contract](Visual_QA_Contract_v1.0.md)。
