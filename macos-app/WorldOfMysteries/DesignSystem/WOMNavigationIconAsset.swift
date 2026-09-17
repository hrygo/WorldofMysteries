/// World-specific navigation icons that should not fall back to generic SF Symbols.
///
/// System-level destinations such as Settings and Gallery intentionally remain SF Symbols;
/// these cases cover only narrative-domain concepts that benefit from a distinct WOM silhouette.
public nonisolated enum WOMNavigationIconAsset: String, CaseIterable, Sendable {
    case character = "wom.icon.character"
    case fate = "wom.icon.fate"
    case worldline = "wom.icon.worldline"
    case notes = "wom.icon.notes"
}
