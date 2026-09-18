# M2 数据内核首批：事务日志与独立 Outbox 恢复

关联任务 #46，上级产品验收 #43。基准 `main@c219b460c3943d7f68f84b49d1a979dd257e5a33`。
分支 `feat/data-kernel-transactions`。本工作与用户的 macOS 真机验证并行，#55 保留开放。

## 本增量边界

这是持久化基础设施，不是完整 Domain Engine。没有修改 macOS、IPC、模型、语音或打包；
没有自动打开用户数据库、创建真实用户世界，或开放建议提交入口。不会改变用户正在验证的 App。

`DatabaseManager` 提供四库路径隔离、只读 Canon、每世界独占单写队列、独立只读池、
强事务提交/持久幂等/事件日志/Outbox、在线数据库备份。`OutboxProjector` 实现独立事件索引
及从权威日志重建；不是完整 FTS、向量、记忆检索或授权引擎。

## 既定决策及实现

遵守 [数据架构基线](../03_工程规范/Data_Architecture_v1.0.md)，权威世界连接为
WAL / synchronous=FULL / foreign_keys=ON / trusted_schema=OFF，核心表 STRICT。
技能中的 NORMAL 示例与权威基线冲突，本实现取 FULL，不调整既有规范或门禁。

生产默认严格要求 SQLite **3.53.4**。测试可显式注入当前解释器 SQLite 版本以验证兼容行为，
该注入不是环境变量、静默降级或生产启动策略。目标随包版本仍须独立实测，当前不将模块接入启动。
无新依赖，没有修改 `engine/uv.lock`、Python 版本或受保护档案。

四库使用独立物理文件，拒绝同路径、符号链接、硬链接/文件别名与不安全数据库附属文件。
Canon 仅以 URI `mode=ro` 打开，query_only 与 SQL authorizer 双重限制；URI 正确转义中文、
空格、问号和井号。世界 writer 使用稳定锁文件 inode 的排他租约，不删除别人或等待者的锁。
关闭时拒绝新请求，排空已接纳操作；读写在独立线程，不将同步 SQLite 阻塞放在 UI/事件循环上。

## 一次已裁决操作如何落盘

`CommitRequest` 与 `StoredEvent` 是内部持久化参数，不是新 IPC/产品 DTO。
调用方必须先经过既有 Domain Resolver / Validators。AI、App 没有 SQL 或该对象的入口。

先冻结输入并计算语义摘要，随后在同一 world.db 事务中：

1. 查持久幂等记录。相同 key/语义返回原始结果，不执行 repository callback；不同语义冲突。
2. 比较 expected world revision，在新 revision 的同步 repository 回调中写入领域表。
3. 同时保存操作日志、原始结果、带可查询独立头字段的 DomainEvent、Outbox 和世界 revision。
4. COMMIT 完成后才返回。取消或丢失响应不能解释为回滚，重试依靠同一幂等 key 查原结果。

回调仅供受信任 Application/repository 代码，不作为不可信 Python 沙箱。
`DomainTransaction` 不暴露 commit/rollback；SQL authorizer 拒绝回调修改基础设施日志、
改变 PRAGMA、ATTACH、DDL 或控制事务。回调不能 await，也不能逃出写线程/事务生命周期。

没有用一个通用 JSON facts 表替代人物、关系、知识、记忆等专门领域表。
当前测试中的 `test_character` / `test_knowledge` 是测试专用 repository，用于证明原子边界；
生产专门表与 Episode Finalization 的完整写入映射属于下一增量。

## 投影故障与重建

projection 读取一个 world.db 快照，在独立 retrieval.db 事务中写事件索引及 checkpoint，
成功后才由 Domain Writer 更新 Outbox 确认。绝不通过 ATTACH 冒充跨库 WAL 原子事务。

投影 COMMIT 后、确认前崩溃：下次根据已提交 checkpoint 补确认，不重复索引事件。
投影写入失败：世界事实和未处理 Outbox 不回滚；损坏检索库不阻塞权威读取或新提交。
删除检索库后：从所有已提交 DomainEvent 重建，而非只读取尚未确认的 Outbox，防止丢掉旧历史。
显式 rebuild 可修复同源未来 checkpoint；另一个世界的索引或缺失身份的已填充索引均拒绝接管。

投影没有 model-facing 全库搜索 API，不能代替 Context Compiler 的知识边界。
本批只声明事件索引可重建，不声明完整 Canon/Memory/Graph/Vector 投影已经完成。

## 备份、迁移与恢复边界

使用 SQLite Online Backup API 对真实活跃 WAL 数据库生成一致快照，先校验再原子不可覆盖发布。
不是裸复制活跃 world.db；不覆盖已有备份或符号链接。当前仅提供数据库快照，不包含资产清单、
Canon 版本绑定、完整导入/恢复向导或存档升级验收。

初始 migration 只初始化空库。未知/已有旧 schema 拒绝打开，不清空、不覆盖、不猜测迁移。
启动检测 world revision、commit journal 和 Outbox 覆盖一致性；身份丢失不重造历史。
现有数据库的有序升级及升级前完整备份属于后续增量，未冒称完成。

## 验证与变更台账

本地采用真实磁盘库，不是全程 mock。覆盖事务前/后故障、真实子进程 `os._exit`、
并发相同/冲突 key、版本竞争、异步取消、写入中并行读取、关闭排空、完整性与别名拒绝、
在线备份、投影提交/确认窗口及已确认历史重建。进程崩溃测试不等于设备断电耐久性验收。

本地 Python 3.13.5 / SQLite 3.46.1 仅提供显式注入的兼容性证据；FULL_P0 和目标 SQLite pin
结论来自实际目标验证，不能用本地专项代替。目标检查与提交凭单状态同步记录于本 PR。

代码范围限定为数据管理器、私有 schema 引导、Outbox、三份初始 migration、两份回归测试、
本记录与新任务胶囊。没有改既有胶囊、protected profiles、required checks、IPC 或用户正在测的包。
没有合并/自动合并授权。

下一增量：专门领域表及 typed repositories → 原子 Episode/人物/知识/记忆/关系写回 →
Application 编排与实际 IPC 首轮贯通 → Golden 001 五轮及重启连续性。
本增量不自行决定人物自主性、记忆策略、分叉规则或用户可感知变化；这些仍先征询。

## 并发初始化回归

发布后补查复现：不同世界同时首次打开共享 runtime.db 时，旧代码在事务外观察空 schema，
随后第二个 writer 按过期观察重复 CREATE TABLE。现将 schema 身份读取与初始 DDL 放在
同一个 BEGIN IMMEDIATE 锁内，不放宽未知 schema 拒绝条件。回归以两个真实连接在获取
写锁前同步，验证一次初始化、双方成功打开及完整性；不依赖随机 sleep 掩盖竞态。

## 生产激活前的 SQLite 对齐项

首次目标验证实际测得：macOS 测试解释器 SQLite 为 3.50.4，当前锁定 standalone 随包
解释器为 3.53.1，并非规范 3.53.4。完整门禁的行为回归使用显式兼容性注入，不能冒称
生产默认路径已通过。原始版本探测和任务跟踪见 #58；数据库启动默认 pin 不放宽，
模块不接入 App 启动，构建依赖对齐不交给最终用户手工解决。正式激活前必须在符合
规范的随包解释器上、不使用版本覆盖，补齐真实磁盘默认路径验收。

## 验证基准刷新

开发期间 main 合入独立 App 图标更新，推进至 `36fdd9c`。固定旧基准的目标验证被正确拦截，
没有覆盖新图标或把旧验证当成最新结果。本分支以非强推的历史合流保留 main 更新；数据
实现与 `fe83fdd` 相同。新增 revision 3 契约绑定新基准，旧 revision 2 原始字节保留于
`fe83fdd` 的 Git 历史，不回写旧凭单。当前活动契约为
`.agents/capsules/M2-DATA-KERNEL-FOUNDATION-R3.json`，重新生成对应受测 head 的原始凭单。
