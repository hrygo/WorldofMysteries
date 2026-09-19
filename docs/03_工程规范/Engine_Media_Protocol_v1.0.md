# Engine Media Protocol v1.0

状态：**W-V01 第一阶段权威协议设计；本提交只定义契约与 fixture，尚未宣称 Python/Swift 运行时已经实现。**

## 1. 目标

语音是高频、大吞吐数据面。现有 `engine_ipc.schema.json` 继续只承担认证后的控制请求、响应与事件；PCM 不进入该 JSON 控制通道，也不使用 Base64。

媒体通道使用独立本地 UDS。控制 IPC 后续通过 `media.open` 类能力签发一次性 grant；grant 至少绑定 engine epoch、stream、direction、scope 与 expiry。媒体连接的第一条 header 必须是 `open` 并提交对应 ticket。ticket 不写日志、不落盘、不作为长期身份凭据。

## 2. Wire framing

每个媒体帧：

```text
0..3    uint32 big-endian header_length
4..7    uint32 big-endian payload_length
8..     header_length bytes UTF-8 JSON header
...     payload_length bytes raw payload
```

硬上限：

- header ≤ 16 KiB；
- raw payload ≤ 256 KiB；
- v1 音频为 mono PCM signed 16-bit little-endian；
- sample rate 仅 16 kHz / 24 kHz / 48 kHz；
- 控制帧 `open / credit / end / cancel / error` 的 payload_length 必须为 0；
- `chunk` 的 `payload_length == payload_bytes == frame_count * 2`。

JSON header 的 Canonical Schema 为 `contracts/protocol/engine_media.schema.json`。未知字段和未知版本默认拒绝，不能用“忽略字段”把 v2 数据解释成 v1。

## 3. Authenticated control grant: `media.open`

`media.open` is an authenticated **control IPC** method, not a media-frame kind. It is advertised by the Engine handshake only when a real media session handler is installed. The current bare Engine CLI remains system-only; it must not advertise a media capability that has no consumer.

Canonical payload schema: `contracts/protocol/engine_media_control.schema.json`.

Request payload:

```json
{
  "direction": "app_to_engine",
  "generation": 4,
  "format": {
    "codec": "pcm_s16le",
    "sample_rate": 16000,
    "channels": 1
  }
}
```

Successful response payload:

```json
{
  "protocol_version": "1.0",
  "socket_path": "<private runtime media UDS>",
  "stream_id": "<server-generated>",
  "trace_id": "<request trace id>",
  "engine_epoch": "<server-generated process/media epoch>",
  "generation": 4,
  "ticket": "<64 lowercase hex, one-time>",
  "direction": "app_to_engine",
  "format": {
    "codec": "pcm_s16le",
    "sample_rate": 16000,
    "channels": 1
  },
  "max_payload_bytes": 65536,
  "initial_credit_bytes": 262144,
  "expires_in_ms": 10000
}
```

Rules:

- The authenticated control session chooses direction, generation and PCM format; the server chooses stream ID, engine epoch, media path, limits and ticket.
- The ticket is a short-lived bearer capability bound to all returned grant metadata. It is consumed **before** the media handler runs; replay and metadata mismatch fail closed.
- Grant tickets are not domain credentials, are not persisted, and must not appear in logs or user-facing diagnostics.
- `socket_path` is returned only to the authenticated local client. It is not a portable asset identifier and never enters Domain state.
- Client and server must reject unknown request/grant fields instead of silently accepting a newer contract.
- The App uses the grant to construct the first binary-channel OPEN header. Only then does the media stream lifecycle begin.

## 4. Stream lifecycle

```text
authenticated control IPC
  → mint one-time media grant
  → connect private media UDS
  → OPEN(ticket, epoch, generation, direction, format)
  → CREDIT / CHUNK*
  → END
```

异常：

```text
OPEN → CHUNK* → CANCEL
OPEN → CHUNK* → ERROR
disconnect before END → incomplete
```

`generation` 是调用方可见的失效代号。用户 stop、supersede、session replacement 时，接收方先提升 generation/丢弃旧队列；迟到的旧 generation CHUNK 不得重新进入播放或 ASR 聚合。

## 5. Sequence、offset 与完整性

- `sequence` 仅属于媒体 CHUNK，首块为 0，逐块 +1；
- `offset_frames` 是该流 PCM 的每声道 frame 坐标；v1 mono 下每 frame = 2 bytes；
- offset 必须连续：下一块 offset = 上一块 offset + frame_count；
- `END.total_frames * 2 == END.total_bytes`；
- 若 END 携带 sha256，其对象是按顺序拼接的**原始 PCM payload bytes**；
- 收到 END 只证明 Engine↔App 媒体流完成，不证明扬声器已经真实输出；设备侧另行维护 DeliveryCursor/PlaybackReceipt。

SpeechRail WebSocket sequence 与本媒体 CHUNK sequence 是两个独立序列，禁止互相套用。

## 6. Backpressure

credit 只计 raw payload bytes。

- receiver 在 OPEN 后通过 initial_credit_bytes 建立初始窗口；
- sender 发送 CHUNK 前必须拥有不少于 payload_length 的 credit，并在发送后扣减；
- receiver 只在真实消费/释放缓冲后增发 CREDIT；
- credit=0 时暂停 CHUNK；
- CANCEL / ERROR / END 等控制帧不消耗 media credit，但实现必须对控制队列另设小容量与 deadline，不能制造无界旁路；
- 音频 render/capture callback 不等待 socket credit、JSON 编码、文件 I/O 或网络。

## 7. 安全边界

- Media UDS 位于 App 创建的私有 runtime 目录，继续遵守现有短 AF_UNIX 路径与 0700/0600 规则；
- peer 同 UID 不是完整授权；ticket 必须与已认证控制 session 和 engine epoch 绑定；
- ticket 一次使用，过期、重放、错误 direction/stream/epoch 均拒绝；
- header/payload 在分配内存前检查长度；
- OPEN 完成后 format 不可变化；若需要新格式必须开新 stream；
- 错误信息不得回显 ticket、PCM、私人文件路径或未授权业务正文。

## 8. v1 范围

v1 只定义安全 transport primitive，不定义：

- 角色选角或 VoiceBinding；
- SpeechRail model/voice 参数；
- 世界 COMMIT / rollback；
- 麦克风设备选择、AEC、播放器；
- “用户已经听懂”的语义；
- 字级时间轴。

这些能力由后续 W-V02/W-V03/W-V04 及 SpeechRail 对应契约承担。

## 9. 跨语言实现门

后续 Python 与 Swift 必须共享 `contracts/fixtures/media/headers.json` 做 parity：

1. 同一 header 的 accept/reject 一致；
2. uint32 big-endian length 行为一致；
3. oversize 在分配前拒绝；
4. CHUNK payload/frame math 一致；
5. control payload 必须为空；
6. generation、sequence、offset 的状态机行为一致；
7. ticket 不出现在 repr/log/error。

在 Python/Swift 实现和对应门禁通过前，本文件不能被解释成“media transport 已上线”。
