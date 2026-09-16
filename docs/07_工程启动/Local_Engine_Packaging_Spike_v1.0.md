# Local Engine Packaging Spike v1.0

> **状态**：P0 技术验证规格  
> **目标**：证明 Python 3.14.7（CPython standard GIL build） / AgentScope Local Engine 能作为 macOS App 的受控本地 helper 随包分发。

## 1. 产品拓扑

```text
MysteriousWorld.app
├── SwiftUI App Process
└── Bundled Local Engine
    ├── Python Runtime
    ├── AgentScope
    ├── Domain Engine
    └── locked Python dependencies
```

Engine 不是用户安装的系统服务，不要求系统 Python。

## 2. Spike 输入

最小 Engine 只实现：

```text
handshake
health
structured_test
crash_test
shutdown
```

`structured_test` 经 AgentScope 执行一个受 Pydantic Schema 约束的模型调用或可注入 mock provider。

## 3. 必须验证

### Runtime
- arm64 Python runtime 可启动；
- `agentscope` import 成功；
- native Python dependencies 可加载；
- Engine working directory 与资源路径稳定；
- locale / UTF-8 / 中文路径稳定。

### Process
- App 启动 Engine；
- Engine PID 可追踪；
- Engine unexpected exit 可检测；
- App 不因 Engine crash 退出；
- Engine restart 后重新 handshake；
- 同一 App 不产生重复 Engine 实例；
- App exit 时 Engine 在 grace period 内退出。

### Security / Distribution
- App Sandbox；
- bundled child process 继承父 App sandbox；
- Engine 与其 Python/native dependencies 全部纳入签名验证；
- Hardened Runtime；
- code signing；
- notarization flow；
- cloud model 访问所需 outbound network entitlement 明确；
- 麦克风权限由 SwiftUI / Audio Device 层持有，Local Engine 不直接采集麦克风；
- 导出文件通过用户授权的文件访问路径完成；
- runtime files 只写 Application Support / App Container 允许目录；
- socket 权限仅允许当前用户。

### Upgrade
- App version 与 Engine version 同包升级；
- protocol compatibility check；
- world.db 不位于 App bundle；
- App 替换不删除用户世界。

## 4. 进程实现基线

MVP 默认由 SwiftUI App 使用受控 child-process 方式启动 bundle 内 Engine executable；child process 继承 App sandbox。

XPC 只在需要不同 sandbox entitlement、独立 privilege boundary 或 launchd-managed lifecycle 时作为 supervisor/packaging 形态使用。无论采用哪种 supervisor，Domain IPC Contract、Engine Code 和 `world.db` ownership 均保持不变。

Python bundling 工具属于实现细节，产品 Contract 不依赖具体工具。

最终实现必须：

```text
No system Python dependency
No pip install after App install
No user-managed daemon
No listening public TCP port
```

## 5. 测试场景

### P001 Cold Start
全新进程启动，记录：

- App ready timestamp；
- Engine process spawned；
- UDS listening；
- handshake complete。

### P002 Engine Crash
收到 `crash_test` 后 Engine 非正常退出。

预期：
- App 存活；
- UI 可进入恢复状态；
- helper restart；
- handshake；
- world state 无损。

### P003 App Force Quit
App 被强制退出。

预期：
- Engine 不长期孤儿运行；
- 下次启动可清理 stale socket / lock。

### P004 Invalid Engine
Engine binary/runtime 缺失或版本不兼容。

预期：
- 产品显示可诊断错误；
- 不尝试打开写入 world.db。

### P005 Upgrade
模拟旧 world data + 新 App / Engine。

预期：
- handshake 成功；
- migration gate 在 DB open 前执行；
- backup/snapshot policy 生效。

## 6. Evidence

Gate evidence：

```text
release build artifact
codesign verification output
notarization result / equivalent release validation
engine dependency lock
cold-start metrics
crash/restart test log
protocol handshake fixture
```

## 7. PASS

`GATE-PACKAGE = PASS`：

1. Release configuration 在目标 Apple Silicon Mac 启动。
2. 用户无需 Python 环境。
3. AgentScope 能正常 import / initialize。
4. UDS 通信稳定。
5. Engine crash 不导致 App crash。
6. Engine 可重启。
7. 用户 Domain 数据位于 Bundle 外。
8. 签名/沙盒/发布配置不存在架构阻塞项。
