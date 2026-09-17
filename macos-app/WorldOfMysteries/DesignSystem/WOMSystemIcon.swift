/// Stable semantic names for platform-standard action icons.
///
/// World-specific concepts live in `WOMIconAsset` as custom vector assets. Standard macOS
/// actions intentionally use SF Symbols so controls preserve platform familiarity, optical
/// alignment and accessibility behavior instead of duplicating system glyphs in Assets.xcassets.
public nonisolated enum WOMSystemIcon: String, CaseIterable, Sendable {
    case add = "plus"
    case remove = "minus"
    case edit = "pencil"
    case search = "magnifyingglass"
}
