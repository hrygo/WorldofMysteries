import Foundation

/// What makes a thrown die worth watching rather than merely correct: it has to tumble,
/// settle at a readable pace, stay inside the engraved circle and come to rest flat.
nonisolated public struct DiePresentationGate: Sendable, Equatable {
  public var minimumBounces: Int = 2
  /// Measured presentation window for the current 16 mm die and tray: the trajectory is
  /// visibly active for roughly 0.20–0.56 s across the seeded throw family.
  public var settleWindow: ClosedRange<Double> = 0.22...0.62
  public var maximumApex: Double = 0.18
  public var minimumFaceUpAlignment: Double = 0.995
  public var maximumLateralDrift: Double = 0.12

  public init() {}

  public static let standard = DiePresentationGate()

  public func accepts(_ outcome: DieRollOutcome) -> Bool {
    outcome.bounces >= minimumBounces
      && settleWindow.contains(outcome.settledTime)
      && outcome.apex <= maximumApex
      && outcome.faceUpAlignment >= minimumFaceUpAlignment
      && outcome.lateralDrift <= maximumLateralDrift
  }
}

nonisolated public struct DieRollPlan: Sendable {
  public var committedFace: ProbabilityDieFace
  public var outcome: DieRollOutcome
  public var candidatesEvaluated: Int
  /// True when the simulated die really does come to rest on the committed face.
  public var landsOnCommittedFace: Bool
  /// True when the search had to relax the presentation gate to find a throw. The roll is
  /// still real physics; it simply tumbles less prettily than the gate asks for.
  public var relaxedPresentationGate: Bool
}

/// Selects one throw out of the family of physically legal ones.
///
/// The committed face is never written into the simulation. The planner only decides *which*
/// honest throw to show, which is what keeps "commit first, present second" true while the
/// die still tumbles like a real object.
nonisolated public struct DieRollPlanner: Sendable {
  public var solver: DieRigidBodySolver
  public var gate: DiePresentationGate
  public var maximumCandidates: Int

  public init(
    solver: DieRigidBodySolver = DieRigidBodySolver(),
    gate: DiePresentationGate = .standard,
    maximumCandidates: Int = 96
  ) {
    self.solver = solver
    self.gate = gate
    self.maximumCandidates = maximumCandidates
  }

  /// Returns the throw to present, or `nil` when no candidate settled at all inside the
  /// budget (which the caller must treat as "no physical presentation available", never as a
  /// licence to invent one).
  public func plan(
    committedFace: ProbabilityDieFace, seed: UInt64,
    throwInput: DieThrowInput = .neutral
  ) -> DieRollPlan? {
    var bestFallback: DieRollOutcome?
    var bestScore = -Double.greatestFiniteMagnitude
    var evaluated = 0

    for attempt in 0..<max(maximumCandidates, 1) {
      let candidateSeed = DieRollPlanner.candidateSeed(base: seed, attempt: attempt)
      guard let outcome = solver.simulate(seed: candidateSeed, throwInput: throwInput) else {
        continue
      }
      evaluated += 1

      if outcome.face == committedFace, gate.accepts(outcome) {
        return DieRollPlan(
          committedFace: committedFace, outcome: outcome, candidatesEvaluated: attempt + 1,
          landsOnCommittedFace: true, relaxedPresentationGate: false)
      }

      let score = DieRollPlanner.score(outcome, committedFace: committedFace, gate: gate)
      if score > bestScore {
        bestScore = score
        bestFallback = outcome
      }
    }

    guard let fallback = bestFallback else { return nil }
    return DieRollPlan(
      committedFace: committedFace, outcome: fallback, candidatesEvaluated: evaluated,
      landsOnCommittedFace: fallback.face == committedFace,
      relaxedPresentationGate: !gate.accepts(fallback))
  }

  static func candidateSeed(base: UInt64, attempt: Int) -> UInt64 {
    var sampler = DieSampler(
      seed: base &+ (0x9E37_79B9_7F4A_7C15 &* UInt64(attempt &+ 1)))
    return sampler.next()
  }

  /// Preference inside the fallback set: landing on the committed face first, then a
  /// readable tumble, then coming to rest flat.
  static func score(
    _ outcome: DieRollOutcome, committedFace: ProbabilityDieFace, gate: DiePresentationGate
  ) -> Double {
    var score = outcome.face == committedFace ? 1_000.0 : 0.0
    score += Double(min(outcome.bounces, 6)) * 20.0
    score += outcome.faceUpAlignment * 40.0
    let centre = (gate.settleWindow.lowerBound + gate.settleWindow.upperBound) / 2
    score -= abs(outcome.settledTime - centre) * 25.0
    score -= outcome.lateralDrift * 100.0
    score -= max(0, outcome.apex - gate.maximumApex) * 200.0
    return score
  }
}
