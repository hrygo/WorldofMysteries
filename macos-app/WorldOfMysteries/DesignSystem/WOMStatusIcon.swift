/// Stable semantic names for platform-standard status icons.
///
/// Generic application states use SF Symbols rather than custom World of Mysteries artwork.
/// World-specific interaction concepts remain in `WOMIconAsset`.
public nonisolated enum WOMStatusIcon: String, CaseIterable, Sendable {
    case info = "info.circle"
    case warning = "exclamationmark.triangle"
    case success = "checkmark.circle"
    case danger = "exclamationmark.octagon"
    case locked = "lock"
    case active = "sparkles"
    case cooldown = "timer"
}
