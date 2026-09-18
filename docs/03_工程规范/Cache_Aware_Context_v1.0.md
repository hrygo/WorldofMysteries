# Cache-Aware Context v1.0

> 实施状态：按独立 WS-AI 增量交付；不表示完整 Context Compiler / Domain 授权 / 真实模型世界回合已经上线。
> 基线：`main@a44665acbde40561f10edd1ed7b67eaad0a98d4c`。决策日期：2026-09-19。

## 1. 目标与边界

目标是每个正确、已提交回合的成本与延迟下降，不是通过增加无关上下文美化缓存命中率。
本方案保持 [Context Compiler](Context_Compiler_v1.0.md) 的授权先行、
[AgentScope 边界](AgentScope_Integration_v1.0.md) 与
[Memory / Knowledge 分离](../02_领域引擎/Memory_Knowledge_Engine_v1.0.md)。

原规范定义权限及领域语义；本文新增模型输入的物理布局、确定性、失效与测量机制。
外部厂商机制来自文末官方文档；本地测试只证明构建行为，不代替真实服务命中或节省费用证据。

## 2. 分层与职责

| 区域 | 内容 | 更新与复用 |
|---|---|---|
| 应用执行契约 | 固定 Worker 职责、Schema、最小工具集 | Prompt / Schema / 工具发布时改变 |
| STATIC | 已授权且与任务相关的静态资料 | 依赖内容或权限改变时重建 |
| CORE | 稳定角色身份与能力定义 | 不混入当前资源、伤势或目标 |
| CHECKPOINT | 固定覆盖范围的已授权摘要 / 基线 | Epoch 切换时重建，不每轮改写 |
| HISTORY | 基线之后已提交、当前仍获授权的记录 | 按显式 sequence 只追加 |
| STATE | 当前有效状态、当前可用能力 | 每轮提供；模型不负责累计 StateDelta |
| RECALL | 本轮所需知识、信念、记忆、关系证据 | 上游先选集，编译器稳定呈现 |
| 当前任务 | 玩家建议、本次问题 | 最后追加；不是权威世界事实 |

预算优先级不等于物理位置。即使 STATE 在尾部，其正确性与保留优先级也高于历史背景。
Canon 稳定不代表任何角色都有权读取；完整原著、其他角色记忆与 Director 秘密不得用于填充公共缓存。
角色、Director、Narrative 等拥有独立 scope、最小工具集和输出契约。

## 3. 数据流与授权接口

```text
Domain 一致性视图 / 语义授权 / 检索选集
  -> AuthorizationView + ContextInput
  -> CacheAwareContextCompiler
  -> immutable PromptPlan
  -> PromptRenderer
  -> provider cache policy / complete-request token counter
  -> bounded Gateway / injected AgentScope transport
  -> JSON Schema + Domain proposal validator
  -> Session Orchestrator 决定后续事务（不在本模块）
```

`AuthorizationView` 是可信 Domain 组件签发的内部对象，不接受模型或 IPC 客户端自行构造。
授权使用完整 Evidence fingerprint，包括内容、来源版本、kind、layer、主体、时间与提交范围。
复制 source_id、改正文或改 placement 均不会继承旧授权。指纹是内容标识，不是密码学授权签名。

本增量不实现数据库授权或 RAG。其明确前置条件是：调用者已完成知识、可见性、剧透、时间与世界线授权，
并提供当前一致性快照；编译器再检查完整 grant、Consumer kind、时间、主体、世界与祖先分叉上界。
权限变化必须重新签发 view。缓存条目、会话 ID、同名事实均不能代替该 view。

所有资料保持 user/data 信任等级；只有应用管理的 WorkerProfile 指令进入 system。
JSON 定界不能防止全部提示注入，因此输出仍须 Schema 与 Domain validation，模型没有提交能力。

## 4. 模型表示与审计表示分离

原 `contracts/schemas/context_packet.schema.json` 保持不变；本次新增类型仅供 Python 内部使用。
不得将整个 ContextPacket 序列化发给模型。request_id、trace_id、excluded_counts、完整授权清单、
预算和编译诊断不进入稳定文本。必要 source_id / source_revision 随事实发送。

Canonical JSON：固定字典键顺序、保留字符串原文和数组业务顺序，拒绝非有限数字、重复 JSON 键、
非字符串键与过深嵌套。采用不可变字符串快照避免外部嵌套对象在取指纹后被修改。
排序只用于无序证据集合；HISTORY 使用显式事件顺序，不对自然语言或语义数组随意重排。

同一授权输入、依赖版本和渲染器必须产生相同消息结构与文本。request_id 或无关全局 revision
不应使稳定前缀变化。相关源正文变化、工具/Schema/Prompt 改变必须改变相应前缀标识。

## 5. Epoch 与失效

先交付稳定前缀 + 完整动态尾部。追加式 Epoch 是可选的第二增量，不绕过每次授权。
同一 Epoch：固定检查点、保留既有 HISTORY 顺序与字节、只追加新的已提交授权记录。
STATE 始终由引擎计算，不让模型从日志重放获得权威当前状态。

权限撤销、世界线分叉、摘要压缩、检查点替换、历史修正应开启新 Epoch；绝不保留旧秘密再追加“忽略”。
授权仍有效但改变已冻结片段也须显式重建。缓存失效、LRU 淘汰、进程重启仅影响性能，不影响领域记忆。
默认只保留有界内存级指纹记录，不保存完整私密 Prompt，不建立第五个权威数据库。

私有缓存路由身份由 owner / world / worldline / Consumer / subject / session / policy / lineage / Epoch
与 Prompt / Schema / 工具 / 渲染版本绑定；使用私有 HMAC，避免把角色身份和小秘密裸哈希写入外部元数据。
不使用每次变化的 request_id 或完整 Packet hash 作为复用组键。路由键不保证供应商隔离或命中。

## 6. Provider 适配

能力按实际 endpoint / model 的显式配置选择，不根据“OpenAI-compatible”或模型名称大小推断。

- OpenAI Responses / Chat：最新显式断点模式仅对已经核验支持的具体模型配置；stable block 标记
  `prompt_cache_breakpoint`，`prompt_cache_options.mode=explicit`；旧模型不发送这些字段。
- Claude Messages：`cache_control` 使用官方结构；控制断点数量与内容块回看窗口，不反复缓存一次性尾部。
- DeepSeek / 通用兼容服务：不发送未声明支持的缓存参数；默认/隐式缓存效果只从实际 usage 观察。
- Gemini / 本地 MLX 等先保留能力边界，不伪装本次已完成全部 API 适配。

TTL、最低前缀长度、缓存写入费用来自具体模型配置；不为了达到最低长度添加无关内容。
不改依赖锁、不绕过固定 AgentScope 版本。Adapter 接入时必须确认完整请求未被格式化器二次改写。
本增量默认不保存服务端 conversation/cache handle，不跨权限复用服务端历史。

## 7. Token 与执行预算

完整出站请求（包含工具、Schema、消息与协议开销）由注入的 provider/model token counter 计量。
禁止用字符数除四当作实际 token 数。缺少可信计数器不能宣称符合精确上下文窗口。
为输出预留额度；超预算直接返回可分类错误，不静默删除硬约束、当前状态或玩家任务。
上游应缩减低价值召回或开启新 Epoch 后重新编译。

异步模型执行有整体期限与有界重试；仅对当前 AI stage 的格式错误进行局部修复，不重跑已提交回合。
每次发送前重新检查快照；收到结果后再次检查，过期提案拒绝进入后续 Domain 操作。

## 8. 可观测性与验收

记录各分段身份、预期稳定边界、实际读取/写入/未缓存输入 token、计数可用性、调用次数及延迟。
不记录完整 Prompt、原始秘密、凭据或未脱敏异常。usage 缺失表示 unknown，不虚构 0。
Claude 总输入为 uncached + cache_read + cache_creation；OpenAI 的 cached 是 total input 子集。

必须区分：本地前缀字节相等、供应商命中、成本降低、用户回合质量四种证据。
聚合指标使用总 cache_read / 总 input，不直接平均单次请求百分比。质量指标还需包含 Schema/Domain
失败率、知识泄露与陈旧状态拒绝；不能通过高重试率换取表面命中率。

验收矩阵：
1. task / request metadata 变化不破坏稳定前缀；字典/查询顺序不抖动，语义数组顺序保留。
2. 未授权内容、篡改正文、错误主体、跨世界、未来知识、越过祖先 fork 边界全部拒绝。
3. 权限撤销即使已有 Epoch 也拒绝；修改历史或压缩必须显式换 Epoch。
4. Provider 请求字段/断点及未知能力降级可复核；不把本地匹配算作 provider hit。
5. 完整请求计数、输出预留、超时、重试、过期结果与 Domain 拒绝均有测试。
6. 真实命中测试后续只能用获准的合成数据、显式凭据与费用预算运行；本地假 Transport 不作为实测。

## 9. 交付节奏与退出条件

A：本方案、任务契约、确定性编译与授权回归，早期 Draft PR。
B：Provider cache policy、统计规范化、有界 Epoch 与 Gateway 集成测试，同一 PR 原子提交。
C：原始 AI_GATEWAY_P0 凭单、完整 CI、范围/摘要验证。未达到目标平台或真实服务验收时保留缺口。
D：Domain 授权/检索与 Golden Mock 就绪后，接入真实业务 Orchestrator，完成真实 API 成本基准。
本 PR 不修改 SQLite #63、签名链 #55、App/IPC/公共 Schema，不开启自动合并。

## 10. 官方依据（核验日期 2026-09-19）

- [OpenAI Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)
- [Claude Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [DeepSeek Context caching](https://api-docs.deepseek.com/guides/kv_cache/)

厂商参数和计费可变化，实施时以实际 endpoint / 固定 SDK 的契约测试和 usage 为准。
