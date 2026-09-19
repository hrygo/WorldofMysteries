import CryptoKit
import Foundation

// MARK: - Deterministic sampler

/// SplitMix64. Every stochastic decision inside a throw is drawn from here, so a roll is
/// reproducible from its seed alone; no system RNG participates anywhere in this file.
nonisolated struct DieSampler: Sendable {
  private var state: UInt64

  init(seed: UInt64) { state = seed }

  mutating func next() -> UInt64 {
    state &+= 0x9E37_79B9_7F4A_7C15
    var z = state
    z = (z ^ (z >> 30)) &* 0xBF58_476D_1CE4_E5B9
    z = (z ^ (z >> 27)) &* 0x94D0_49BB_1331_11EB
    return z ^ (z >> 31)
  }

  mutating func unit() -> Double { Double(next() >> 11) * (1.0 / 9_007_199_254_740_992.0) }

  mutating func range(_ lower: Double, _ upper: Double) -> Double {
    lower + (upper - lower) * unit()
  }
}

// MARK: - Local algebra

nonisolated func dieCross(_ a: SIMD3<Double>, _ b: SIMD3<Double>) -> SIMD3<Double> {
  SIMD3(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x)
}

nonisolated func dieDot(_ a: SIMD3<Double>, _ b: SIMD3<Double>) -> Double {
  a.x * b.x + a.y * b.y + a.z * b.z
}

nonisolated func dieLength(_ v: SIMD3<Double>) -> Double {
  (v.x * v.x + v.y * v.y + v.z * v.z).squareRoot()
}

/// Minimal quaternion algebra kept local, so the solver does not depend on the availability
/// of the generic `simd` overloads for `SIMD3<Double>`.
nonisolated struct DieQuaternion: Sendable, Equatable {
  var x: Double
  var y: Double
  var z: Double
  var w: Double

  static let identity = DieQuaternion(x: 0, y: 0, z: 0, w: 1)

  static func * (lhs: DieQuaternion, rhs: DieQuaternion) -> DieQuaternion {
    DieQuaternion(
      x: lhs.w * rhs.x + lhs.x * rhs.w + lhs.y * rhs.z - lhs.z * rhs.y,
      y: lhs.w * rhs.y - lhs.x * rhs.z + lhs.y * rhs.w + lhs.z * rhs.x,
      z: lhs.w * rhs.z + lhs.x * rhs.y - lhs.y * rhs.x + lhs.z * rhs.w,
      w: lhs.w * rhs.w - lhs.x * rhs.x - lhs.y * rhs.y - lhs.z * rhs.z)
  }

  static func + (lhs: DieQuaternion, rhs: DieQuaternion) -> DieQuaternion {
    DieQuaternion(x: lhs.x + rhs.x, y: lhs.y + rhs.y, z: lhs.z + rhs.z, w: lhs.w + rhs.w)
  }

  static func * (lhs: DieQuaternion, scale: Double) -> DieQuaternion {
    DieQuaternion(x: lhs.x * scale, y: lhs.y * scale, z: lhs.z * scale, w: lhs.w * scale)
  }

  func normalized() -> DieQuaternion {
    let norm = (x * x + y * y + z * z + w * w).squareRoot()
    guard norm > 1e-12 else { return .identity }
    return DieQuaternion(x: x / norm, y: y / norm, z: z / norm, w: w / norm)
  }

  var vector: SIMD4<Double> { SIMD4(x, y, z, w) }

  func rotate(_ v: SIMD3<Double>) -> SIMD3<Double> {
    let axis = SIMD3(x, y, z)
    let t = 2.0 * dieCross(axis, v)
    return v + w * t + dieCross(axis, t)
  }

  static func fromAxisAngle(_ axis: SIMD3<Double>, angle: Double) -> DieQuaternion {
    let magnitude = dieLength(axis)
    guard magnitude > 1e-12 else { return .identity }
    let unitAxis = axis / magnitude
    let half = angle * 0.5
    let s = sin(half)
    return DieQuaternion(x: unitAxis.x * s, y: unitAxis.y * s, z: unitAxis.z * s, w: cos(half))
  }

  /// Shoemake's uniform random rotation, so a throw does not favour any starting pose.
  static func random(_ sampler: inout DieSampler) -> DieQuaternion {
    let u1 = sampler.unit()
    let u2 = sampler.unit()
    let u3 = sampler.unit()
    let a = (1 - u1).squareRoot()
    let b = u1.squareRoot()
    return DieQuaternion(
      x: a * sin(2 * .pi * u2), y: a * cos(2 * .pi * u2), z: b * sin(2 * .pi * u3),
      w: b * cos(2 * .pi * u3)
    ).normalized()
  }

  /// Shortest-arc spherical interpolation.
  static func interpolate(_ from: DieQuaternion, _ to: DieQuaternion, _ t: Double) -> DieQuaternion {
    var target = to
    var cosine = from.x * to.x + from.y * to.y + from.z * to.z + from.w * to.w
    if cosine < 0 {
      target = DieQuaternion(x: -to.x, y: -to.y, z: -to.z, w: -to.w)
      cosine = -cosine
    }
    if cosine > 0.9995 { return (from + (target + (from * -1.0)) * t).normalized() }
    let theta = acos(min(max(cosine, -1), 1))
    let sinTheta = sin(theta)
    let a = sin((1 - t) * theta) / sinTheta
    let b = sin(t * theta) / sinTheta
    return DieQuaternion(
      x: from.x * a + target.x * b, y: from.y * a + target.y * b, z: from.z * a + target.z * b,
      w: from.w * a + target.w * b
    ).normalized()
  }
}

// MARK: - Physical description

/// Real-world scale (a 16 mm die) so gravity, bounce cadence and impact rates stay in SI
/// units instead of being tuned animation curves.
nonisolated public struct DieBodyDefinition: Sendable, Equatable {
  public var side: Double
  public var cornerRadius: Double
  public var mass: Double

  public init(side: Double = 0.016, cornerRadius: Double = 0.0012, mass: Double = 0.0045) {
    self.side = side
    self.cornerRadius = cornerRadius
    self.mass = mass
  }

  public static let standard = DieBodyDefinition()

  /// Half extent of the inner box; the rounded corners are modelled as spheres of
  /// `cornerRadius` sitting on each of its eight vertices.
  var halfExtent: Double { side * 0.5 - cornerRadius }

  /// Solid cube inertia tensor (isotropic): I = m·s²/6.
  var inertia: Double { mass * side * side / 6 }

  var cornerOffsets: [SIMD3<Double>] {
    let h = halfExtent
    var offsets: [SIMD3<Double>] = []
    offsets.reserveCapacity(8)
    for sx in [-1.0, 1.0] {
      for sy in [-1.0, 1.0] {
        for sz in [-1.0, 1.0] {
          offsets.append(SIMD3(sx * h, sy * h, sz * h))
        }
      }
    }
    return offsets
  }
}

/// The throw field: a bounded, wet-stone tray exactly like the engraved circle the artwork
/// shows, plus the contact and damping coefficients of the solver.
nonisolated public struct DieThrowField: Sendable, Equatable {
  public var gravity: Double = 9.81
  public var trayRadius: Double = 0.15
  public var restitution: Double = 0.44
  public var restitutionThreshold: Double = 0.16
  public var friction: Double = 0.40
  /// Damping while the die touches the stone. A real 16 mm die loses spin to rolling and to
  /// inelastic impacts over roughly a second; damping it in a quarter of that reads as a
  /// flick rather than a throw, which is what the first tuning pass did.
  public var contactAngularDamping: Double = 2.2
  public var contactLinearDamping: Double = 1.1
  public var airAngularDamping: Double = 0.04
  public var airLinearDamping: Double = 0.08
  /// Contacts are allowed to stay slightly penetrated. Without this slack the position
  /// projector lifts the die every step and gravity drops it back, which the solver reports
  /// as permanent residual velocity instead of rest.
  public var contactSlop: Double = 5e-5
  public var timeStep: Double = 1.0 / 1000.0
  public var solverIterations: Int = 12
  public var maximumDuration: Double = 6.0
  /// Bake rate of the presented trajectory: one sample every N solver steps.
  public var sampleStride: Int = 4
  /// Length of the final blend that settles the die flat onto the face it landed on.
  public var settleSnapDuration: Double = 0.10
  /// Per-sample motion below both thresholds counts as "the die has stopped". Loose enough to
  /// sit above solver jitter, tight enough that the remaining turn is imperceptible.
  public var restTurnThreshold: Double = 0.006
  public var restTravelThreshold: Double = 6e-5

  public init() {}

  public static let standard = DieThrowField()
}

/// The player's input, reduced to what the physics can use: a lateral direction and how hard
/// the die was flicked. Neither changes the committed face; both change the throw.
nonisolated public struct DieThrowInput: Sendable, Equatable {
  public var direction: SIMD2<Double>
  public var impulse: Double

  public init(direction: SIMD2<Double> = SIMD2(0.6, -0.4), impulse: Double = 0.0) {
    self.direction = direction
    self.impulse = min(max(impulse, 0), 1)
  }

  public static let neutral = DieThrowInput()
}

// MARK: - Baked result

nonisolated public struct DiePoseSample: Sendable, Equatable {
  public var time: Double
  public var position: SIMD3<Double>
  /// Quaternion in (x, y, z, w) order.
  public var orientation: SIMD4<Double>
  /// Normal approach speed of the hardest contact in this sample window, in m/s. Zero while
  /// airborne. Kept as the hook for impact audio and haptics.
  public var impactSpeed: Double
}

nonisolated public struct DieRollOutcome: Sendable {
  public var face: ProbabilityDieFace
  public var seed: UInt64
  public var settledTime: Double
  public var bounces: Int
  /// Alignment of the landing face with world up, measured before the settle blend. This is
  /// the physical quality metric: 1.0 means the die came to rest perfectly flat.
  public var faceUpAlignment: Double
  public var lateralDrift: Double
  public var apex: Double
  public var trajectoryDigest: String
  public var samples: [DiePoseSample]

  public var finalPose: DiePoseSample? { samples.last }
}

// MARK: - Solver

nonisolated struct DieContact {
  var point: SIMD3<Double>
  var normal: SIMD3<Double>
  var penetration: Double
}

nonisolated struct DieFaceNormal: Sendable {
  var face: ProbabilityDieFace
  var normal: SIMD3<Double>
}

/// Deterministic 6-DOF rigid-body solver for a rounded cube on a bounded tray.
///
/// Same seed and same input always produce byte-identical samples, which is what lets the
/// presentation layer search for a physically honest throw instead of faking one.
nonisolated public struct DieRigidBodySolver: Sendable {
  public var body: DieBodyDefinition
  public var field: DieThrowField

  public init(body: DieBodyDefinition = .standard, field: DieThrowField = .standard) {
    self.body = body
    self.field = field
  }

  public func simulate(seed: UInt64, throwInput: DieThrowInput = .neutral) -> DieRollOutcome? {
    var sampler = DieSampler(seed: seed)
    let corners = body.cornerOffsets
    let inertia = body.inertia
    let stepDuration = field.timeStep

    var orientation = DieQuaternion.random(&sampler)
    // Release envelope of an actual throw rather than a drop: a die has to fall far enough and
    // spin fast enough to tumble. The first tuning pass released it 5-12 cm with 15-40 rad/s,
    // which turned less than one revolution in total and read as a flick.
    let dropHeight = 0.09 + sampler.range(0, 0.12)
    var position = SIMD3<Double>(0, dropHeight, 0)

    let speedScale = 0.7 + 0.6 * throwInput.impulse
    let lateralSpeed = (0.20 + sampler.range(0, 0.30)) * speedScale
    var velocity = SIMD3<Double>(
      throwInput.direction.x * lateralSpeed, sampler.range(0, 0.25),
      throwInput.direction.y * lateralSpeed)

    let spinAxis = SIMD3<Double>(sampler.range(-1, 1), sampler.range(-1, 1), sampler.range(-1, 1))
    var spin = spinAxis * ((25.0 + sampler.range(0, 35.0)) / max(1e-9, dieLength(spinAxis)))

    var contacts: [DieContact] = []
    contacts.reserveCapacity(16)
    var samples: [DiePoseSample] = []
    samples.reserveCapacity(Int(field.maximumDuration / stepDuration) / field.sampleStride + 8)

    let maxRadius = field.trayRadius - body.cornerRadius
    var apex = dropHeight
    var bounces = 0
    var restingSteps = 0
    var wasAirborne = true
    var step = 0
    var stepImpact = 0.0
    let maximumSteps = Int(field.maximumDuration / stepDuration)

    while step < maximumSteps {
      step += 1
      velocity += SIMD3(0, -field.gravity, 0) * stepDuration

      var hadContact = false
      stepImpact = 0
      for _ in 0..<field.solverIterations {
        gatherContacts(
          position: position, orientation: orientation, corners: corners, contacts: &contacts)
        guard !contacts.isEmpty else { break }
        hadContact = true
        if stepImpact == 0 {
          stepImpact = contacts.reduce(0) { partial, contact in
            let arm = contact.point - position
            let approach = dieDot(velocity + dieCross(spin, arm), contact.normal)
            return approach < 0 ? max(partial, -approach) : partial
          }
        }
        for contact in contacts {
          applyImpulse(
            position: &position, velocity: &velocity, spin: &spin, contact: contact,
            inertia: inertia)
        }
      }

      if hadContact {
        velocity *= 1 - field.contactLinearDamping * stepDuration
        spin *= 1 - field.contactAngularDamping * stepDuration
      } else {
        velocity *= 1 - field.airLinearDamping * stepDuration
        spin *= 1 - field.airAngularDamping * stepDuration
      }

      position += velocity * stepDuration
      let spinRate = DieQuaternion(x: spin.x, y: spin.y, z: spin.z, w: 0) * orientation
      orientation = (orientation + spinRate * (0.5 * stepDuration)).normalized()

      // One positional projection pass keeps the die out of the floor and the tray wall
      // without feeding energy back into the velocity solver.
      var lowestCorner = Double.greatestFiniteMagnitude
      var furthestCorner = 0.0
      for corner in corners {
        let world = position + orientation.rotate(corner)
        lowestCorner = min(lowestCorner, world.y)
        furthestCorner = max(furthestCorner, (world.x * world.x + world.z * world.z).squareRoot())
      }
      let restingHeight = body.cornerRadius - field.contactSlop
      if lowestCorner < restingHeight { position.y += restingHeight - lowestCorner }
      if furthestCorner > maxRadius {
        let shrink = maxRadius / furthestCorner
        position.x *= shrink
        position.z *= shrink
      }
      apex = max(apex, position.y)

      // Grounded is evaluated from the current pose only; a latched flag would hide every
      // rebound after the first landing.
      let grounded = lowestCorner <= restingHeight + 2e-4
      if grounded && wasAirborne { bounces += 1 }
      wasAirborne = !grounded

      if step % field.sampleStride == 0 {
        samples.append(
          DiePoseSample(
            time: Double(step) * stepDuration, position: position,
            orientation: orientation.vector, impactSpeed: stepImpact))
      }

      if grounded && dieLength(velocity) < 0.02 && dieLength(spin) < 0.5 {
        restingSteps += 1
        if restingSteps > 60 {
          velocity = .zero
          spin = .zero
        }
        if restingSteps > 160 {
          return finish(
            orientation: orientation, position: position, seed: seed,
            settledTime: Double(step) * stepDuration, apex: apex - dropHeight, bounces: bounces,
            samples: samples)
        }
      } else {
        restingSteps = 0
      }
    }
    return nil
  }

  // MARK: Contacts

  private func gatherContacts(
    position: SIMD3<Double>, orientation: DieQuaternion, corners: [SIMD3<Double>],
    contacts: inout [DieContact]
  ) {
    contacts.removeAll(keepingCapacity: true)
    let wallLimit = field.trayRadius - body.cornerRadius
    for corner in corners {
      let world = position + orientation.rotate(corner)
      let floorPenetration = body.cornerRadius - world.y
      if floorPenetration > 0 {
        contacts.append(
          DieContact(point: world, normal: SIMD3(0, 1, 0), penetration: floorPenetration))
      }
      let radial = SIMD3<Double>(world.x, 0, world.z)
      let distance = dieLength(radial)
      if distance > wallLimit, distance > 1e-9 {
        contacts.append(
          DieContact(
            point: world, normal: -(radial / distance), penetration: distance - wallLimit))
      }
    }
  }

  private func applyImpulse(
    position: inout SIMD3<Double>, velocity: inout SIMD3<Double>, spin: inout SIMD3<Double>,
    contact: DieContact, inertia: Double
  ) {
    let arm = contact.point - position
    let normal = contact.normal
    let normalSpeed = dieDot(velocity + dieCross(spin, arm), normal)
    if normalSpeed > 0 { return }

    let normalArm = dieCross(arm, normal)
    let effectiveMass = 1.0 / body.mass + dieDot(normalArm, normalArm) / inertia
    let bounce =
      (-normalSpeed > field.restitutionThreshold) ? field.restitution : 0.0
    let normalImpulse = max(0.0, -(1 + bounce) * normalSpeed / effectiveMass)
    velocity += normal * (normalImpulse / body.mass)
    spin += dieCross(arm, normal) * (normalImpulse / inertia)

    let relative = velocity + dieCross(spin, arm)
    let tangential = relative - normal * dieDot(relative, normal)
    let tangentialSpeed = dieLength(tangential)
    guard tangentialSpeed > 1e-7 else { return }
    let tangent = tangential / -tangentialSpeed
    let tangentArm = dieCross(arm, tangent)
    let effectiveMassTangent = 1.0 / body.mass + dieDot(tangentArm, tangentArm) / inertia
    let limit = field.friction * normalImpulse
    let tangentialImpulse = min(
      limit, max(-limit, -dieDot(relative, tangent) / effectiveMassTangent))
    velocity += tangent * (tangentialImpulse / body.mass)
    spin += dieCross(arm, tangent) * (tangentialImpulse / inertia)
  }

  // MARK: Settling

  /// Resolves the landing face, snaps the final pose flat, and digests the trajectory.
  ///
  /// The snap only removes residual solver jitter (a degree or two); it never changes which
  /// face the die actually landed on, which is why the raw alignment is reported separately.
  private func finish(
    orientation: DieQuaternion, position: SIMD3<Double>, seed: UInt64,
    settledTime: Double, apex: Double, bounces: Int, samples: [DiePoseSample]
  ) -> DieRollOutcome {
    let up = SIMD3<Double>(0, 1, 0)
    var landedFace = ProbabilityDieFace.one
    var landedNormal = SIMD3<Double>(0, 1, 0)
    var alignment = -2.0
    for candidate in DieRigidBodySolver.faceNormals {
      let world = orientation.rotate(candidate.normal)
      if world.y > alignment {
        alignment = world.y
        landedFace = candidate.face
        landedNormal = world
      }
    }
    let correction = DieQuaternion.fromAxisAngle(
      dieCross(landedNormal, up), angle: acos(min(max(dieDot(landedNormal, up), -1), 1)))
    let settledOrientation = (correction * orientation).normalized()

    // The solver integrates until its rest detector releases, which appends a tail where the
    // die is already motionless. Presenting that tail freezes the die for up to a second
    // before the reveal, so the trajectory is trimmed back to the moment it stops.
    let endIndex = DieRigidBodySolver.motionEndIndex(of: samples, field: field)
    let presentedTime = samples[endIndex].time
    let presentedPosition = samples[endIndex].position

    let blendStart = max(0, presentedTime - field.settleSnapDuration)
    var baked = Array(samples[0...endIndex])
    for index in baked.indices where baked[index].time > blendStart {
      let progress = min(max((baked[index].time - blendStart) / field.settleSnapDuration, 0), 1)
      let eased = progress * progress * (3 - 2 * progress)
      let raw = DieQuaternion(
        x: baked[index].orientation.x, y: baked[index].orientation.y,
        z: baked[index].orientation.z, w: baked[index].orientation.w)
      baked[index].orientation = DieQuaternion.interpolate(raw, settledOrientation, eased).vector
    }
    baked.append(
      DiePoseSample(
        time: presentedTime, position: presentedPosition, orientation: settledOrientation.vector,
        impactSpeed: baked.last?.impactSpeed ?? 0))

    return DieRollOutcome(
      face: landedFace, seed: seed, settledTime: presentedTime, bounces: bounces,
      faceUpAlignment: alignment,
      lateralDrift: (position.x * position.x + position.z * position.z).squareRoot(), apex: apex,
      trajectoryDigest: DieRigidBodySolver.digest(of: baked), samples: baked)
  }

  /// Index of the first baked sample after the last visibly moving interval.
  ///
  /// Scanning from the tail removes the solver's motionless rest-detector tail. A late jitter
  /// spike remains visible by design: it is still a physical sample, and hiding it would make
  /// the presented trajectory diverge from the solved one.
  static func motionEndIndex(of samples: [DiePoseSample], field: DieThrowField) -> Int {
    guard samples.count > 1 else { return 0 }
    var index = samples.count - 1
    while index > 0 {
      let previous = samples[index - 1]
      let current = samples[index]
      let from = DieQuaternion(
        x: previous.orientation.x, y: previous.orientation.y, z: previous.orientation.z,
        w: previous.orientation.w)
      let to = DieQuaternion(
        x: current.orientation.x, y: current.orientation.y, z: current.orientation.z,
        w: current.orientation.w)
      let dot = min(1.0, abs(from.x * to.x + from.y * to.y + from.z * to.z + from.w * to.w))
      let turn = 2 * acos(dot)
      let travel = dieLength(current.position - previous.position)
      if turn > field.restTurnThreshold || travel > field.restTravelThreshold { return index }
      index -= 1
    }
    return 0
  }

  static func digest(of samples: [DiePoseSample]) -> String {
    var hasher = SHA256()
    var buffer = [UInt8]()
    buffer.reserveCapacity(samples.count * 40)
    func append(_ value: Double) {
      let quantised = Int64((value * 1_000_000).rounded())
      withUnsafeBytes(of: quantised.littleEndian) { buffer.append(contentsOf: $0) }
    }
    for sample in samples {
      append(sample.time)
      append(sample.position.x)
      append(sample.position.y)
      append(sample.position.z)
      append(sample.orientation.x)
      append(sample.orientation.y)
      append(sample.orientation.z)
      append(sample.orientation.w)
    }
    hasher.update(data: Data(buffer))
    return hasher.finalize().map { String(format: "%02x", $0) }.joined()
  }

  /// Body-space face normals. Opposite faces sum to seven, matching the layout the app ships.
  static let faceNormals: [DieFaceNormal] = [
    DieFaceNormal(face: .one, normal: SIMD3(0, 1, 0)),
    DieFaceNormal(face: .six, normal: SIMD3(0, -1, 0)),
    DieFaceNormal(face: .two, normal: SIMD3(0, 0, 1)),
    DieFaceNormal(face: .five, normal: SIMD3(0, 0, -1)),
    DieFaceNormal(face: .three, normal: SIMD3(1, 0, 0)),
    DieFaceNormal(face: .four, normal: SIMD3(-1, 0, 0)),
  ]
}
