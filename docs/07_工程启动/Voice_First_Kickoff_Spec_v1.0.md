# Voice-First 首批开工规格 v1.0

日期：2026-09-19。状态：**实施输入与测试规格，尚未编码或执行用例**。

本文件细化[实施计划](Voice_First_Implementation_Plan_v2.0.md)的 W-V00/W-V02/W-V03；总设计以[Voice-First v2](../03_工程规范/voice/Voice_First_Technical_Design_v2.0.md)为准，上游事项见[跨仓契约](../03_工程规范/voice/SpeechRail_Integration_Contract_v1.0.md)。固定审查基线为 WoM `591b490`、SpeechRail `28755de8`。正式编码必须重新固定当时基线、pack 并取得所需范围。

## 1. 首批实现范围与入口

先交付可以独立验证的 `media_demo`：PTT 采集 → 真实 ASR → 明示的合成台词 fixture → 固定音色 TTS → 原生播放/停止。界面必须明确这不是世界回合；不能让测试用 Commit/Authorization 被生产依赖注入自动选中。

`story_voice` 单独启用：只有真实领域授权、一致性读取、幂等命令、Writer COMMIT 与恢复查询均存在，才可把 FinalTranscript 接入玩家建议。基础媒体功能可以先开发，不必等待全部上游增强或情绪研究。

候选实现位置，不在本次创建：

| 位置 | 首批职责 | 不应承担 |
|---|---|---|
| engine/infrastructure/audio/config.py | 显式配置优先、默认loopback、超时与策略校验 | 安装/启动SpeechRail、回退云端 |
| engine/infrastructure/audio/ 下新发现适配器 | 当前models/voices及最低协议能力、legacy状态 | 宣称跨GET是原子snapshot |
| engine/domain/audio_voice.py | 未提供confidence保留unknown；旧整段接口兼容 | 依赖SDK、持久化原始音频 |
| Swift Media/ 下 ASR client/assembler | 采集、单写队列、manual ASR、输入闭合、媒体控制 | 直接写world.db或判定Commit成功 |
| engine/infrastructure/audio/ 下 Realtime TTS adapter | response关联、PCM重组、明确终态、取消 | 选择未授权声音/台词 |
| Engine MediaBridge 与 Swift Playback | 独立媒体面、generation、本机停止、进度估计 | 把接收/入队当成真正听懂 |

公共 Schema/媒体协议和原生设备接口仍须先完成 W-V01 的版本与授权评审。文中逻辑字段不是对当前服务器新增的必填参数。

## 2. W-V00：连接与能力的最小完成契约

### 2.1 配置和数据流安全

保持当前显式配置优先级；仅替换未配置时的默认值为 `http://127.0.0.1:8201/v1`。错误的显式地址必须报告，不试探其他端口后偷偷改用云端。配置明确区分：provider实例、ASR/TTS模型请求名、voice ID、local-only/允许远端策略、凭据引用及超时。

默认不扫描局域网，不把任意hostname当作可信loopback；非loopback端点需经过显式信任/传输安全策略。跨主机重定向不得携带原Authorization头；自动跟随策略应由客户端控制。Keychain或已批准配置提供凭据，日志只记录安全错误分类，不回显token/完整URL参数。

只读探测使用 `/health`、`/readyz`、`/v1/models`、`/v1/voices`，不通过试合成判断是否ready。记录可用状态和实际已披露字段；多次GET只得到legacy视图，不能标成服务原子快照。没有voice-level确证时只发已验证的最低参数集合；请求被拒绝后不得按描述臆测支持。

### 2.2 内部 ProbeReport 建议

记录 `observed_protocol`、服务实例标识或unknown、目录/模型身份或unknown、被选voice的availability、支持参数集合/来源、失败分类与观测时间。另存 `assurance = legacy_observed | revision_pinned`；只有SR-V01/02能力与请求回执共同满足时才可用后者。

状态必须可区分：配置非法、认证失败、不可达、服务未ready、请求模型未列出、voice不可用、参数不支持、身份不明确。健康返回200不自动等于模型可推理；缺少confidence不填1.0。

### 2.3 首个代码增量的测试清单

- 缺省端点对齐；显式旧地址继续保留；非法/空配置不会隐式外呼。
- 未提供ASR confidence为unknown，有来源的数据才保留；检查所有旧调用者和序列化边界，不能只改dataclass却破坏严格v1 DTO。
- light/balanced/quality 的安全目录fixture；Base clone不发送instructions、非1.0 speed或caller seed。
- `/readyz`失败、目录缺voice、模型alias、端点重定向和超时分类；不把缺字段补成支持。
- fake HTTP/WS捕获完整出站参数，断言无额外模型安装、音色注册或云请求。

上述是待编写测试，不是本次已通过项目。独立真实smoke随后在获准的已安装服务执行，并记录实际返回能力；不能拿快照或模拟fixture代替现场结果。

## 3. W-V02：普通 ASR 轮次闭合算法

### 3.1 为什么使用已有栅栏

当前SpeechRail为普通事件维护FIFO handler，`_commit_audio`会等待reader，而clear在清理后返回cleared；历史#10的legacy EOF已采用commit→clear。`previous_item_id`则固定为空。因此起步应固化该已有顺序，而非假设服务器支持自造finish_id，或为取得分人EOF而启用额外模型。

使用条件：独立ASR连接、manual/null、无diarization、一个客户端写队列、一次仅一个未收口input_turn。服务版本需要契约/fixture验证；泛OpenAI兼容服务不自动继承这一保证。

### 3.2 客户端状态与数据

每轮持有：connection_epoch、input_turn_id、本机输入帧范围、client事件账本、committed item顺序、terminal集合、相关errors、finish_requested、barrier_seen、取消标识及绝对本机期限。

- 服务完整sequence先用于连接连续性检查，再把事件分发给assembler；若SDK丢弃未知事件，不能只凭筛选后的序号跳跃判断丢包。
- item按首次committed的服务sequence排序；final异步处理可能乱序，但不得按final回调时间重新排序。
- `(epoch,item_id)`决定正文所属片段。相同event ID/内容可去重；重复ID而内容冲突须失败。同文不同item是两段实际话语，不能按文本去重。
- partial是UI草稿；最终只使用各item的completed全文，不把全部delta再加一次。

正常结束时停止采集，完成重采样尾部处理，将全部append交给同一写队列后，发送commit和clear。网络send完成只表示本机交付给传输层，不代表逐样本服务接收；这里利用FIFO与最终栅栏，不制造采样ACK。

```text
CAPTURING
  → stop capture + drain local append queue
  → enqueue commit
  → enqueue clear
  → FINALIZING（禁止混入下一轮append）
  → cleared AND all observed committed items completed
                AND no relevant error/gap/cancel
  → FINAL_READY，按committed次序合并一次
```

全轮空正文返回EMPTY，不创建Advice。只要有failed/missing、append被拒绝、commit失败、连接关闭或无法消除的顺序缺口，返回INCOMPLETE/FAILED；即使稍后cleared到达也不变成成功。超时不以“先用已经识别的部分”推进世界。

取消分支只丢弃输入并clear或关闭连接，不发布Final。重连使用新epoch，不回放未确认的旧PCM。收口期间再次按PTT：第一版明确显示“正在结束上一段”并要求重试；不能悄悄录入后丢弃，也不能自动把两个建议并成一个。更复杂的有界双缓冲只作为后续独立优化。

### 3.3 可直接翻译为测试的事件轨迹

下列是测试记法，不是新增API；C=committed，F=completed，X=failed/error，B=cleared。

| 轨迹 | 预期判定 |
|---|---|
| C(a), F(a,“先观察”), C(b), F(b,“再敲门”), C(c), F(c,“”), B | 单个Final；保留a、b，空尾c不丢前文 |
| C(a), C(b), F(b,“后段”), F(a,“前段”), B | 按a→b合并，不按final回调次序 |
| C(a), F(a,“好”), C(b), F(b,“好”), B | 两段都保留，不做全文相等去重 |
| C(a), F(a,“前段”), C(b), X(b), B | 失败；不得提交“前段” |
| append error, C(a), F(a,“有内容”), B | 输入不完整；不得因有文本放行 |
| C(a), F(a,“前段”), C(b), B | 缺终态，失败；不继续无限等 |
| C(a), F(a,“”), B | EMPTY，无Advice |
| C(a), F(a,“完整”), connection closed before B | 未证明收口；显式重试，不自动重放PCM |
| cancel requested, B | CANCELLED，无Advice |
| old epoch F(a) after new connection | 丢弃旧事件，不污染新轮次 |

第二条是客户端异步分发防御用例，不宣称当前服务器在同一WS故意逆序。该算法证明协议层的闭合条件，不替代ASR识别质量和源采样级回执。

服务规范/组合回归见[SpeechRail #69](https://github.com/hrygo/SpeechRail/issues/69)。WoM需要独立消费者测试，不能只依赖上游测试。

## 4. W-V03：停止、取消与表达失败分开

| 用户/系统操作 | 立即本机动作 | Engine/Provider动作 | Domain动作 |
|---|---|---|---|
| Pause/Stop | 失效generation、停止/保留可恢复位置 | 暂停或取消对应TTS | 无 |
| Replay/Volume/全局播放rate | 对原take或当前图操作 | 必要时查询原资产 | 无 |
| 新的语音活动 | duck或短暂停止 | 原输入轮次继续判定 | 无，直到确定意图 |
| 明确Cancel pending或确认替换建议 | 停声，旧块拒绝 | 取消表达/关联pending工作 | 同Writer裁决cancel与Commit |
| POST_COMMIT新建议 | 停止当前表达 | 从cursor保留恢复选项 | 创建新turn，不撤销旧事实 |
| TTS/设备失败 | 标记当前媒体失败，保留字幕 | 只重试该表达单元 | 无 |

不能复用一个“取消所有东西”的按钮处理以上情况。UI标签为pre_commit也不能证明Writer尚未提交；迟到取消返回already_committed时保持事实，禁止在客户端模拟回滚。

## 5. 输出完整性、信用与时钟的最小规格

TTS起步每连接一个活动response；严格绑定item/response，不同时消费legacy/current两组音频。适配器将任意网络块重组为采样帧；`sample_count`定义为每声道帧数，所有长度乘法先做上限检查再分配。Provider成功terminal、帧合法、累计计数一致且无错误后，才允许发布完整AudioTake。

媒体UDS使用鉴权控制面给出的单次ticket与engine epoch；验证同用户peer不能代替现有会话/作用域绑定。ticket不进入日志。未知版本、超长header/payload、格式改变和未知关键字段按协商策略拒绝。

接收方建立stream后提供初始credit，后续按实际消费释放信用；零credit时仅暂停CHUNK，不阻止受限FORMAT/END/ERROR/CANCEL控制。控制另有小容量上限与期限，不能以“控制优先”创建无界队列。音频回调不等待credit、网络、actor或文件；只处理已准备缓冲。

WebSocket的全量服务sequence与媒体CHUNK局部seq分离。源帧坐标、设备渲染位置与UI时间分开保存；重采样和播放rate变化需映射。只有估计时记estimated-output；回调或缓存消费完成不宣称扬声器已实际输出。

## 6. 可先行、增强与禁止承诺

| 能力 | 当前可以先交付的范围 | 需要增强后才能保证 |
|---|---|---|
| 真实媒体输入/输出 | 经固定版本验证的双Realtime、PTT、固定批准voice | 完整story_voice还需要真实领域服务 |
| ASR收口 | 上述FIFO栅栏＋逐item错误检查 | SR-V08固化契约；当前不承诺逐样本服务水位 |
| 能力发现 | legacy安全快照与最低参数集合 | SR-V01一致snapshot |
| 人物绑定 | App持久CAS绑定＋冻结批准池＋真实旧take | SR-V02推理时原子voice revision pin |
| 完整缓存 | 已取得合法成功terminal的实际音频 | SR-V03的可核验HTTP/精确渲染身份 |
| 响应速度 | 限定下一单元预取，不在互动中做质检 | SR-V04服务级维护隔离，SR-V05条件特征缓存 |
| 动态新音色 | 准备期候选、人工批准、失败仍用原池 | SR-V06多维证据；201不等于发布 |
| 情绪变化 | 同一声线＋停顿/安全音量/明确降级 | SR-V07研究结果，不作为媒体MVP阻塞 |
| 术语/人名稳定读音 | 上层保存 DisplayText/SpokenText 并做显式规则 | SR-V09版本化词典与span mapping |
| 自动动态选音 | 冻结批准音色池＋已有描述/人工配置 | SR-V10结构化目录与最小披露 |
| 长叙述自然度 | 当前短SpeechUnit＋既有planner | SR-V11跨句韵律/planner契约 |
| 精确字幕/口型 | 句级/单元级时间线 | SR-V12可选TTS timing sidecar；首版不伪造字级时间 |

后续实现PR必须逐项报告：代码完成、服务验证、设备验收、发布验收。软件完成不消除后三级缺口；本次文档不能替代任何一级运行证据。

## 7. 证据索引

SpeechRail链接固定于审查SHA：

- [普通事件FIFO与错误关联](https://github.com/hrygo/SpeechRail/blob/28755de8cc51046f25ce75c7869fe1bacd34752d/src/speechrail/http/routes/realtime_openai.py)
- [commit等待reader及clear实现](https://github.com/hrygo/SpeechRail/blob/28755de8cc51046f25ce75c7869fe1bacd34752d/src/speechrail/application/realtime_openai.py)
- [previous_item_id构造](https://github.com/hrygo/SpeechRail/blob/28755de8cc51046f25ce75c7869fe1bacd34752d/src/speechrail/compatibility/openai_realtime.py)
- [既有rollover/clear回归](https://github.com/hrygo/SpeechRail/blob/28755de8cc51046f25ce75c7869fe1bacd34752d/tests/test_realtime_openai.py)
- [历史语音准入Issue #10及legacy EOF](https://github.com/hrygo/SpeechRail/issues/10)

本文件的错误枚举、内部ProbeReport、客户端算法与测试轨迹属于设计建议，尚未发布为当前SDK接口。
