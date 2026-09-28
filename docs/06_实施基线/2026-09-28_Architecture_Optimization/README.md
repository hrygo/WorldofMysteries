# 架构优化 — Luna 独立交付方案集

> 核实日期：2026-09-28。源码基准：`main@ca68d485a15bacf46ade5e703abde00598ec5251`。
> 状态：待实施设计；本轮仅分析和生成文档，未执行代码变更、数据库迁移、门禁、真实模型/语音测试、提交或推送。
> 图谱 generation 为 `2026-09-19T23:55:02Z`，相关新增/变化文件已直接读取源码补证；不声称完成全仓穷尽审计。
> 编写时 `docs/PROJECT_STATE.json` 存在其他未提交改动，保留原状。
> 收尾核对：另一文档提交已将 HEAD 推进至 `79e93e9`；相对 `ca68d48` 仅变更状态、文档入口及四视图，业务代码不变，本方案源码依据仍有效。本批六份方案未提交。

## 方案与交付顺序

| ID | 独立交付文件 | 交付结果 | 硬依赖 | 建议责任角色 |
|---|---|---|---|---|
| AO-01 | [结构化叙事与音频解耦](01_Narrative_Audio_Separation_Luna_Guide.md) | 没有语音也有文字；旁白/对白类型保留 | 无 | AGT-AI 主责，AGT-VOICE / AGT-MAC 配合 |
| AO-02 | [统一文字与语音请求恢复](02_Unified_Input_Recovery_Luna_Guide.md) | 两种输入共用冻结请求与恢复机制 | 无 | AGT-MAC |
| AO-03 | [提交后持久工作与恢复](03_Durable_Post_Commit_Work_Luna_Guide.md) | 提交回执及时返回，后续工作可恢复 | AO-01、AO-02 | AGT-ARB 主责，AGT-DATA / AGT-MAC 配合 |
| AO-04 | [场景规则与 Golden 隔离](04_Scenario_Policy_Isolation_Luna_Guide.md) | 通用会话不依赖五轮常量及 Golden 工厂 | 无；建议 AO-03 后合入 | AGT-AI 主责，AGT-DOM 配合 |
| AO-05 | [动态授权上下文接线](05_Authorized_Runtime_Context_Luna_Guide.md) | live 调用消费同一快照下的授权证据 | AO-04 | AGT-AI 主责，AGT-DATA / AGT-DOM 配合 |
| AO-06 | [回合编排与装配收敛](06_Turn_Orchestration_Convergence_Luna_Guide.md) | 一个回合编排者，集中装配与清晰模型执行边界 | AO-03、AO-04、AO-05 | AGT-ARB |

推荐合入顺序：**AO-01 → AO-02 → AO-03 → AO-04 → AO-05 → AO-06**。独立交付表示每份有自己的范围、完整行为、测试和回退方式，不要求六份一次性上线；不代表没有前置依赖或可以同时写共享文件。

AO-01 与 AO-02 可在独立工作区分别准备；`AppState.swift`、`StorySessionPanel.swift`、显式 Swift driver 源文件清单等共享路径只能有一个写入者。其余包按顺序合入，依赖完成后重新核对基准并修订胶囊。本文不自动创建或委派代理。

## 共同架构决定

1. 保留 SwiftUI App + 同机独立 Engine、类型化 UDS、四库隔离、单写事务和确定性 Resolver。
  世界与角色事实继续归 Domain；AI 无数据库写权限。
2. `projection_outbox` 是检索投影的 revision 确认队列，**不得挪作表达任务队列，也不得由表达 worker 标记 projected**。AO-03 增加独立工作记录，通过同一个领域事务登记必要后续工作。
3. `TurnTransaction.status` 表示现有回合/表达进度，`turn_intake_commands.status` 表示输入受理；AO-03 工作状态表示调度，不替换二者，不制造第二份世界事实。
4. AO-01 先保留同步提交接口语义；AO-03 通过新增 capability / v2 方法引入快速回执，不偷偷改变旧方法的完成语义。
5. AO-02 冻结的 `input_mode` 与 wire method 必须进入本地请求日志；旧日志只能按历史事实解释为固定文字请求，不能推断为语音。
6. AO-04 先实现规则注入与第二个测试场景，不同时开放任意外部内容加载，不放宽现有 `golden_001` 公开白名单。
7. AO-05 复用已有授权 IR 与编译器；不伪造 token 计数以强行接入 CacheAwareGateway。完整缓存网关接线不是本轮必要条件。
8. AO-06 保留当前 OpenAI-compatible transport 的执行行为；AgentScope 完整 SDK 接入另立任务。需要修改现有 ADR 的规范决定必须走架构评审，不能靠代码重构默认为已批准。

## 证据与验证规则

- 前序：[项目现状分析与四视图](../../01_总体架构/2026-09-28_项目现状分析与四视图.md)。
- 本方案集里的新模块、类型、表、状态和 IPC 方法均标为“拟新增”；当前代码符号集中在各文件第 2 节。
- 所有实现验收当前均为**未执行**。文档生成不证明测试通过，也不证明模型/TTS 可用。
- 门禁命令唯一来源保持为 [FULL_P0](../../../.hacf/gates/full_p0.json) 与 registry；各方案只调用 runner，不复制或重定义 stage 命令。
- 业务代码跨角色路径与 `contracts/`、迁移等受保护路径，由 AGT-ARB 在实际实施胶囊中明确授权。用户当前授权仅为生成方案，不能据此执行迁移、发布或合并。
- 每份方案实施时遵循项目 pack → 隔离工作区 → 实质提交 → verify → 独立凭单提交流程；创建托管工作区时遵循当前宿主工具规则。远端变更另按会话授权处理。

各方案共同的验收入口，运行位置为**实际实施工作区根目录**：

```bash
python3 scripts/gate_profile.py check
python3 scripts/gate_profile.py run --profile FULL_P0 --cwd . --log-dir .hacf/logs/architecture-optimization
```

预期：registry 一致，所有档案 stage 成功，相关新用例确实被收集且未跳过。实现者按下列各方案验收矩阵检查原始证据，不以退出码代替结果核对；胶囊 verify 产生的 Work Receipt 仍是后续集成所需证据。

真实设备/外部模型验收使用现有 opt-in 用例另行记录，不能把默认跳过记为通过。无设备或服务时，只能声明确定性/受控依赖部分通过，并列出剩余实测。

## 冲突与回退

每包实施前检查目标分支、工作树、已有迁移编号、契约与前置包产物。发现差异先核实，不覆盖并行改动。新编号使用实施时下一空闲版本；文档中的 `013` 仅是 `world schema=12` 基准下的拟定值。

非数据库包采用普通代码回退且保留用户文件。数据库升级后禁止把旧二进制直接指向新库、删除新表降级或以旧备份覆盖用户新事实；优先前向修复。只有明确接受升级后数据损失且另获授权，才允许在隔离恢复目录核实备份后恢复。
