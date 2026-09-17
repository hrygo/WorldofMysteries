/// Stable semantic names for World of Mysteries visual assets.
///
/// Asset Catalog filenames are intentionally hidden behind this registry so call sites do not
/// grow ad-hoc string literals. Rendering and interaction policy belongs to `WOMIcon`.
public nonisolated enum WOMIconAsset: String, CaseIterable, Sendable {
    case world = "wom.icon.world"
    case ritual = "wom.icon.ritual"
    case codex = "wom.icon.codex"
    case artifact = "wom.icon.artifact"
    case character = "wom.icon.character"
    case clue = "wom.icon.clue"
    case inventory = "wom.icon.inventory"
    case settings = "wom.icon.settings"
    case divination = "wom.icon.divination"
    case spirituality = "wom.icon.spirituality"
    case grayFog = "wom.icon.grayfog"
    case seal = "wom.icon.seal"
    case card = "wom.icon.card"
}
