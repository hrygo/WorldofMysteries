/// Semantic bridge for texture assets that already exist in the app catalog.
///
/// Raw values preserve the current Asset Catalog names so the visual-system migration never
/// duplicates heavyweight texture files. `semanticKey` is the stable design-system vocabulary
/// that future catalog renames can preserve without touching component call sites.
public nonisolated enum WOMTextureAsset: String, CaseIterable, Sendable {
    case grayFogSoft = "TextureFoolVeil"
    case agedGold = "TextureGold"
    case parchment = "TextureParchment"
    case sacredSlate = "TextureSacredSlate"
    case velvet = "TextureVelvet"

    /// Compatibility aliases used by the Wave B component vocabulary.
    public static var foolVeil: Self { .grayFogSoft }
    public static var gold: Self { .agedGold }

    public var semanticKey: String {
        switch self {
        case .grayFogSoft: "wom.texture.grayfog.soft"
        case .agedGold: "wom.texture.metal.aged-gold"
        case .parchment: "wom.texture.parchment.subtle"
        case .sacredSlate: "wom.texture.slate.sacred"
        case .velvet: "wom.texture.velvet.dark"
        }
    }
}
