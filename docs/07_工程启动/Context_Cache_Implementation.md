# Cache-Aware Context 实施记录

## 基线与交付范围

任务 `AI-CACHE-AWARE-CONTEXT`，基于 `main@a44665a`，分支 `feat/cache-aware-context`，PR #65。
完整设计：[Cache-Aware Context v1.0](../03_工程规范/Cache_Aware_Context_v1.0.md)。
本次仅修改 Application / AI、对应单测及实施文档；公共 Schema、Domain、数据库、App 和受保护门禁不变。

## 已实现组件

| 文件 | 实际职责 |
|---|---|
| `engine/application/context_plan.py` | 不可变内部 IR、ContextScope、Evidence、AuthorizationView、WorkerProfile 与 PromptPlan |
| `engine/application/context_compiler.py` | 完整内容 grant 二次检查、Consumer kind、时点、主体、跨世界及祖先 fork 上界检查、确定性排序 |
| `engine/application/context_epoch.py` | 有界、线程安全的 LRU 指纹记录；冻结前缀与追加历史连续性；显式重建错误 |
| `engine/ai/prompt_renderer.py` | 稳定契约 → 授权资料 → 当前状态 → 任务；元数据不出站；HMAC 私有复用身份 |
| `engine/ai/prompt_cache_policy.py` | 显式 endpoint/model 能力配置；OpenAI Chat/Responses、Claude、无特有字段通用模式 |
| `engine/ai/cache_metrics.py` | OpenAI/Claude/DeepSeek usage 规范化；未知不冒充零；加权聚合与无效计数拒绝 |
| `engine/ai/gateway.py` | 完整请求计量、输出预留、发送前后新鲜度复核、局部 Schema 重试、Domain validator、逐尝试统计 |
| `engine/ai/agentscope_adapter.py` | 绑定目标的 prepared executor 接口；原样转交不可变请求，不拥有领域状态 |

`Evidence` 指纹不是授权签名。`AuthorizationView` 必须由可信 Domain 服务生成，不能把客户端传入的
source_id 或候选对象转换成 grant。数据库知识/可见性/RAG 授权逻辑仍需上游实现，不能只靠 kind 标签。

## 调用方式与宿主前置条件

```python
from engine.ai.gateway import CacheAwareGateway, ExecutionBudget
from engine.ai.agentscope_adapter import PreparedAgentScopeAdapter
from engine.ai.prompt_renderer import PromptRenderer

# 以下依赖由可信 Application composition root 提供，而非 LLM/IPC 输入：
# target: 明确 endpoint/model 的 ProviderProfile
# execute_prepared: 已对固定 AgentScope SDK 做出站捕获验证的异步执行器
# authorize: 每次返回当前领域授权快照的异步函数
# count_full_request: 与目标模型绑定的完整请求 token 计数器
# validate_domain_proposal: 纯领域语义校验，不能在此提交事务
# secret: 从宿主受保护凭据存储读取的至少 32 字节随机 HMAC key

gateway = CacheAwareGateway(
    renderer=PromptRenderer(secret),
    transport=PreparedAgentScopeAdapter(target, execute_prepared),
    authorize=authorize,
    count_tokens=count_full_request,
    validate_proposal=validate_domain_proposal,
    observe_attempt=record_safe_attempt_metadata,
)
result = await gateway.execute(
    context_input, worker_profile, target,
    ExecutionBudget(context_window=16000, output_tokens=2000),
)
# 仅得到已验证 Proposal；提交仍由 Session Orchestrator 管理。
proposal = result.proposal()
```

该代码展示集成接口，不提供伪造的生产 authorize / tokenizer / 模型客户端。
原 ContextPacket 保持审计用途，不能直接整体转换成 Prompt。
输出 Schema 必须先解析成本地无 `$ref` 的完整 Schema；v1 拒绝远程 Schema 引用，避免校验时访问网络。
结构化网关 v1 对非空 tools 明确拒绝，不把未实现的 Director 工具循环伪装成支持。
Schema 目前作为固定执行提示并由 JSON Schema 在本地验证，不冒称所有厂商的原生 strict structured output 已开启。

## 已运行的本地证据

本地为 Linux / Python 3.13.5；不是生产锁定的 Python 3.14.7 / macOS arm64。

- 新增四组上下文、Epoch、Provider、Gateway 测试：**76 passed**。
- Architecture Fitness：通过。
- Python compileall：通过。
- 完整本地套件：在正确的 engine 工作目录收集时因缺少 `openai` 依赖失败；没有全绿结论。
- 工作区独立环境 provisioning 尝试 `uv sync --locked --extra dev`，下载 Python 时因 DNS 失败。
- 本地测试计数器和 Transport 使用合成值。任何数字均不代表真实云端 cache hit 或计费节省。

测试覆盖：动态尾部与请求 ID、静态资料角色等级、篡改正文/层级、撤权、跨世界/角色/分支、未来证据、
当前状态必需性、history 连续性与 LRU、Provider 断点和输出额度字段、未知 usage、加权统计、
整请求预算、超时与取消、重试、过期结果、Domain 拒绝和失败调用 usage 保留。

正式目标平台凭单与 CI 状态在 PR 中按实际 head 记录；不回填到历史受测提交，不手填成功凭单。

## 待满足的生产接入门禁

1. 真实 Domain 授权、检索选集和会话一致性视图，以及 Golden Mock 先行路径。
2. 固定 AgentScope 2.0.8 + SDK 的真实出站请求捕获测试，确认缓存字段、角色和消息边界不被改写。
3. 实际模型 tokenizer / count API 对工具、Schema 与协议开销的计量，不使用字符数近似冒充精确计数。
4. 显式授权的合成云端基准：冷/热、重试、TTL、换模型、世界线与权限变化；真实 usage / TTFT / 成本。
5. 完整世界回合接入；本次不在 App 启动或 IPC 中启用网络模型调用。

## 运行时注意事项

- Epoch 淘汰仅丢弃指纹连续性提示，调用方必须在从领域来源重建时管理新 Epoch；它不是完整历史存储。
- Provider AUTO 仅不发送特有参数，不承诺关闭服务端自动缓存；默认无付费保活或 NPC 预热循环。
- 失败/超时可能没有 usage，统计应保留 unknown 覆盖；遥测 sink 自身故障由宿主监控，不能导致领域重试。
- 对各阶段调用的预算是单次 stage 总期限，含计数、授权与 Schema 重试；不跨已提交阶段回滚。

## 基线刷新记录（2026-09-19）

首个目标平台 run `35404425215` 在精确代码 `8e69abd` 上被原始 verifier 拒绝：
读取到 `origin/main@afdad649`，而 R1 契约目标仍为 `a44665a`。没有运行放行门禁，
该次失败不代表 76 项专项测试失败，也不作为通过证据。原始失败 Artifact `10571299118` 保留。

已读取新增治理规范；新 main 只更新 HACF 目标 ref 与作业文档/回归，不与本任务文件重叠。
业务分支合入 `afdad649e07be3b01f54f1f53ba9a6651cda2d5f`，在该 main 上使用未修改的
`pack_capsule(..., target_ref="origin/main", supersedes=...)` 创建 R2：
`.agents/capsules/AI-CACHE-AWARE-CONTEXT-R2.json`。范围及受保护档案保持原样，R1 不回写。
必须在新已提交 head 上重新执行 verifier；未使用 `--allow-stale`。
