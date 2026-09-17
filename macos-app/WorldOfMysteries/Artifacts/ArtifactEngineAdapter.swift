import Foundation

// MARK: - Local Engine IPC Bridge

/// Artifact gameplay stays inside the existing UDS IPC boundary.
/// The macOS App never commits artifact effects itself; it only sends typed
/// requests and renders typed resolutions returned by the Local Engine.
public struct EngineArtifactActionResolver: ArtifactActionResolving {
  private let client: EngineIPCClient

  public init(client: EngineIPCClient) {
    self.client = client
  }

  public func resolve(_ request: ArtifactActionRequest) async throws -> ArtifactActionResolution {
    let response = try await client.send(
      envelope: IPCEnvelope(
        kind: "request",
        traceId: UUID().uuidString,
        requestId: request.requestID.uuidString,
        idempotencyKey: request.idempotencyKey,
        method: ArtifactIPCMethod.method(for: request.artifactID, action: request.action),
        payload: try ArtifactIPCCodec.payload(from: request)
      )
    )

    return try ArtifactIPCCodec.decodeResponse(response, as: ArtifactActionResolution.self)
  }
}

public struct EngineProbabilityDieResolver: ProbabilityDieResolving {
  private let client: EngineIPCClient

  public init(client: EngineIPCClient) {
    self.client = client
  }

  public func resolve(_ request: ProbabilityDieRollRequest) async throws -> ProbabilityDieResolution
  {
    // Presentation-owned meters are deliberately not authoritative input.
    // The engine resolves the real artifact state from world.db/session state.
    let payload = ProbabilityDieIPCRequest(
      requestID: request.requestID,
      context: request.context,
      stakes: request.stakes
    )

    let response = try await client.send(
      envelope: IPCEnvelope(
        kind: "request",
        traceId: UUID().uuidString,
        requestId: request.requestID.uuidString,
        idempotencyKey: request.requestID.uuidString,
        method: "artifact.probability_die.resolve",
        payload: try ArtifactIPCCodec.payload(from: payload)
      )
    )

    return try ArtifactIPCCodec.decodeResponse(response, as: ProbabilityDieResolution.self)
  }
}

public struct EngineAlzuhodQuillOrchestrator: AlzuhodQuillOrchestrating {
  private let client: EngineIPCClient

  public init(client: EngineIPCClient) {
    self.client = client
  }

  public func draft(_ request: QuillWriteRequest) async throws -> QuillDraft {
    // The engine owns the authoritative 0-08 state. The UI snapshot is omitted
    // from the production IPC request to avoid client-side state becoming truth.
    let payload = QuillDraftIPCRequest(
      context: request.context,
      desiredOutcome: request.desiredOutcome,
      horizon: request.horizon,
      riskTolerance: request.riskTolerance
    )
    let requestID = UUID()

    let response = try await client.send(
      envelope: IPCEnvelope(
        kind: "request",
        traceId: UUID().uuidString,
        requestId: requestID.uuidString,
        idempotencyKey: requestID.uuidString,
        method: "artifact.alzuhod.draft",
        payload: try ArtifactIPCCodec.payload(from: payload)
      )
    )

    return try ArtifactIPCCodec.decodeResponse(response, as: QuillDraft.self)
  }

  public func commit(
    draftID: UUID,
    context: ArtifactContext,
    artifactState _: AlzuhodArtifactState
  ) async throws -> QuillCommitResult {
    let requestID = UUID()
    let payload = QuillCommitIPCRequest(
      draftID: draftID,
      context: context,
      expectedStoryRevision: context.storyRevision
    )

    let response = try await client.send(
      envelope: IPCEnvelope(
        kind: "request",
        traceId: UUID().uuidString,
        requestId: requestID.uuidString,
        idempotencyKey: requestID.uuidString,
        method: "artifact.alzuhod.commit",
        payload: try ArtifactIPCCodec.payload(from: payload)
      )
    )

    return try ArtifactIPCCodec.decodeResponse(response, as: QuillCommitResult.self)
  }
}

// MARK: - Stable IPC Method Mapping

public enum ArtifactIPCMethod {
  public static func method(for artifactID: ArtifactID, action: ArtifactActionKind) -> String {
    switch (artifactID, action) {
    case (.arrodesMirror, .ask):
      return "artifact.arrodes.ask"
    case (.arrodesMirror, .answerExchange):
      return "artifact.arrodes.answer_exchange"
    case (.arrodesMirror, .refuseExchange):
      return "artifact.arrodes.refuse_exchange"

    case (.trunsoestBrassBook, .enactRule):
      return "artifact.trunsoest.enact_rule"
    case (.magicWishingLamp, .wish):
      return "artifact.wishing_lamp.wish"

    case (.creepingHunger, .graze):
      return "artifact.creeping_hunger.graze"
    case (.creepingHunger, .invokeSoul):
      return "artifact.creeping_hunger.invoke_soul"

    case (.leymanoTravels, .recordAbility):
      return "artifact.leymano.record"
    case (.leymanoTravels, .invokeRecordedAbility):
      return "artifact.leymano.invoke"

    case (.groselleTravels, .enterBookWorld):
      return "artifact.groselle.enter"
    case (.groselleTravels, .exitBookWorld):
      return "artifact.groselle.exit"

    case (.azikCopperWhistle, .sendLetter):
      return "artifact.azik_whistle.send"
    case (.cardsOfBlasphemy, .unlockLore):
      return "artifact.blasphemy_card.unlock"

    case (.seaGodScepter, .answerPrayer):
      return "artifact.sea_god.answer_prayer"
    case (.seaGodScepter, .invokeAuthority):
      return "artifact.sea_god.invoke_authority"

    case (.staffOfStars, .projectLocation):
      return "artifact.staff_of_stars.project"
    case (.boxOfGreatOldOnes, .openLayer):
      return "artifact.old_ones_box.open_layer"

    case (.deathKnell, .targetWeakness):
      return "artifact.death_knell.target_weakness"
    case (.deathKnell, .fireWeaknessShot):
      return "artifact.death_knell.fire"

    case (.unshadowedCrucifix, .purify):
      return "artifact.unshadowed_crucifix.purify"

    default:
      return "artifact.\(artifactID.rawValue).\(action.rawValue)"
    }
  }
}

// MARK: - Payload Codec

private enum ArtifactIPCCodec {
  static func payload<T: Encodable>(from value: T) throws -> [String: AnyCodableValue] {
    let data = try JSONEncoder().encode(value)
    return try JSONDecoder().decode([String: AnyCodableValue].self, from: data)
  }

  static func decodeResponse<T: Decodable>(_ response: IPCEnvelope, as type: T.Type) throws -> T {
    guard response.status == "ok" else {
      if let error = response.error {
        throw ArtifactIPCError.engine(code: error.code, message: error.message)
      }
      throw ArtifactIPCError.engine(code: "artifact_ipc_error", message: "Local Engine 拒绝了特殊物品请求。")
    }

    guard let value = try response.decodePayload(as: type) else {
      throw ArtifactIPCError.missingPayload(method: response.method)
    }
    return value
  }
}

private struct ProbabilityDieIPCRequest: Codable, Sendable {
  let requestID: UUID
  let context: ArtifactContext
  let stakes: ArtifactRiskBand
}

private struct QuillDraftIPCRequest: Codable, Sendable {
  let context: ArtifactContext
  let desiredOutcome: String
  let horizon: QuillHorizon
  let riskTolerance: ArtifactRiskBand
}

private struct QuillCommitIPCRequest: Codable, Sendable {
  let draftID: UUID
  let context: ArtifactContext
  let expectedStoryRevision: Int?
}

public enum ArtifactIPCError: Error, LocalizedError, Sendable {
  case missingPayload(method: String?)
  case engine(code: String, message: String)

  public var errorDescription: String? {
    switch self {
    case .missingPayload(let method):
      return "Local Engine 尚未返回 \(method ?? "artifact") 的类型化 payload。"
    case .engine(let code, let message):
      return "\(message) [\(code)]"
    }
  }
}
