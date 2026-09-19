import SwiftUI

/// Presentation context only. Gameplay, resolver and Domain state are unchanged by this value.
public enum ArtifactPresentationContext: Sendable, Equatable {
  case standard
  case vaultExhibit
}

public enum ArtifactExhibitionArchetype: String, CaseIterable, Sendable, Equatable {
  case fateInstrument
  case oracleAndArchive
  case spatialRelic
  case authorityAndCombat
  case ruleAndPurification

  public var localizedTitle: String {
    switch self {
    case .fateInstrument: "命运仪器"
    case .oracleAndArchive: "神谕与档案"
    case .spatialRelic: "空间遗物"
    case .authorityAndCombat: "权柄与战斗器具"
    case .ruleAndPurification: "规则与净化遗物"
    }
  }
}

public enum ArtifactMountStyle: String, CaseIterable, Sendable, Equatable {
  case framedSquare
  case plinthSquare
  case bookCradle
  case suspendedSquare
  case ritualTray

  public var systemImage: String {
    switch self {
    case .framedSquare: "rectangle.center.inset.filled"
    case .plinthSquare: "square.stack.3d.up"
    case .bookCradle: "book.closed"
    case .suspendedSquare: "sparkles"
    case .ritualTray: "seal"
    }
  }
}

public struct ArtifactStageAnchor: Sendable, Equatable {
  public let horizontalBias: Double
  public let verticalBias: Double

  public init(horizontalBias: Double = 0, verticalBias: Double = 0) {
    self.horizontalBias = min(max(horizontalBias, -0.18), 0.18)
    self.verticalBias = min(max(verticalBias, -0.18), 0.18)
  }

  public static let center = Self()
}

public struct ArtifactPresentationAssetCapabilities: Sendable, Equatable {
  public let subjectMask: Bool
  public let coarseDepth: Bool
  public let contactShadow: Bool
  public let rimLight: Bool

  public init(
    subjectMask: Bool = false,
    coarseDepth: Bool = false,
    contactShadow: Bool = true,
    rimLight: Bool = true
  ) {
    self.subjectMask = subjectMask
    self.coarseDepth = coarseDepth
    self.contactShadow = contactShadow
    self.rimLight = rimLight
  }

  public static let fallback = Self()
}

public enum ArtifactEnvironmentToken: String, CaseIterable, Sendable, Equatable {
  case obsidian
  case brass
  case azure
  case teal
  case amber
  case ritual
}

/// Presentation-only metadata. This intentionally does not duplicate ArtifactDescriptor data.
public struct ArtifactPresentationProfile: Sendable, Equatable {
  public let artifactID: ArtifactID
  public let archetype: ArtifactExhibitionArchetype
  public let mount: ArtifactMountStyle
  public let stageAnchor: ArtifactStageAnchor
  public let artworkVariant: WOMArtworkVariant
  public let assetCapabilities: ArtifactPresentationAssetCapabilities
  public let environmentToken: ArtifactEnvironmentToken
  public let relatedIDs: [ArtifactID]

  public init(
    artifactID: ArtifactID,
    archetype: ArtifactExhibitionArchetype,
    mount: ArtifactMountStyle,
    stageAnchor: ArtifactStageAnchor = .center,
    artworkVariant: WOMArtworkVariant = .artifactDetail,
    assetCapabilities: ArtifactPresentationAssetCapabilities = .fallback,
    environmentToken: ArtifactEnvironmentToken = .obsidian,
    relatedIDs: [ArtifactID] = []
  ) {
    self.artifactID = artifactID
    self.archetype = archetype
    self.mount = mount
    self.stageAnchor = stageAnchor
    self.artworkVariant = artworkVariant
    self.assetCapabilities = assetCapabilities
    self.environmentToken = environmentToken
    self.relatedIDs = relatedIDs
  }
}

public enum ArtifactPresentationProfiles {
  public static let all: [ArtifactPresentationProfile] = ArtifactRegistry.all.map {
    makeProfile(for: $0.id)
  }

  private static let byID: [ArtifactID: ArtifactPresentationProfile] =
    Dictionary(uniqueKeysWithValues: all.map { ($0.artifactID, $0) })

  public static func profile(for id: ArtifactID) -> ArtifactPresentationProfile {
    byID[id] ?? fallbackProfile(for: id)
  }

  private static func makeProfile(for id: ArtifactID) -> ArtifactPresentationProfile {
    switch id {
    case .probabilityDie:
      .init(
        artifactID: id, archetype: .fateInstrument, mount: .plinthSquare,
        stageAnchor: .init(verticalBias: 0.04),
        assetCapabilities: .init(subjectMask: true, coarseDepth: true),
        environmentToken: .azure, relatedIDs: [.alzuhodQuill, .magicWishingLamp])
    case .arrodesMirror:
      .init(
        artifactID: id, archetype: .oracleAndArchive, mount: .framedSquare,
        stageAnchor: .init(verticalBias: -0.02),
        assetCapabilities: .init(subjectMask: true, coarseDepth: true),
        environmentToken: .azure, relatedIDs: [.cardsOfBlasphemy, .leymanoTravels])
    case .alzuhodQuill:
      .init(
        artifactID: id, archetype: .fateInstrument, mount: .bookCradle,
        stageAnchor: .init(horizontalBias: -0.03, verticalBias: 0.02),
        assetCapabilities: .init(subjectMask: true, coarseDepth: true),
        environmentToken: .amber, relatedIDs: [.probabilityDie, .trunsoestBrassBook])
    case .trunsoestBrassBook:
      .init(
        artifactID: id, archetype: .ruleAndPurification, mount: .bookCradle,
        stageAnchor: .init(verticalBias: 0.05),
        assetCapabilities: .init(subjectMask: true, coarseDepth: false),
        environmentToken: .brass, relatedIDs: [.unshadowedCrucifix, .leymanoTravels])
    case .magicWishingLamp:
      .init(
        artifactID: id, archetype: .fateInstrument, mount: .plinthSquare,
        stageAnchor: .init(verticalBias: 0.05),
        assetCapabilities: .init(subjectMask: true, coarseDepth: true),
        environmentToken: .amber, relatedIDs: [.probabilityDie, .arrodesMirror])
    case .creepingHunger:
      .init(
        artifactID: id, archetype: .authorityAndCombat, mount: .plinthSquare,
        assetCapabilities: .init(subjectMask: true, coarseDepth: true),
        environmentToken: .ritual, relatedIDs: [.seaGodScepter, .deathKnell])
    case .leymanoTravels:
      .init(
        artifactID: id, archetype: .oracleAndArchive, mount: .bookCradle,
        stageAnchor: .init(verticalBias: 0.04),
        assetCapabilities: .init(subjectMask: true, coarseDepth: false),
        environmentToken: .teal, relatedIDs: [.groselleTravels, .cardsOfBlasphemy])
    case .groselleTravels:
      .init(
        artifactID: id, archetype: .spatialRelic, mount: .bookCradle,
        stageAnchor: .init(verticalBias: 0.04),
        assetCapabilities: .init(subjectMask: true, coarseDepth: true),
        environmentToken: .azure, relatedIDs: [.staffOfStars, .boxOfGreatOldOnes])
    case .azikCopperWhistle:
      .init(
        artifactID: id, archetype: .ruleAndPurification, mount: .ritualTray,
        stageAnchor: .init(horizontalBias: 0.02, verticalBias: 0.06),
        assetCapabilities: .init(subjectMask: true, coarseDepth: false),
        environmentToken: .teal, relatedIDs: [.unshadowedCrucifix, .seaGodScepter])
    case .cardsOfBlasphemy:
      .init(
        artifactID: id, archetype: .oracleAndArchive, mount: .framedSquare,
        stageAnchor: .init(verticalBias: 0.02),
        assetCapabilities: .init(subjectMask: true, coarseDepth: false),
        environmentToken: .brass, relatedIDs: [.arrodesMirror, .leymanoTravels])
    case .seaGodScepter:
      .init(
        artifactID: id, archetype: .authorityAndCombat, mount: .plinthSquare,
        stageAnchor: .init(verticalBias: 0.04),
        assetCapabilities: .init(subjectMask: true, coarseDepth: true),
        environmentToken: .azure, relatedIDs: [.creepingHunger, .staffOfStars])
    case .staffOfStars:
      .init(
        artifactID: id, archetype: .spatialRelic, mount: .suspendedSquare,
        stageAnchor: .init(verticalBias: -0.03),
        assetCapabilities: .init(subjectMask: true, coarseDepth: true),
        environmentToken: .azure, relatedIDs: [.groselleTravels, .boxOfGreatOldOnes])
    case .boxOfGreatOldOnes:
      .init(
        artifactID: id, archetype: .spatialRelic, mount: .suspendedSquare,
        stageAnchor: .init(verticalBias: 0.02),
        assetCapabilities: .init(subjectMask: true, coarseDepth: true),
        environmentToken: .amber, relatedIDs: [.staffOfStars, .groselleTravels])
    case .deathKnell:
      .init(
        artifactID: id, archetype: .authorityAndCombat, mount: .plinthSquare,
        stageAnchor: .init(horizontalBias: 0.03, verticalBias: 0.04),
        assetCapabilities: .init(subjectMask: true, coarseDepth: true),
        environmentToken: .ritual, relatedIDs: [.creepingHunger, .seaGodScepter])
    case .unshadowedCrucifix:
      .init(
        artifactID: id, archetype: .ruleAndPurification, mount: .ritualTray,
        stageAnchor: .init(verticalBias: 0.03),
        assetCapabilities: .init(subjectMask: true, coarseDepth: false),
        environmentToken: .brass, relatedIDs: [.trunsoestBrassBook, .azikCopperWhistle])
    }
  }

  private static func fallbackProfile(for id: ArtifactID) -> ArtifactPresentationProfile {
    .init(artifactID: id, archetype: .oracleAndArchive, mount: .framedSquare)
  }
}

private struct ArtifactPresentationContextKey: EnvironmentKey {
  static let defaultValue: ArtifactPresentationContext = .standard
}

public extension EnvironmentValues {
  var artifactPresentationContext: ArtifactPresentationContext {
    get { self[ArtifactPresentationContextKey.self] }
    set { self[ArtifactPresentationContextKey.self] = newValue }
  }
}
