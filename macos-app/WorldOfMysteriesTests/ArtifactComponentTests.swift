import Foundation
import Testing

@testable import WorldOfMysteriesCore

@Suite("Canon Artifact Component Integration")
struct ArtifactComponentTests {
  @Test("Artifact registry contains fifteen unique gameplay components")
  func registryCoverage() {
    #expect(ArtifactRegistry.all.count == 15)
    #expect(Set(ArtifactRegistry.all.map(\.id)).count == 15)
    #expect(
      ArtifactRegistry.all.allSatisfy { !$0.displayName.isEmpty && !$0.shortGameplay.isEmpty })
  }

  @Test("Artifact visual semantics reuse the shared MysticTone taxonomy")
  func unifiedToneTaxonomy() {
    let allowed = Set(MysticTone.allCases.map(\.rawValue))
    let artifactTones = Set(ArtifactRegistry.all.map { $0.tone.rawValue })
    #expect(artifactTones.isSubset(of: allowed))
    #expect(!artifactTones.isEmpty)
  }

  @Test("Probability die faces preserve favorable and adverse direction")
  func probabilityFaceSemantics() {
    #expect(ProbabilityDieFace.one.bias == .extremeAdverse)
    #expect(ProbabilityDieFace.two.bias == .strongAdverse)
    #expect(ProbabilityDieFace.three.bias == .adverse)
    #expect(ProbabilityDieFace.four.bias == .favorable)
    #expect(ProbabilityDieFace.five.bias == .strongFavorable)
    #expect(ProbabilityDieFace.six.bias == .extremeFavorable)
    #expect(ProbabilityDieFace.one.bias.tone == .crimson)
    #expect(ProbabilityDieFace.six.bias.tone == .teal)
  }

  @Test("Artifact state meters clamp to normalized gameplay ranges")
  func meterClamping() {
    let die = ProbabilityDieArtifactState(awakening: 2, resentment: -1)
    #expect(die.awakening == 1)
    #expect(die.resentment == 0)

    let quill = AlzuhodArtifactState(awakening: 2, exposure: -1, narrativeDebt: -10, sealed: false)
    #expect(quill.awakening == 1)
    #expect(quill.exposure == 0)
    #expect(quill.narrativeDebt == 0)
  }

  @Test("Artifact action request binds idempotency and expected revision")
  func actionEnvelopeSemantics() {
    let context = ArtifactContext(
      worldID: "world",
      worldlineID: "main",
      storySessionID: "story",
      storyRevision: 12,
      actorID: "character"
    )
    let request = ArtifactActionRequest(
      artifactID: .arrodesMirror,
      action: .ask,
      context: context,
      input: "这里发生过什么？"
    )

    #expect(!request.idempotencyKey.isEmpty)
    #expect(request.expectedStoryRevision == 12)
    #expect(request.context.worldlineID == "main")
  }

  @Test("Arrodes preview returns observation before equivalent exchange")
  func arrodesPreviewSemantics() async throws {
    let resolver = PreviewArtifactResolver()
    let context = ArtifactContext(worldID: "world", worldlineID: "main", storyRevision: 3)
    let result = try await resolver.resolve(
      .init(
        artifactID: .arrodesMirror,
        action: .ask,
        context: context,
        input: "Morris 隐瞒了什么？"
      )
    )

    #expect(result.disposition == .observation)
    #expect(result.state == "exchange_due")
    #expect(result.followUpPrompt != nil)
    #expect(result.meters["exchangeDebt"] != nil)
  }

  @Test("Forbidden third layer remains rejected in preview semantics")
  func forbiddenBoxLayer() async throws {
    let resolver = PreviewArtifactResolver()
    let context = ArtifactContext(worldID: "world", worldlineID: "main", storyRevision: 3)
    let result = try await resolver.resolve(
      .init(
        artifactID: .boxOfGreatOldOnes,
        action: .openLayer,
        context: context,
        stringParameters: ["layer": "3"]
      )
    )

    #expect(result.disposition == .rejected)
    #expect(result.state == "forbidden")
    #expect(result.severity == .dangerous)
  }

  @Test("Quill draft keeps hard gates visible and does not mutate the world")
  func quillDraftSemantics() async throws {
    let orchestrator = PreviewAlzuhodQuillOrchestrator()
    let context = ArtifactContext(worldID: "world", worldlineID: "main", storyRevision: 7)
    let draft = try await orchestrator.draft(
      .init(
        context: context,
        desiredOutcome: "让目标合理离开诊所十分钟",
        horizon: .scene,
        riskTolerance: .high,
        artifactState: .init(sealed: false)
      )
    )

    #expect(!draft.openingSentence.isEmpty)
    #expect(draft.constraints.contains { $0.contains("不能改写已提交的过去") })
    #expect(draft.causalSteps.contains { $0.visibility == .hiddenUntilTriggered })
  }

  @Test("All five artifact families are represented")
  func familyCoverage() {
    let families = Set(ArtifactRegistry.all.map(\.family.rawValue))
    #expect(families.count == ArtifactFamily.allCases.count)
  }
}

@Suite("Artifact IPC Integration")
struct ArtifactIPCIntegrationTests {
  @Test("Stable IPC method mapping covers core artifact actions")
  func methodMapping() {
    #expect(
      ArtifactIPCMethod.method(for: .arrodesMirror, action: .ask)
        == "artifact.arrodes.ask")
    #expect(
      ArtifactIPCMethod.method(for: .trunsoestBrassBook, action: .enactRule)
        == "artifact.trunsoest.enact_rule")
    #expect(
      ArtifactIPCMethod.method(for: .magicWishingLamp, action: .wish)
        == "artifact.wishing_lamp.wish")
    #expect(
      ArtifactIPCMethod.method(for: .deathKnell, action: .fireWeaknessShot)
        == "artifact.death_knell.fire")
  }

  @Test("Production adapter does not invent an engine payload")
  func adapterFailsClosedWhenEngineHasNoTypedPayload() async throws {
    let client = EngineIPCClient()
    try await client.connect(socketPath: "/tmp/world_of_mysteries_test.sock")
    let resolver = EngineArtifactActionResolver(client: client)
    let context = ArtifactContext(worldID: "world", worldlineID: "main", storyRevision: 1)

    do {
      _ = try await resolver.resolve(
        .init(
          artifactID: .arrodesMirror,
          action: .ask,
          context: context,
          input: "这里发生过什么？"
        )
      )
      Issue.record("Expected the production adapter to fail closed without a typed engine payload")
    } catch let error as ArtifactIPCError {
      switch error {
      case .missingPayload:
        break
      case .engine:
        Issue.record("Expected missingPayload, got engine error: \(error)")
      }
    }

    await client.disconnect()
  }
}

@Suite("Artifact Fate Surface Runtime")
struct ArtifactFateSurfaceRuntimeTests {
  @Test("Disconnected app uses explicit non-persistent preview mode")
  func previewWhenEngineIsOffline() {
    #expect(
      ArtifactRuntimeAvailability.resolve(engineReady: false, hasActiveContext: false)
        == .preview)
  }

  @Test("Connected engine without world context fails closed")
  func connectedWithoutContextIsUnavailable() {
    #expect(
      ArtifactRuntimeAvailability.resolve(engineReady: true, hasActiveContext: false)
        == .unavailable)
  }

  @Test("Connected engine with active world context enables live artifact actions")
  func liveRequiresEngineAndContext() {
    #expect(
      ArtifactRuntimeAvailability.resolve(engineReady: true, hasActiveContext: true)
        == .live)
  }

  @MainActor
  @Test("AppState clears artifact context on shutdown")
  func appStateContextLifecycle() async {
    let state = AppState()
    state.updateActiveArtifactContext(
      .init(
        worldID: "world",
        worldlineID: "main",
        storySessionID: "story",
        storyRevision: 9,
        actorID: "actor"
      )
    )
    #expect(state.activeArtifactContext?.storyRevision == 9)

    await state.shutdown()
    #expect(state.activeArtifactContext == nil)
  }
}
