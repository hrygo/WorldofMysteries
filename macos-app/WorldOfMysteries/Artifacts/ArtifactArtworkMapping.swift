/// Presentation-only mapping from the authoritative 15 Artifact IDs to premium artwork identity.
///
/// Gameplay truth remains owned by `ArtifactRegistry` and the engine. This mapping is deliberately
/// one-way: artwork can follow Artifact identity, but artwork never becomes a resolver or domain
/// source of truth.
public extension ArtifactID {
    var artworkAsset: WOMArtifactArtworkAsset {
        switch self {
        case .probabilityDie: .probabilityDie
        case .arrodesMirror: .arrodesMirror
        case .alzuhodQuill: .alzuhodQuill
        case .trunsoestBrassBook: .trunsoestBrassBook
        case .magicWishingLamp: .magicWishingLamp
        case .creepingHunger: .creepingHunger
        case .leymanoTravels: .leymanoTravels
        case .groselleTravels: .groselleTravels
        case .azikCopperWhistle: .azikCopperWhistle
        case .cardsOfBlasphemy: .cardsOfBlasphemy
        case .seaGodScepter: .seaGodScepter
        case .staffOfStars: .staffOfStars
        case .boxOfGreatOldOnes: .boxOfGreatOldOnes
        case .deathKnell: .deathKnell
        case .unshadowedCrucifix: .unshadowedCrucifix
        }
    }
}
