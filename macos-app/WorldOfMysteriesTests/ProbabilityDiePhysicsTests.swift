import Foundation
import Testing

@testable import WorldOfMysteriesCore

@Suite("Probability Die Deterministic Physics", .serialized)
struct ProbabilityDiePhysicsTests {
  @Test("The same seed and throw produce an identical trajectory")
  func trajectoryIsReproducible() throws {
    let solver = DieRigidBodySolver()
    let first = try #require(solver.simulate(seed: 0x5EED_1234))
    let second = try #require(solver.simulate(seed: 0x5EED_1234))

    #expect(first.trajectoryDigest == second.trajectoryDigest)
    #expect(first.face == second.face)
    #expect(first.samples.count == second.samples.count)
    #expect(abs(first.settledTime - second.settledTime) < 1e-12)
  }

  @Test("Different seeds produce different throws")
  func seedsProduceDistinctThrows() throws {
    let solver = DieRigidBodySolver()
    var digests: Set<String> = []
    for seed in 0..<24 {
      digests.insert(try #require(solver.simulate(seed: UInt64(seed) &* 7919)).trajectoryDigest)
    }
    #expect(digests.count == 24)
  }

  @Test("Throws converge and come to rest flat on a real face")
  func throwsSettleFlat() {
    let solver = DieRigidBodySolver()
    var settled = 0
    for seed in 0..<300 {
      guard let outcome = solver.simulate(seed: UInt64(seed) &* 2_654_435_761) else { continue }
      settled += 1
      #expect(outcome.faceUpAlignment >= 0.99)
      #expect(outcome.bounces >= 1)
      #expect(outcome.settledTime > 0.05)
    }
    // The solver must not silently give up on a meaningful share of throws: a missing
    // outcome would mean "no physics available", which the presentation has to know about.
    #expect(settled >= 285)
  }

  @Test("Presented throws do not carry a motionless tail")
  func presentedThrowsTrackVisibleMotion() {
    let solver = DieRigidBodySolver()
    var settled = 0
    for seed in 0..<120 {
      guard let outcome = solver.simulate(seed: UInt64(seed) &* 2_654_435_761) else { continue }
      settled += 1
      #expect(outcome.settledTime <= 0.62)
      #expect(outcome.samples.last?.time == outcome.settledTime)
    }
    #expect(settled >= 114)
  }

  @Test("Unweighted throws show no systematic bias across the six faces")
  func landingDistributionIsUnbiased() {
    let solver = DieRigidBodySolver()
    var counts: [ProbabilityDieFace: Int] = [:]
    for seed in 0..<600 {
      guard let outcome = solver.simulate(seed: UInt64(seed) &* 7919 &+ 13) else { continue }
      counts[outcome.face, default: 0] += 1
    }
    for face in ProbabilityDieFace.allCases {
      let count = counts[face] ?? 0
      #expect(count >= 50 && count <= 150, "face \(face.rawValue) landed \(count) times")
    }
  }

  @Test("Every committed face is presentable by a real throw")
  func plannerLandsOnCommittedFace() throws {
    let planner = DieRollPlanner()
    for face in ProbabilityDieFace.allCases {
      let plan = try #require(
        planner.plan(committedFace: face, seed: 0xFACE_0000 &+ UInt64(face.rawValue)),
        "no plan for face \(face.rawValue)")
      #expect(plan.outcome.face == face)
      #expect(plan.landsOnCommittedFace)
      #expect(!plan.relaxedPresentationGate)
      #expect(planner.gate.accepts(plan.outcome))
    }
  }

  @Test("Planning is reproducible and cheap")
  func planningIsReproducible() throws {
    let planner = DieRollPlanner()
    let clock = ContinuousClock()
    let start = clock.now
    let first = try #require(planner.plan(committedFace: .five, seed: 42))
    let second = try #require(planner.plan(committedFace: .five, seed: 42))
    let elapsed = clock.now - start

    #expect(first.outcome.trajectoryDigest == second.outcome.trajectoryDigest)
    #expect(first.candidatesEvaluated == second.candidatesEvaluated)
    #expect(first.candidatesEvaluated <= 40)
    #expect(elapsed < .milliseconds(500))
  }

  @Test("Planning is usable away from the main actor")
  func planningRunsOffTheMainActor() async throws {
    let planner = DieRollPlanner()
    let plan = await Task.detached { planner.plan(committedFace: .three, seed: 7) }.value
    let resolved = try #require(plan)
    #expect(resolved.outcome.face == .three)
  }

  @Test("An unsatisfiable presentation gate still yields an honest plan")
  func impossibleGateFallsBackHonestly() throws {
    var gate = DiePresentationGate()
    gate.minimumBounces = 99
    let planner = DieRollPlanner(gate: gate, maximumCandidates: 12)
    let plan = try #require(planner.plan(committedFace: .six, seed: 99))

    #expect(plan.relaxedPresentationGate)
    #expect(!gate.accepts(plan.outcome))
    // The fallback still prefers the committed face; if it ever could not, the caller must
    // not imply the animation decided the outcome, which is what this flag is for.
    #expect(plan.outcome.face == .six)
    #expect(plan.landsOnCommittedFace)
  }

  @Test("The die never leaves the engraving it is thrown onto")
  func dieStaysInsideTheTray() throws {
    let solver = DieRigidBodySolver()
    let outcome = try #require(solver.simulate(seed: 4321))
    let limit = solver.field.trayRadius + 1e-6
    for sample in outcome.samples {
      let radial = (sample.position.x * sample.position.x + sample.position.z * sample.position.z)
        .squareRoot()
      #expect(radial <= limit)
    }
  }

  @Test("The presented die ends flat on the face it reports")
  func presentedPoseIsFlat() throws {
    let solver = DieRigidBodySolver()
    let outcome = try #require(solver.simulate(seed: 77))
    let final = try #require(outcome.finalPose)
    let faceNormal = try #require(
      DieRigidBodySolver.faceNormals.first { $0.face == outcome.face })
    let orientation = DieQuaternion(
      x: final.orientation.x, y: final.orientation.y, z: final.orientation.z,
      w: final.orientation.w)

    #expect(abs(orientation.rotate(faceNormal.normal).y - 1) < 1e-6)
  }

  @Test("Resting poses map to one stable height on screen")
  func presentationRestHeightIsStable() {
    let placement = DiePresentationTransform()
    let resting = DiePoseSample(
      time: 0, position: SIMD3(0, DieBodyDefinition.standard.side / 2, 0),
      orientation: SIMD4(0, 0, 0, 1), impactSpeed: 0)
    #expect(abs(placement.transform(for: resting).translation.y - Float(placement.restY)) < 1e-5)
  }

  @Test("A settled presentation reveals the roll exactly once")
  @MainActor
  func settledPresentationRevealsOnce() async throws {
    let context = ArtifactContext(worldID: "world", worldlineID: "main", storyRevision: 4)
    let model = ProbabilityDieModel(resolver: PreviewProbabilityDieResolver())

    // Settling before a roll is in flight must not fabricate history.
    model.presentationDidSettle()
    #expect(model.history.isEmpty)

    let roll = Task { await model.roll(context: context, stakes: .guarded) }
    var waited = 0
    while waited < 40 {
      if case .rolling = model.phase { break }
      try await Task.sleep(for: .milliseconds(25))
      waited += 1
    }
    guard case .rolling = model.phase else {
      Issue.record("the model never reached the rolling phase")
      await roll.value
      return
    }

    model.presentationDidSettle()
    #expect(model.history.count == 1)
    if case .revealed = model.phase {} else {
      Issue.record("the physics-driven settle did not reveal the roll")
    }

    // The fallback timer must be a no-op once the physics already reported the landing.
    await roll.value
    #expect(model.history.count == 1)
  }
}
