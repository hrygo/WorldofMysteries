import Testing

@testable import WorldOfMysteriesCore

@Suite("Artifact IPC Semantic Coverage")
struct ArtifactIPCSemanticCoverageTests {
  @Test("Every registered non-specialized artifact action resolves to a stable IPC method")
  func stableMappingsRemainIntentional() {
    let pairs: [(ArtifactID, ArtifactActionKind, String)] = [
      (.arrodesMirror, .ask, "artifact.arrodes.ask"),
      (.arrodesMirror, .answerExchange, "artifact.arrodes.answer_exchange"),
      (.arrodesMirror, .refuseExchange, "artifact.arrodes.refuse_exchange"),
      (.trunsoestBrassBook, .enactRule, "artifact.trunsoest.enact_rule"),
      (.magicWishingLamp, .wish, "artifact.wishing_lamp.wish"),
      (.creepingHunger, .graze, "artifact.creeping_hunger.graze"),
      (.creepingHunger, .invokeSoul, "artifact.creeping_hunger.invoke_soul"),
      (.leymanoTravels, .recordAbility, "artifact.leymano.record"),
      (.leymanoTravels, .invokeRecordedAbility, "artifact.leymano.invoke"),
      (.groselleTravels, .enterBookWorld, "artifact.groselle.enter"),
      (.groselleTravels, .exitBookWorld, "artifact.groselle.exit"),
      (.azikCopperWhistle, .sendLetter, "artifact.azik_whistle.send"),
      (.cardsOfBlasphemy, .unlockLore, "artifact.blasphemy_card.unlock"),
      (.seaGodScepter, .answerPrayer, "artifact.sea_god.answer_prayer"),
      (.seaGodScepter, .invokeAuthority, "artifact.sea_god.invoke_authority"),
      (.staffOfStars, .projectLocation, "artifact.staff_of_stars.project"),
      (.boxOfGreatOldOnes, .openLayer, "artifact.old_ones_box.open_layer"),
      (.deathKnell, .targetWeakness, "artifact.death_knell.target_weakness"),
      (.deathKnell, .fireWeaknessShot, "artifact.death_knell.fire"),
      (.unshadowedCrucifix, .purify, "artifact.unshadowed_crucifix.purify"),
    ]

    for (artifactID, action, expected) in pairs {
      #expect(ArtifactIPCMethod.method(for: artifactID, action: action) == expected)
    }
  }
}
