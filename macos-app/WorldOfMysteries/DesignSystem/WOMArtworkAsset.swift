/// Runtime-sized artwork variants allowed in the compiled Asset Catalog.
///
/// Production masters intentionally have no variant here: they belong to provenance/source
/// storage and must never be loaded by runtime selectors.
public nonisolated enum WOMArtworkVariant: String, CaseIterable, Sendable {
    case sceneRuntime = "runtime"
    case wideHeader = "wide-header"
    case artifactThumbnail = "thumbnail"
    case artifactDetail = "detail"
}

/// Stable semantic identities for the six premium world / scene artwork families.
///
/// The raw value is the primary 2560×1600 runtime Asset Catalog name. Wide header derivatives
/// append `.wide` and remain an explicitly separate payload so hero screens never load masters.
public nonisolated enum WOMWorldArtworkAsset: String, CaseIterable, Sendable {
    case worldHero = "wom.art.world.hero"
    case grayFog = "wom.art.world.gray-fog"
    case ritualAltar = "wom.art.scene.ritual-altar"
    case codexArchive = "wom.art.scene.codex-archive"
    case fateWorldline = "wom.art.scene.fate-worldline"
    case artifactVault = "wom.art.scene.artifact-vault"

    public var runtimeAssetName: String { rawValue }
    public var wideHeaderAssetName: String { "\(rawValue).wide" }

    public func assetName(for variant: WOMArtworkVariant) -> String? {
        switch variant {
        case .sceneRuntime: runtimeAssetName
        case .wideHeader: wideHeaderAssetName
        case .artifactThumbnail, .artifactDetail: nil
        }
    }
}

/// Stable semantic identities for the 15 canonical Artifact artwork families.
///
/// Raw values are identity keys only. Runtime payloads always use `.thumbnail` or `.detail`
/// suffixes, which prevents collection selectors from accidentally decoding a production master.
public nonisolated enum WOMArtifactArtworkAsset: String, CaseIterable, Sendable {
    case probabilityDie = "wom.art.artifact.probability-die"
    case arrodesMirror = "wom.art.artifact.arrodes"
    case alzuhodQuill = "wom.art.artifact.alzuhod-quill"
    case trunsoestBrassBook = "wom.art.artifact.trunsoest-brass-book"
    case magicWishingLamp = "wom.art.artifact.magic-wishing-lamp"
    case creepingHunger = "wom.art.artifact.creeping-hunger"
    case leymanoTravels = "wom.art.artifact.leymano-travels"
    case groselleTravels = "wom.art.artifact.groselle-travels"
    case azikCopperWhistle = "wom.art.artifact.azik-copper-whistle"
    case cardsOfBlasphemy = "wom.art.artifact.cards-of-blasphemy"
    case seaGodScepter = "wom.art.artifact.sea-god-scepter"
    case staffOfStars = "wom.art.artifact.staff-of-stars"
    case boxOfGreatOldOnes = "wom.art.artifact.box-of-great-old-ones"
    case deathKnell = "wom.art.artifact.death-knell"
    case unshadowedCrucifix = "wom.art.artifact.unshadowed-crucifix"

    public var thumbnailAssetName: String { "\(rawValue).thumbnail" }
    public var detailAssetName: String { "\(rawValue).detail" }

    public func assetName(for variant: WOMArtworkVariant) -> String? {
        switch variant {
        case .artifactThumbnail: thumbnailAssetName
        case .artifactDetail: detailAssetName
        case .sceneRuntime, .wideHeader: nil
        }
    }
}
