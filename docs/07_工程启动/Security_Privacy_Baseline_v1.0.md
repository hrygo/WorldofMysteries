# Security & Privacy Baseline v1.0

> **状态**：工程安全基线

## 1. 数据分类

### Domain Private
- world.db
- Character Memory / Knowledge / Belief
- Story history
- user notes
- transcript

### Hidden Narrative
- unrevealed World Truth
- secrets
- future beats
- Canon facts above spoiler scope

### Credentials
- model provider API keys
- account tokens

### Ephemeral
- raw microphone audio by default
- intermediate ASR partials
- transient AgentScope runtime messages unless diagnostics explicitly capture metadata

## 2. Credential Storage

Provider secrets 必须进入 macOS Keychain 或等价受保护凭据存储。

禁止：
- hard-code；
- plaintext config；
- world.db；
- regular logs；
- IPC fixture。

## 3. Microphone

默认：
- raw audio 只用于实时 ASR；
- Story 完成后不保留 raw microphone；
- final transcript 可作为 PlayerAdvice 来源持久化；
- 用户明确启用录音留存时才保存原始音频。

## 3.1 macOS Capability Ownership

SwiftUI / Presentation 进程持有：

- microphone permission；
- audio playback device；
- user-selected file export/import；
- UI notifications（如启用）。

Local Engine 持有：

- App Container / Application Support 中的 Domain data；
- outbound network client（仅在调用 cloud provider 时）；
- bundled local model/runtime resources。

Local Engine 不直接申请麦克风权限，不直接访问任意用户文件系统路径。

## 4. Cloud Model Egress

只有 Context Compiler 生成的 Authorized ContextPacket 可进入 cloud provider。

禁止发送：
- 完整 world.db；
- 未授权 hidden truth；
- 与当前任务无关的 Character Memory；
- raw API keys；
-完整 debug dump。

每次 ModelRequest 记录：
- task type；
- provider；
- context packet id/hash；
- data classification；
- prompt/schema/model revision。

## 5. Logs / Trace

Release：
- metadata first；
- 默认不保存完整 Prompt；
- 默认不保存完整 Hidden Truth；
- error details redact credentials / private text；
- user diagnostics export 先脱敏。

Debug 可提高记录粒度，但必须显式开发配置，不能随 Release 开启。

## 6. Local Files

Domain data 位于当前用户 Application Support。

Socket、runtime lock 等只允许当前用户访问。

Assets 使用相对路径与 hash，禁止任意 path traversal。

## 7. Backup / Export

World Export 明确包含：
- world.db snapshot；
- required assets；
- manifest；
- schema version；
- Canon Pack compatibility metadata。

默认不包含：
- API keys；
- runtime diagnostics；
- retrieval.db；
- raw microphone cache。

## 8. Delete World

删除世界应覆盖：
- authoritative world data；
- assets；
- snapshots；
- derived retrieval projections；
- runtime caches referencing that world。

删除后不要求修改共享 Canon Pack。

## 9. Crash / Diagnostics

Crash report 禁止包含：
- API key；
-完整 ContextPacket；
- hidden truth payload；
- raw user transcript unless user explicitly submits diagnostic context。

## 10. Release Gate

`GATE-SECURITY = PASS`：

- Keychain verified；
- IPC current-user only；
- no public TCP listener；
- raw audio default ephemeral；
- cloud egress authorization test；
- log redaction tests；
- export excludes credentials；
- delete-world test；
- diagnostic bundle redaction test。
