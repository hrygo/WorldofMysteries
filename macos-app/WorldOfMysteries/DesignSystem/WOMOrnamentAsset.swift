/// Stable semantic names for reusable occult ornament assets.
///
/// These assets provide geometry only. Color, opacity, material and interaction states remain
/// owned by the consuming SwiftUI style so visual semantics continue to come from DesignTokens.
public nonisolated enum WOMOrnamentAsset: String, CaseIterable, Sendable {
    case divider = "wom.ornament.divider"
    case ritualSeal = "wom.ornament.ritual-seal"
    case artifactSlot = "wom.ornament.artifact-slot"
    case sectionFlourish = "wom.ornament.section-flourish"
}
