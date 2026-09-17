import Foundation
import Observation

// MARK: - Probability Die

public enum ProbabilityDieFace: Int, CaseIterable, Codable, Identifiable, Sendable {
  case one = 1
  case two
  case three
  case four
  case five
  case six

  public var id: Int { rawValue }

  public var bias: ProbabilityBias {
    switch self {
    case .one: return .extremeAdverse
    case .two: return .strongAdverse
    case .three: return .adverse
    case .four: return .favorable
    case .five: return .strongFavorable
    case .six: return .extremeFavorable
    }
  }
}

public enum ProbabilityBias: String, Codable, Sendable {
  case extremeAdverse
  case strongAdverse
  case adverse
  case favorable
  case strongFavorable
  case extremeFavorable

  public var localizedTitle: String {
    switch self {
    case .extremeAdverse: return "极端不利"
    case .strongAdverse: return "强烈不利"
    case .adverse: return "不利"
    case .favorable: return "有利"
    case .strongFavorable: return "强烈有利"
    case .extremeFavorable: return "极端有利"
    }
  }

  public var tone: MysticTone {
    switch self {
    case .extremeAdverse, .strongAdverse, .adverse: return .crimson
    case .favorable, .strongFavorable, .extremeFavorable: return .teal
    }
  }
}

public struct ProbabilityDieArtifactState: Codable, Hashable, Sendable {
  public var awakening: Double
  public var resentment: Double
  public var sealed: Bool
  public var lastFace: ProbabilityDieFace?

  public init(
    awakening: Double = 0, resentment: Double = 0, sealed: Bool = false,
    lastFace: ProbabilityDieFace? = nil
  ) {
    self.awakening = min(max(awakening, 0), 1)
    self.resentment = min(max(resentment, 0), 1)
    self.sealed = sealed
    self.lastFace = lastFace
  }
}

public struct ProbabilityDieRollRequest: Codable, Hashable, Sendable {
  public var requestID: UUID
  public var context: ArtifactContext
  public var stakes: ArtifactRiskBand
  public var artifactState: ProbabilityDieArtifactState

  public init(
    requestID: UUID = UUID(), context: ArtifactContext, stakes: ArtifactRiskBand,
    artifactState: ProbabilityDieArtifactState
  ) {
    self.requestID = requestID
    self.context = context
    self.stakes = stakes
    self.artifactState = artifactState
  }
}

public struct ProbabilityDieResolution: Codable, Hashable, Sendable {
  public var requestID: UUID
  public var rollID: UUID
  public var face: ProbabilityDieFace
  public var deterministicSeed: UInt64
  public var affectedEventIDs: [String]
  public var resultingArtifactState: ProbabilityDieArtifactState
  public var autonomousRerollArmed: Bool

  public init(
    requestID: UUID,
    rollID: UUID = UUID(),
    face: ProbabilityDieFace,
    deterministicSeed: UInt64,
    affectedEventIDs: [String] = [],
    resultingArtifactState: ProbabilityDieArtifactState,
    autonomousRerollArmed: Bool = false
  ) {
    self.requestID = requestID
    self.rollID = rollID
    self.face = face
    self.deterministicSeed = deterministicSeed
    self.affectedEventIDs = affectedEventIDs
    self.resultingArtifactState = resultingArtifactState
    self.autonomousRerollArmed = autonomousRerollArmed
  }
}

public protocol ProbabilityDieResolving: Sendable {
  func resolve(_ request: ProbabilityDieRollRequest) async throws -> ProbabilityDieResolution
}

public struct ProbabilityDieRollRecord: Identifiable, Sendable {
  public let id: UUID
  public let timestamp: Date
  public let face: ProbabilityDieFace
  public let rollID: UUID
  public let autonomous: Bool

  public init(
    id: UUID = UUID(), timestamp: Date = .now, face: ProbabilityDieFace, rollID: UUID,
    autonomous: Bool
  ) {
    self.id = id
    self.timestamp = timestamp
    self.face = face
    self.rollID = rollID
    self.autonomous = autonomous
  }
}

@Observable
@MainActor
public final class ProbabilityDieModel {
  public enum Phase: Equatable {
    case dormant
    case requesting
    case rolling
    case revealed(ProbabilityDieFace)
    case sealed
    case error(String)
  }

  public private(set) var phase: Phase
  public private(set) var artifactState: ProbabilityDieArtifactState
  public private(set) var currentResolution: ProbabilityDieResolution?
  public private(set) var history: [ProbabilityDieRollRecord] = []
  public private(set) var presentationRevision = 0
  public private(set) var throwVector = CGSize.zero

  private let resolver: any ProbabilityDieResolving

  public init(
    artifactState: ProbabilityDieArtifactState = .init(), resolver: any ProbabilityDieResolving
  ) {
    self.artifactState = artifactState
    self.resolver = resolver
    self.phase = artifactState.sealed ? .sealed : .dormant
  }

  public var canRoll: Bool {
    switch phase {
    case .dormant, .revealed: return !artifactState.sealed
    default: return false
    }
  }

  public func roll(context: ArtifactContext, stakes: ArtifactRiskBand, throwVector: CGSize = .zero)
    async
  {
    guard canRoll else { return }
    self.throwVector = throwVector
    phase = .requesting

    do {
      let resolution = try await resolver.resolve(
        .init(context: context, stakes: stakes, artifactState: artifactState))
      guard !Task.isCancelled else { return }
      currentResolution = resolution
      artifactState = resolution.resultingArtifactState
      phase = .rolling
      presentationRevision += 1
      try? await Task.sleep(for: .milliseconds(1050))
      guard !Task.isCancelled else { return }
      history.append(.init(face: resolution.face, rollID: resolution.rollID, autonomous: false))
      if history.count > 16 { history.removeFirst(history.count - 16) }
      phase = .revealed(resolution.face)
    } catch {
      phase = .error(error.localizedDescription)
    }
  }

  public func resetPresentation() {
    guard !artifactState.sealed else {
      phase = .sealed
      return
    }
    currentResolution = nil
    phase = .dormant
  }
}

public struct PreviewProbabilityDieResolver: ProbabilityDieResolving {
  public init() {}

  public func resolve(_ request: ProbabilityDieRollRequest) async throws -> ProbabilityDieResolution
  {
    try await Task.sleep(for: .milliseconds(180))
    let seed = stableSeed(
      request.requestID.uuidString + request.context.worldlineID
        + String(request.context.storyRevision ?? 0))
    let face = ProbabilityDieFace(rawValue: Int(seed % 6) + 1) ?? .one
    var next = request.artifactState
    let pressure: Double
    switch request.stakes {
    case .low: pressure = 0.02
    case .guarded: pressure = 0.035
    case .high: pressure = 0.055
    case .extreme: pressure = 0.08
    }
    next.awakening = min(1, next.awakening + pressure)
    next.lastFace = face
    return .init(
      requestID: request.requestID,
      face: face,
      deterministicSeed: seed,
      resultingArtifactState: next,
      autonomousRerollArmed: next.awakening >= 0.7
    )
  }

  private func stableSeed(_ text: String) -> UInt64 {
    var hash: UInt64 = 14_695_981_039_346_656_037
    for byte in text.utf8 {
      hash ^= UInt64(byte)
      hash &*= 1_099_511_628_211
    }
    return hash
  }
}

// MARK: - Alzuhod Quill

public struct AlzuhodArtifactState: Codable, Hashable, Sendable {
  public var awakening: Double
  public var exposure: Double
  public var narrativeDebt: Double
  public var sealed: Bool

  public init(
    awakening: Double = 0, exposure: Double = 0, narrativeDebt: Double = 0, sealed: Bool = true
  ) {
    self.awakening = min(max(awakening, 0), 1)
    self.exposure = min(max(exposure, 0), 1)
    self.narrativeDebt = max(0, narrativeDebt)
    self.sealed = sealed
  }
}

public enum QuillHorizon: String, CaseIterable, Codable, Sendable {
  case immediate
  case scene
  case episode

  public var localizedTitle: String {
    switch self {
    case .immediate: return "当前"
    case .scene: return "场景"
    case .episode: return "本篇"
    }
  }
}

public struct QuillCausalStep: Identifiable, Codable, Hashable, Sendable {
  public enum Visibility: String, Codable, Sendable { case visible, hiddenUntilTriggered }
  public var id: String
  public var summary: String
  public var plausibility: Double
  public var visibility: Visibility

  public init(id: String, summary: String, plausibility: Double, visibility: Visibility = .visible)
  {
    self.id = id
    self.summary = summary
    self.plausibility = min(max(plausibility, 0), 1)
    self.visibility = visibility
  }
}

public struct QuillDraft: Identifiable, Codable, Hashable, Sendable {
  public var id: UUID
  public var openingSentence: String
  public var coherence: Double
  public var risk: ArtifactRiskBand
  public var predictedDebt: Double
  public var causalSteps: [QuillCausalStep]
  public var constraints: [String]

  public init(
    id: UUID = UUID(), openingSentence: String, coherence: Double, risk: ArtifactRiskBand,
    predictedDebt: Double, causalSteps: [QuillCausalStep], constraints: [String]
  ) {
    self.id = id
    self.openingSentence = openingSentence
    self.coherence = min(max(coherence, 0), 1)
    self.risk = risk
    self.predictedDebt = max(0, predictedDebt)
    self.causalSteps = causalSteps
    self.constraints = constraints
  }
}

public struct QuillWriteRequest: Codable, Hashable, Sendable {
  public var context: ArtifactContext
  public var desiredOutcome: String
  public var horizon: QuillHorizon
  public var riskTolerance: ArtifactRiskBand
  public var artifactState: AlzuhodArtifactState
}

public struct QuillCommitResult: Codable, Hashable, Sendable {
  public var committedRevision: Int?
  public var autonomousSentence: String?
  public var resultingArtifactState: AlzuhodArtifactState
}

public protocol AlzuhodQuillOrchestrating: Sendable {
  func draft(_ request: QuillWriteRequest) async throws -> QuillDraft
  func commit(draftID: UUID, context: ArtifactContext, artifactState: AlzuhodArtifactState)
    async throws -> QuillCommitResult
}

@Observable
@MainActor
public final class AlzuhodQuillModel {
  public enum Phase: Equatable {
    case sealed, dormant, editing, drafting, awaitingConfirmation, writing, resolved, backlash
    case error(String)
  }

  public var desiredOutcome = ""
  public var horizon: QuillHorizon = .scene
  public var riskTolerance: ArtifactRiskBand = .high
  public private(set) var phase: Phase
  public private(set) var artifactState: AlzuhodArtifactState
  public private(set) var draft: QuillDraft?
  public private(set) var commitResult: QuillCommitResult?

  private let orchestrator: any AlzuhodQuillOrchestrating

  public init(
    artifactState: AlzuhodArtifactState = .init(), orchestrator: any AlzuhodQuillOrchestrating
  ) {
    self.artifactState = artifactState
    self.orchestrator = orchestrator
    self.phase = artifactState.sealed ? .sealed : .dormant
  }

  public var canDraft: Bool {
    !artifactState.sealed
      && desiredOutcome.trimmingCharacters(in: .whitespacesAndNewlines).count >= 4
      && phase != .drafting && phase != .writing
  }

  public func beginEditing() {
    guard !artifactState.sealed else {
      phase = .sealed
      return
    }
    phase = .editing
  }

  public func requestDraft(context: ArtifactContext) async {
    guard canDraft else { return }
    phase = .drafting
    do {
      draft = try await orchestrator.draft(
        .init(
          context: context,
          desiredOutcome: desiredOutcome.trimmingCharacters(in: .whitespacesAndNewlines),
          horizon: horizon, riskTolerance: riskTolerance, artifactState: artifactState))
      phase = .awaitingConfirmation
    } catch {
      phase = .error(error.localizedDescription)
    }
  }

  public func commit(context: ArtifactContext) async {
    guard let draft else { return }
    phase = .writing
    do {
      let result = try await orchestrator.commit(
        draftID: draft.id, context: context, artifactState: artifactState)
      commitResult = result
      artifactState = result.resultingArtifactState
      phase = result.autonomousSentence == nil ? .resolved : .backlash
    } catch {
      phase = .error(error.localizedDescription)
    }
  }

  public func discardDraft() {
    draft = nil
    commitResult = nil
    phase = artifactState.sealed ? .sealed : .editing
  }
}

public struct PreviewAlzuhodQuillOrchestrator: AlzuhodQuillOrchestrating {
  public init() {}

  public func draft(_ request: QuillWriteRequest) async throws -> QuillDraft {
    try await Task.sleep(for: .milliseconds(260))
    return .init(
      openingSentence: "很快，一件看似偶然的小事会让现实朝你写下的方向移动。",
      coherence: 0.78,
      risk: request.riskTolerance,
      predictedDebt: request.artifactState.narrativeDebt + 1.2,
      causalSteps: [
        .init(id: "visible.1", summary: "一个既有关系被重新触发。", plausibility: 0.88),
        .init(
          id: "hidden.1", summary: "某个参与者在不知道被操纵的情况下做出合理选择。", plausibility: 0.82,
          visibility: .hiddenUntilTriggered),
      ],
      constraints: ["不能改写已提交的过去", "不能绕过 Canon / Capability / Knowledge Gate"]
    )
  }

  public func commit(draftID: UUID, context: ArtifactContext, artifactState: AlzuhodArtifactState)
    async throws -> QuillCommitResult
  {
    try await Task.sleep(for: .milliseconds(320))
    var next = artifactState
    next.awakening = min(1, next.awakening + 0.08)
    next.exposure = min(1, next.exposure + 0.06)
    next.narrativeDebt += 1.2
    return .init(
      committedRevision: context.storyRevision.map { $0 + 1 },
      autonomousSentence: next.awakening >= 0.7 ? "而它又自行补写了一句关于你的话。" : nil,
      resultingArtifactState: next
    )
  }
}
