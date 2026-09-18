/// Stable semantic names for platform-standard UI icons.
///
/// World-specific concepts live in custom vector registries. Standard macOS actions and
/// platform destinations intentionally use SF Symbols so controls preserve platform familiarity,
/// optical alignment and accessibility behavior.
public nonisolated enum WOMSystemIcon: String, CaseIterable, Sendable {
    case add = "plus"
    case remove = "minus"
    case edit = "pencil"
    case search = "magnifyingglass"
    case close = "xmark"
    case back = "chevron.left"
    case favorite = "star"
    case more = "ellipsis"
    case refresh = "arrow.triangle.2.circlepath"
    case retry = "arrow.counterclockwise"
    case gallery = "square.grid.2x2"
    case settings = "gearshape"
    case sidebarCollapse = "sidebar.left"
    case sidebarExpand = "sidebar.right"
    case voiceAdvice = "waveform.badge.mic"
    case audioReplay = "speaker.wave.2.fill"
}
