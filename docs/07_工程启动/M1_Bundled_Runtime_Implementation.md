# M1 随包引擎运行时：实施与证据边界

关联：Issue #53；承接已合并 PR #52，Refs #43/#44/#45。
固定实现基准：`main@b6874c9bc4b753c3321fcce1d4be65a1b5bde514`。

## 目标与用户边界

用户安装 App 后不安装 Python、不运行终端、不复制 token、不自行下载运行时。
App 仅使用包内 `Contents/Resources/LocalEngine`；用户数据和 socket 不写入 Bundle。
本增量不改 Domain/Canon、协议、世界提交、语音、依赖锁文件或最低系统要求。

## 来源与构建

固定输入在 `macos-app/Packaging/python-runtime.lock.json`。来源为
[python-build-standalone 20260901](https://github.com/astral-sh/python-build-standalone/releases/tag/20260901)
的 CPython **3.14.7 标准 GIL、aarch64-apple-darwin install_only_stripped**，
归档 SHA-256 为 `4632cb1a6edad9e73d3c81b6d2e69131637d995173e3e85005df14102b0592ba`。
生产构建不解析 latest；构建阶段校验长度及 SHA-256 后才解包。
归档检查拒绝路径越界、特殊文件、重复条目、过度解压和包外链接。

依赖从未修改的 `engine/uv.lock` 导出完整哈希需求，以锁定版本安装到真实随包解释器。
不复制开发机 venv，不生成指向系统 Python 的链接；保留第三方许可证、锁文件、依赖版本清单。
代码从 Git 跟踪的引擎模块复制，不携带数据库、测试、环境凭据或 pyc。
清单记录输入归档、依赖锁、源提交、已安装分发及签名前文件哈希；签名后原生文件字节变化
不能错误地与签名前哈希作等值声明。最终 ZIP 另有完整 SHA-256。

App 启动前验证清单的 Python、GIL、arm64、AgentScope 与协议版本，以及包内路径。
忽略外部 Python 环境，不写 bytecode。缺失或不兼容运行时明确不可用，绝不静默回退。

## 目标平台工程验证

新增 `BUNDLED_RUNTIME_P0` 只增补工程证据；原有 FULL_P0 四阶段、required checks 和摘要不变。
新档案与工作流的修改权限由本任务不可变胶囊明确限定。

新增只读权限工作流分别执行：

1. 构建实际 Release App，内嵌解释器与锁定依赖，检查每个原生依赖包含 arm64 且不引用构建机路径。
2. 内向外 ad-hoc 签名，保留 App Sandbox、子进程继承与 Hardened Runtime；不关闭 library validation。
3. 将实际 App 放入与构建目录不同的中文/空格路径。独立的临时探针副本使用同一生产 Swift
   进程管理器和客户端验证三次启动、真实鉴权/health、崩溃后重启与 socket 清理。
4. 实际 Release 二进制另行启动，检查真实子进程、引擎崩溃恢复与 App 强退后引擎退出。
   探针副本不会替换最终交付的 Release 可执行文件。
5. 用受限 PATH 和故意无效的 Python 环境变量执行验证，检查 Bundle 启动前后不变及签名完整性。
6. 在精确源提交运行未修改的 FULL_P0 verifier，导出真实凭单与日志；最终凭单提交不改写受测 head。

构建命令的权威入口在受保护档案；产物位于 `.hacf/artifacts/bundled-runtime/`，日志通过 Actions
Artifact 留存，不将二进制或临时输出提交源码 Git。

## 当前证据与明确未完成

首批本地 Linux 打包专项：**51 项通过**。这只证明归档/清单/路径/安全边界等确定性逻辑，
不替代 macOS 编译、原生依赖导入或 sandbox 下的进程运行。
另有 16 项既有生产 Swift–Python 真实跨进程回归在本地通过。目标平台结果以当前候选 Actions 为准。

本工作流只提供 **ad-hoc 工程验证包**，不具备 Developer ID、公证或 Gatekeeper 发行资格。
缺少发布签名身份时不会要求用户关闭系统安全机制，也不会将该包宣称为正式零配置发行包。
`GATE-PACKAGE`、目标用户安装体验、签名公证、升级保留数据和持久世界五轮闭环仍需独立验收。
没有合并、自动合并或公开发行授权。

## macOS 回归增量 1

首个候选 `7fdefa0` 的 Release 构建、固定 CPython 校验与 91 个锁定生产依赖安装已成功；
离线探针错误调用 AgentScope 2.x 不再导出的 `init`，流程已如实失败并保留日志，未上传成功包。
修复为已核对的 `UserMsg` 构造/文本读取，不修改 SDK 版本、不引入模型调用。
原生库检查显式选择 arm64，避免 Universal2 的其他架构标题被当成动态库路径。
本地当前 52 项打包专项通过；macOS 签名、搬迁和实际进程运行仍以新候选为准。
