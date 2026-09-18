import Foundation

/// Connection facts are distinct from world/model/voice capability and demo content.
public nonisolated enum EngineConnectionState: Sendable, Equatable {
    case idle
    case connecting
    /// Explicit previews only; production no longer simulates a connection.
    case scaffoldPreview
    /// This build has no bundled executable. Never fall back to a user-installed Python.
    case unavailable
    /// Authenticated, healthy system transport; world APIs are not yet available.
    case transportReady
    /// A real health response and capability negotiation both advertise world access.
    case ready
    case failed(message: String)

    public var isReady: Bool {
        if case .ready = self { return true }
        return false
    }
}
