/// Stable semantic names for reusable World of Mysteries texture assets.
///
/// The current catalog still contains several legacy asset names. Call sites use this registry
/// so future catalog renames can happen without spreading string literals through SwiftUI views.
public nonisolated enum WOMTextureAsset: String, CaseIterable, Sendable {
    case parchment = "TextureParchment"
    case gold = "TextureGold"
    case foolVeil = "TextureFoolVeil"
    case sacredSlate = "TextureSacredSlate"
    case velvet = "TextureVelvet"
}
