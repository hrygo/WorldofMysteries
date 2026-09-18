import Foundation

/// Local Engine 连接状态（界面唯一允许消费的连接事实）。
///
/// 该枚举把「界面能说什么」与「链路真的做了什么」绑定在一起：
/// 只要 IPC 传输仍是骨架实现（`EngineIPCClient.isScaffoldOnly`），状态就只能是
/// `scaffoldPreview`，界面必须明确告诉用户引擎尚未接入，而不得显示「已就绪 · IPC 活跃」。
public enum EngineConnectionState: Sendable, Equatable {
    /// 尚未发起连接。
    case idle
    /// 正在连接。
    case connecting
    /// 传输层仍是骨架通道，未接入真实 Local Engine：界面只能展示示例数据。
    case scaffoldPreview
    /// 真实握手成功。
    case ready
    /// 连接或握手失败。
    case failed(message: String)

    public var isReady: Bool {
        if case .ready = self { return true }
        return false
    }
}
