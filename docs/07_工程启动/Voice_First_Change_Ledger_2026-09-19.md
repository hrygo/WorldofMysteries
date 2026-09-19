# Voice-First 方案落地 Change Ledger

日期：2026-09-19。任务：`VOICE-FIRST-V2-PLAN`。执行角色：AGT-ARB（方案与跨仓接口），不声称运行独立多Agent。

## 基线与范围

- WorldofMysteries：`main@591b4900606c122cb07416cd71fd56b66d056423`。
- SpeechRail：`main@28755de8cc51046f25ce75c7869fe1bacd34752d`。
- WoM目标分支：`docs/voice-first-v2-plan`；只修改Markdown。
- SpeechRail写入范围：创建需求Issue、关联已有Issue；不改代码、不启动服务、不下载模型、不执行验收。
- 输入：上一轮《Voice-First Runtime v2与动态音色管理方案》；在新基线上细化接口、状态、依赖、失败路径与验收。

## 获取与核对

Native Git网络预检失败（DNS）；通过GitHub连接器和只读Actions导出固定版本的tracked UTF-8源文件。导出省略二进制、symlink和过大文件，完整Git文件清单另存并逐项校验导出文件SHA-256/Git blob；**不是完整git clone，没有提交历史，也不声称检查过省略的二进制资源**。

只读导出run `35411844932`；Artifact `10573743072`；外层ZIP SHA-256 `97273728510618ed4e1f1633455f27bca2dde390783ad415c5b217d60b07702c`。导出只读仓库文件，不执行SpeechRail代码、模型或测试。

## 本次文件

- [入口](../03_工程规范/voice/README.md)
- [技术方案](../03_工程规范/voice/Voice_First_Technical_Design_v2.0.md)
- [跨仓接口与依赖](../03_工程规范/voice/SpeechRail_Integration_Contract_v1.0.md)
- [实施方案](Voice_First_Implementation_Plan_v2.0.md)
- [验收矩阵](Voice_First_Acceptance_v2.0.md)
- 本台账；docs导航与原语音规范增加v2方案关联。

## 状态与证据边界

文档分“已查证现状”“提议契约”“待实施任务”“候选SLO”，不把未来能力写成已发布API。主链改为双独立Realtime是基于HTTP BATCH_TTS准入与完整性边界的显式设计修订。

当前仅文档静态检查：内部链接、围栏、路径/敏感信息、任务/Issue映射、变更范围。未运行产品Python/Swift测试、真实模型、麦克风、UI自动化、音色创建或声学benchmark。Markdown属于仓库元数据范围，不伪造代码Task Capsule/Work Receipt；后续代码实施必须重新pack并遵守原始门禁。

GitHub PR号码、Issue链接、最终提交与CI状态以PR及本次交付索引的实际回读为准；本文不写自身commit SHA以避免自引用。不会自动合并或启用自动合并。


## 已发布增量

- 方案Draft PR：[WorldofMysteries #69](https://github.com/hrygo/WorldofMysteries/pull/69)。
- 首个文档提交：`9c9b3ce81eac4fb7f5e68fefb766b842c91f0aae`；6个Markdown的原子提交，tree `f94ad86ae2415abeb200007aaa2ec469e2dd55b7`。
- 第二增量：登记[SpeechRail #62–#68](../03_工程规范/voice/SpeechRail_Integration_Contract_v1.0.md)，关联既有#34/#44并补充导航；未提交任何SpeechRail代码变更。
- 本地文档检查不是运行时代码验收；PR自动触发的仓库CI与其实际head绑定，结果另记在PR和交付索引，不沿用其他PR证据。
