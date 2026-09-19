# Voice-First v2 技术与实施工作包

日期：2026-09-19。状态：**方案落地，运行时待实施**。本工作包不代表已接通真实游戏回合、已达到音质/延迟目标或已完成发行验收。

| 文档 | 用途 |
|---|---|
| [技术设计](Voice_First_Technical_Design_v2.0.md) | 架构、数据、状态机、媒体传输、身份与表演、缓存和失败路径 |
| [实施方案](../../07_工程启动/Voice_First_Implementation_Plan_v2.0.md) | W-V00–W-V10，代码落点、责任、依赖、完成标准与回退 |
| [SpeechRail接入与Issue映射](SpeechRail_Integration_Contract_v1.0.md) | 已有能力、提议契约、上游任务与兼容路线 |
| [验收矩阵](../../07_工程启动/Voice_First_Acceptance_v2.0.md) | 协议、取消、安全、声音身份、缓存、设备、中文听测和SLO |
| [首批开工规格](../../07_工程启动/Voice_First_Kickoff_Spec_v1.0.md) | 连接认证、ASR收口oracle、媒体/Domain命令分流与依赖降级表 |
| [Change Ledger](../../07_工程启动/Voice_First_Change_Ledger_2026-09-19.md) | 基线、来源、交付与验证边界 |

第一目标：用户说完建议 → 唯一Final → 真实世界COMMIT → 固定角色开声 → 用户打断 → 原生停止 → 继续或新建议 → 旧音频不回流、事实不重复也不回滚。

媒体服务与Domain尚未全部接线时，可以显式交付`media_demo`，不能把Mock提交写成生产`story_voice`。原生设备和游戏提交属于WorldofMysteries；模型、Provider音色制品与资源准入属于SpeechRail。两个仓库独立环境、独立发布，只通过协商接口连接。

## 操作语义澄清：停声不等于取消回合

技术设计 §5.3 的 `cancel_pending` 竞态流程，仅适用于用户明确取消 pending Turn，或已确认用新 Advice 替代尚未提交的回合。纯粹 `MediaStop / Pause / Replay / Volume` 只影响播放、媒体 generation 和对应语音渲染；**不因为停止扬声器而自动调用 Domain 取消**。

语音活动或短应答先停声/duck，待最终意图确认后才选择领域操作。实施 W-V03/W-V09 必须分别验证“纯媒体停止不取消回合”和“显式取消与 COMMIT 由同一 Writer 裁决”。已提交事实始终不回滚；任何用户界面的 PRE_COMMIT 显示都不能替代事务结果。

当前只增加文档和SpeechRail待办；不更改已有Schema、代码、模型或用户数据，不自动合并。
