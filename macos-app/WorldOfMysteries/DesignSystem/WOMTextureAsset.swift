/// Semantic bridge for texture assets that already exist in the app catalog.
///
/// The raw values intentionally preserve the current Asset Catalog names so this migration does
/// not duplicate heavyweight textures. `semanticKey` is the stable design-system vocabulary that
/// future asset renames can preserve without touching component call sites.
public nonisolated enum WOMTextureAsset: String, CaseIterable, Sendable {
    case grayFogSoft = "TextureFoolVeil"
    case agedGold = "TextureGold"
    case parchment = "TextureParchment"
    case sacredSlate = "TextureSacredSlate"
    case velvet = "TextureVelvet"

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
