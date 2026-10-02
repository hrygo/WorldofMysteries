# ADR-007：provider 中立的能力声明契约

> **状态**：待裁决（提案；供人类架构师与 AGT-ARB 评审）  
> **日期**：2026-10-02  
> **职责**：人类架构师负责架构裁决；AGT-ARB 维护决策与契约边界  
> **作用范围**：音频能力探测、`AudioCapabilityObservation`、渲染运行时与铸造面的装配条件、绑定准入  
> **前置文档**：[ADR-005](ADR-005_音色供给与铸造_v1.0.md)、[ADR-006](ADR-006_叙事块的说话人语义.md)  
> **语态约定**：第 2–4 节以终态事实语态定义系统行为；第 1 节记录当前证据，第 5 节记录决策状态。

---

## 1. 背景与证据边界

ADR-005 第 60 行要求「不永久排斥具备相同保证的其他 provider 来源」，`AGENTS.md`
项目头声称「支持任意兼容第三方热拔插」。2026-10-02 实测发现：**换任何非 SpeechRail
服务商，整个音色面关闭**——不是降级，是消失。

本仓静态复核与实测确认以下事实：

| 证据 | 当前结论 | 对决策的约束 |
|:---|:---|:---|
| `engine/infrastructure/audio/capabilities.py:443` | `provider_name.casefold() != "speechrail"` 即返回 `status="not_applicable"`、`assurance="not_applicable"`，**不做任何探测** | 「无能力声明」与「非 SpeechRail」被当成同一件事 |
| `engine/infrastructure/story_runtime.py:673` | `_open_voice` 对非 SpeechRail 返回 `None` | 无渲染运行时 |
| `engine/infrastructure/story_runtime.py:698` | `_open_foundry` 对非 SpeechRail 返回 `None` | 铸造面不注册，握手不宣称该能力 |
| `engine/infrastructure/voice_binding_resolver.py:165` | `observation.status != "ready"` 即抛 `voice_provider_not_ready` | 绑定全拒 |
| 本仓实测（三种 provider 各一次） | `speechrail` → 渲染运行时有；`openai-compatible` 与 `elevenlabs` → 运行时 `None`、快照 `not_applicable` | 行为确定，非偶发 |
| `engine/tests/test_audio_adapter.py:435-436` | 测试**断言** `status == "not_applicable"` | 这是当前既定设计，不是疏漏 |
| `docs/` 全库检索 | 此前**未任何位置**声明这条限制 | 缺口此前未披露，本 ADR 同时补上披露 |

三处闸门形态一致，注释也一致（"Build the render runtime only for a named
SpeechRail provider"），说明这是一个**有意但过宽**的判断：把「我只会说
SpeechRail 的协议」写成了「只有 SpeechRail 可用」。

本 ADR 不主张立刻放开绑定。它主张把「协议不会说」与「产品不许用」这两件事分开。

## 2. 问题陈述

能力探测解析的是 SpeechRail 专有端点 `/v1/speechrail/capabilities`。因此：

1. 本仓**只有一种协议实现**，任何其他服务商的真实能力在本仓无从得知；
2. 代码据此把「无从得知」升级为「禁止使用」；
3. 于是 ADR-005 第 60 行的「不永久排斥」在实现层失效，`AGENTS.md` 的
   「热拔插」声索与实现长期背离。

**当前行为是安全的**（fail closed），问题不在安全性，而在**安全被用作不实现的理由**：
正确的 fail closed 是「没有能力声明就不绑定」，而不是「不认识的名字就不许绑定」。

## 3. 目标行为

1. 能力探测按**能力声明是否存在**判定，而非按服务商名字。
2. 未提供能力声明的服务商 → `not_applicable` 且准入全拒，**与今日行为完全一致**。
3. 提供本仓可解析的能力声明的其他服务商 → 走与 SpeechRail **同一套**准入规则。
4. 准入规则本身**不放宽**：ADR-005 的证据、范围、撤销、时效条件一字不改。
5. 新增服务商只允许**新增映射**，不允许修改准入判定。

## 4. 方案

### 4.1 中立能力声明契约

新增 `contracts/schemas/audio_capability_declaration.schema.json`。字段忠实映射
现有 `VoiceCapabilityObservation`，**不新增语义**，只去掉厂商专有命名：

| 契约字段 | 映射自 | 说明 |
|:---|:---|:---|
| `schema_version` | — | 固定 `audio_capability_v1` |
| `provider_instance` | `provider_name` | 服务商标识，仅作审计与隔离 |
| `service_instance_epoch` | 同名 | 服务重启后必须变化，防止跨重启复用陈旧目录 |
| `catalog_revision` | 同名 | 目录集合修订 |
| `voices[]` | 同名 | 见下 |
| `realtime` | `RealtimeResponsibilityObservation` | 谁负责编排/会话状态，调用方不得假定服务端助手 |
| `guarantees` | 同名 | provider 自述保证，游戏侧只记录不据此放宽准入 |

`voices[]` 每项：`voice_id`、`available`、`availability_reason`、`variant`、
`voice_revision`、`voice_identity_assurance`、`revoked`、`production_ready`、
`production_ready_reason`、`quality_status`、`supports_speaker`、
`supports_instruction`、`supports_clone`、`realtime_speech`，以及嵌套 `model`
对象承载 `source` / `artifact` / `variant` / `assurance` / `runtime_revision` /
`catalog_revision`。

**字段不删不改名**，是为了让映射是纯机械的：SpeechRail 的
`/v1/speechrail/capabilities` → 中立声明是一次字段重命名，不含判断。

### 4.2 关键约束：`runtime_revision` 不可省

ADR-005 V01 要求「带 pin 但缺合格证据的声音不能正式合成」。中立契约因此规定：
`voices[].model.runtime_revision` 为**必填**（`rt_` 前缀 + 64 位十六进制），
缺失即整个声明 `invalid`，provider 不得声明 `production_ready: true`。

这条把 §3 的上游缺口**内建进契约**：今后任何 provider 若拿不出运行时身份，
在契约层就被挡住，而不是等到绑定时才被拒。

### 4.3 三处闸门的改法

```python
# 现状：按名字否决
if provider_name.casefold() != "speechrail":
    return None

# 提案：按证据否决
if not capability_declaration_available(provider):
    return None
```

- `capabilities.py`：新增 `SpeechRailCapabilityDeclarationAdapter`，把现有
  `/v1/speechrail/capabilities` 解析结果**投影**为中立声明。现有解析逻辑
  （`_parse_model_identity` 等）原样复用，行为不变。
- `story_runtime.py`：`_open_voice` / `_open_foundry` 改为检查
  「是否已取得该 provider 的能力声明」，而非名字。
- `voice_binding_resolver.py`：`_select` 的 `status != "ready"` 判定保持不变。
  **它本来就正确**——中立声明若声明了但 `production_ready=false`，仍会被拒。

### 4.4 一个服务商如何接入

1. 实现 `CapabilityDeclarationAdapter`，把该服务商的**原生**能力响应映射为中立契约；
2. 注册到 adapter 表，键为 `provider_instance`；
3. 映射测试须覆盖：字段缺失、`runtime_revision` 缺失、撤销态、目录修订变化；
4. **不得**修改 `voice_casting_policy` 或 `voice_evidence` 的任何判定。

本轮**不实现**任何非 SpeechRail 适配器。ADR 批准只解除「机制上不可能」，
不解除「尚未有人写适配器」。

## 5. 迁移、兼容与回退

| 方面 | 结论 |
|:---|:---|
| 持久化数据 | 无迁移。能力快照是读时观测，不入库 |
| 公共接口 | 新增 schema 与 adapter 协议；**不删除**任何现有字段或行为 |
| 现有行为 | SpeechRail 路径逐字段等价，FULL_P0 全绿 |
| 其他服务商 | 与今日**完全一致**：`not_applicable`、绑定全拒 |
| 回退 | 不引入契约即回到今日状态；变更可独立评审、独立回退 |
| 风险 | 最大风险是**误以为已支持热拔插**。故本 ADR 批准后，`AGENTS.md` 与本 ADR 须同步标注「机制具备，尚无第二个适配器」 |

## 6. 测试策略

| 层 | 断言 |
|:---|:---|
| 映射单测 | SpeechRail 响应 → 中立声明，逐字段等价；现有断言全部保留 |
| 契约校验 | 缺 `runtime_revision` 的声明判 `invalid`，且 provider 不得声明 `production_ready` |
| 闸门行为 | 无声明的其他 provider → `not_applicable` + 绑定拒（与今日一致） |
| 准入不变 | 中立声明下 `production_ready=false` 仍被拒；证据、范围、撤销、时效条件一字未改 |
| 真实联调 | 对 SpeechRail 跑 `voice_contention_probe` 与 `test_speechrail_live_contract.py`，确认 RTF/TTFC 与 2026-10-02 基线（0.253 / 0.026s）同量级 |

## 7. 与既有决策的关系

- **不改 ADR-005 的任何准入条款**，本 ADR 只解决「如何得知其他 provider 的能力」。
- **不改 ADR-006** 的说话人语义。
- 与 §1 表格中「此前未披露」互相补足：本 ADR 负责机制与契约，
  [验收报告 §4.1](../06_实施基线/2026-10-02_ADR005_逐项验收报告_V01-V12.md) 负责披露。

## 8. 决策状态

**待裁决**。需人类架构师裁定三项：

1. 是否引入中立能力声明契约（公共接口变更）；
2. `runtime_revision` 是否定为必填（会使所有不提供该字段的服务商一律不可用——
   这是**有意为之**的 fail closed，但代价是当前没有任何第二家可用）；
3. `AGENTS.md` 项目头「支持任意兼容第三方热拔插」的表述，
   在第二个适配器落地前是否下调为「机制已备，尚无第二家适配器」。

未裁决前，**实现保持现状**：SpeechRail 独占，非 SpeechRail 全关。
本 ADR 不授权任何绕过准入的改动。
