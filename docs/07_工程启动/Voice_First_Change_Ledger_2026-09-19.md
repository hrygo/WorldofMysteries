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

## 持续审查增量

回读 PR #69 head `3103edd9174b37a4485e69d8be6f0de36cee2c83` 后继续同一文档分支，不另建PR。原有SpeechRail #62–#68保留；新增[SR-V08 / SpeechRail #69](https://github.com/hrygo/SpeechRail/issues/69)只固化普通ASR已有收口语义和组合回归，不重做#10的VAD/EOF实现，也不要求先新增finish API。

具体修正：当前previous_item_id为空；采用已核验FIFO下的commit→clear/cleared栅栏。必须保留append/commit失败和每个item终态，cleared不代表成功；停止采集/写队列水位属于本机，不能冒充服务采样回执。将纯MediaStop不调用领域取消从入口澄清同步到技术正文。媒体sample_count明确为每声道帧数，媒体seq与全量WS sequence分开。

增加[首批开工规格](Voice_First_Kickoff_Spec_v1.0.md)，给出W-V00/W-V02/03最小接口、失败oracle及可先行/受上游约束能力表。状态仍为文档与Issue落地，产品实现和声学目标未完成。

本轮只读文档导出run `35413562495`，Artifact `10575041441`，外层ZIP SHA-256 `892164a35626d7b22ee660a09c1bdff75d65e79dadef4f44096dfb9c6086efd0`；8份原始文档按manifest逐一核对Git blob及SHA-256。临时工作流不进入方案PR；清理与最新CI结果在PR交付回读中记录，不把导出成功当作产品测试。


## SpeechRail 团队维护视角再审查

确认 SpeechRail 同属团队维护后，依然保持其产品定位：本地共享 ASR/TTS 服务负责模型适配、音色制品、协议、资源准入与可验证的语音元数据；不接管游戏/LLM/麦克风/播放器。基于此新增四项通用平台任务：

- [SR-V09 / #70](https://github.com/hrygo/SpeechRail/issues/70)：版本化发音词典与可审计 SpokenText 映射。
- [SR-V10 / #71](https://github.com/hrygo/SpeechRail/issues/71)：结构化 Voice Catalog 与最小披露视图。
- [SR-V11 / #72](https://github.com/hrygo/SpeechRail/issues/72)：长文本/跨句 planner 与韵律连续性；明确不重做已完成 #18 的 planner 基础。
- [SR-V12 / #73](https://github.com/hrygo/SpeechRail/issues/73)：可选 TTS 文本-音频时间轴 sidecar，复用已有 fixed-text alignment 接缝但不阻塞热路径。

没有另建“预热 API”：冷驱逐/预热已由完成的 #9 和持续 #44/#65 覆盖。没有建立播放器、角色选角算法、剧情授权或业务数据库相关 SpeechRail issue，因为这些仍属于消费者。当前 SpeechRail issue 总数由 SR-V01..V08 扩展为 SR-V01..V12；创建 issue 不代表能力已实现。
