import Testing
@testable import WorldOfMysteries

@Suite("Visual System Semantic Contracts")
struct VisualSystemSemanticTests {
    @Test("WOM icon size scale remains 16/20/24/32")
    func iconSizeScale() {
        #expect(WOMIconSize.compact.points == 16)
        #expect(WOMIconSize.standard.points == 20)
        #expect(WOMIconSize.prominent.points == 24)
        #expect(WOMIconSize.large.points == 32)
    }

    @Test("platform action icon semantics stay mapped to stable SF Symbols")
    func systemIconMappings() {
        #expect(WOMSystemIcon.add.rawValue == "plus")
        #expect(WOMSystemIcon.remove.rawValue == "minus")
        #expect(WOMSystemIcon.edit.rawValue == "pencil")
        #expect(WOMSystemIcon.search.rawValue == "magnifyingglass")
        #expect(WOMSystemIcon.close.rawValue == "xmark")
        #expect(WOMSystemIcon.back.rawValue == "chevron.left")
        #expect(WOMSystemIcon.favorite.rawValue == "star")
        #expect(WOMSystemIcon.more.rawValue == "ellipsis")
        #expect(WOMSystemIcon.gallery.rawValue == "square.grid.2x2")
        #expect(WOMSystemIcon.settings.rawValue == "gearshape")
    }

    @Test("status icon semantics stay platform-native")
    func statusIconMappings() {
        #expect(WOMStatusIcon.warning.rawValue == "exclamationmark.triangle")
        #expect(WOMStatusIcon.success.rawValue == "checkmark.circle")
        #expect(WOMStatusIcon.locked.rawValue == "lock")
        #expect(WOMStatusIcon.active.rawValue == "sparkles")
        #expect(WOMStatusIcon.cooldown.rawValue == "timer")
    }

    @Test("texture aliases preserve the pre-Wave-B API and semantic keys")
    func textureCompatibility() {
        #expect(WOMTextureAsset.foolVeil.rawValue == WOMTextureAsset.grayFogSoft.rawValue)
        #expect(WOMTextureAsset.gold.rawValue == WOMTextureAsset.agedGold.rawValue)
        #expect(WOMTextureAsset.grayFogSoft.semanticKey == "wom.texture.grayfog.soft")
        #expect(WOMTextureAsset.agedGold.semanticKey == "wom.texture.metal.aged-gold")
        #expect(WOMTextureAsset.parchment.semanticKey == "wom.texture.parchment.subtle")
        #expect(WOMTextureAsset.sacredSlate.semanticKey == "wom.texture.slate.sacred")
        #expect(WOMTextureAsset.velvet.semanticKey == "wom.texture.velvet.dark")
    }

    @Test("world-specific icon registry contains Wave B semantics")
    func worldIconRegistry() {
        let values = Set(WOMIconAsset.allCases.map(\.rawValue))
        let required: Set<String> = [
            "wom.icon.world",
            "wom.icon.ritual",
            "wom.icon.codex",
            "wom.icon.artifact",
            "wom.icon.character",
            "wom.icon.clue",
            "wom.icon.inventory",
            "wom.icon.settings",
            "wom.icon.divination",
            "wom.icon.spirituality",
            "wom.icon.grayfog",
            "wom.icon.seal",
            "wom.icon.card",
        ]

        #expect(required.isSubset(of: values))
    }

    @Test("all nine primary navigation entries use the intended typed icon source")
    func navigationIconSources() {
        #expect(iconSourceKey(NavigationItem.world.iconSource) == "asset:wom.icon.world")
        #expect(iconSourceKey(NavigationItem.character.iconSource) == "navigation:wom.icon.character")
        #expect(iconSourceKey(NavigationItem.fate.iconSource) == "navigation:wom.icon.fate")
        #expect(iconSourceKey(NavigationItem.storyBook.iconSource) == "asset:wom.icon.codex")
        #expect(iconSourceKey(NavigationItem.cards.iconSource) == "asset:wom.icon.card")
        #expect(iconSourceKey(NavigationItem.worldline.iconSource) == "navigation:wom.icon.worldline")
        #expect(iconSourceKey(NavigationItem.notes.iconSource) == "navigation:wom.icon.notes")
        #expect(iconSourceKey(NavigationItem.gallery.iconSource) == "system:square.grid.2x2")
        #expect(iconSourceKey(NavigationItem.settings.iconSource) == "system:gearshape")
    }

    private func iconSourceKey(_ source: WOMIconSource) -> String {
        switch source {
        case .asset(let asset):
            "asset:\(asset.rawValue)"
        case .navigation(let asset):
            "navigation:\(asset.rawValue)"
        case .system(let icon):
            "system:\(icon.rawValue)"
        case .status(let icon):
            "status:\(icon.rawValue)"
        }
    }
}
