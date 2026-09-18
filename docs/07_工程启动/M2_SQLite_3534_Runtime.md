# M2 Data SQLite 3.53.4 Runtime Alignment

关联：#58、#46、#53；实现基准 `main@a44665acbde40561f10edd1ed7b67eaad0a98d4c`。

## 目标

数据架构固定 Runtime SQLite `3.53.4`，且不得依赖 macOS 系统 SQLite。现有
python-build-standalone CPython 3.14.7 内建 `_sqlite3` 使用 3.53.1，因此生产数据层不能直接使用它。
本增量保持 CPython 3.14.7 standard GIL、arm64 和 AgentScope 2.0.8 不变，只新增一个数据层私有
`_wom_sqlite3` 扩展。

## 构建模型

构建阶段固定下载两个公开上游源包：

- Python 3.14.7 官方 XZ 源码，用于取得与解释器 ABI 完全一致的 `Modules/_sqlite` 绑定源码；
- SQLite 3.53.4 官方 amalgamation，用于提供数据内核的 SQLite C 实现。

两者均以固定 URL 和摘要验证。SQLite 同时验证发布页给出的 archive SHA3-256 与 `sqlite3.c` SHA3-256。
构建器只对 CPython `module.c` 做两个可审计的私有命名替换：模块名 `_sqlite3` → `_wom_sqlite3`，
初始化符号 `PyInit__sqlite3` → `PyInit__wom_sqlite3`；其余绑定源码保持上游 3.14.7 原文。
SQLite 静态进入该扩展，因此最终模块不依赖 macOS 系统 libsqlite3。

扩展必须实际探测并通过：SQLite 3.53.4、STRICT、WAL、FULL durability 所需基础能力、FTS5 trigram、
Online Backup API，以及规定的 FTS/RTREE/GEOPOLY/percentile/threadsafe 编译特性。来源摘要、编译特性和
扩展相对路径写入 `runtime-manifest.json`。

## 运行时边界

`engine/infrastructure/sqlite_runtime.py` 是数据持久化唯一驱动接缝：随包 Release 优先加载
`_wom_sqlite3`；普通开发/CI 环境可退回 stdlib sqlite3 仅用于兼容性测试。`DatabaseManager.open()`
在未显式注入测试版本时同时要求“私有驱动 + 精确 3.53.4”，因此不存在系统 SQLite 恰好同版本便被误当生产
路径的情况。

这不改变 Domain、IPC、用户数据模型和现有 migration；也不要求最终用户安装 Python/SQLite 或执行命令。
新 `.so` 属于产品原生签名面，后续 #55 必须与 App、Python 及其他 native extensions 使用同一真实 Team ID；
本任务不通过关闭 Library Validation 绕过该要求。

## 明确边界

- 本任务解决 SQLite 3.53.4 的**构建和数据驱动对齐**，不等于 #55 Developer ID/公证已经完成；
- 不改变四库隔离、single-writer、Outbox、提交即命运等已合并语义；
- 不把 stdlib SQLite 3.53.1 从 CPython 中删除；它可以被其他三方包内部使用，但权威数据内核只走私有驱动；
- 不接入人物/记忆领域表，也不宣称 Golden 001 首轮或五轮已完成。
