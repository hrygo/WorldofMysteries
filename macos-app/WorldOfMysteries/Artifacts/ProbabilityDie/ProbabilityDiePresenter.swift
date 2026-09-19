import AppKit
import RealityKit
import SwiftUI
import simd

/// Maps a solved trajectory in real-world metres onto the scene units the card renders in.
///
/// The scale is presentation only: it never changes the sample order, the timing, or which
/// face comes to rest upward. The die is presented 0.82 scene units across, so the tray the
/// physics uses corresponds to the circle the artwork engraves on the stone.
struct DiePresentationTransform: Sendable {
  var scale: Double = 5.0
  var restY: Double = 0.08
  var visualSize: Double = 0.82
  var body: DieBodyDefinition = .standard

  func transform(for pose: DiePoseSample) -> Transform {
    let restingHeight = body.side * 0.5
    var transform = Transform()
    transform.scale = .one
    transform.translation = SIMD3<Float>(
      Float(pose.position.x * scale),
      Float(restY + (pose.position.y - restingHeight) * scale),
      Float(pose.position.z * scale))
    transform.rotation = simd_quatf(
      ix: Float(pose.orientation.x), iy: Float(pose.orientation.y),
      iz: Float(pose.orientation.z), r: Float(pose.orientation.w))
    return transform
  }
}

/// Which world axis a face points along in body space.
enum DieFaceAxis: Sendable {
  case xPositive, xNegative, yPositive, yNegative, zPositive, zNegative
}

struct DieFacePlacement: Sendable {
  var face: ProbabilityDieFace
  var axis: DieFaceAxis
}

/// Plays a planned roll on a procedurally built die.
///
/// The die is generated from geometry rather than scanned from artwork on purpose: pips have
/// to sit at exact positions with opposite faces summing to seven, which is the one thing a
/// generated image cannot be trusted with.
@MainActor
public final class ProbabilityDiePresenter {
  public let root = Entity()

  private let die = ModelEntity()
  private let placement = DiePresentationTransform()
  private var isPrepared = false
  private var playback: Task<Void, Never>?

  public init() {}

  public func prepare() {
    guard !isPrepared else { return }
    isPrepared = true
    buildDie()
    buildLighting()
  }

  /// Starts the planned throw. `onSettle` fires exactly once, when the die has come to rest,
  /// which is what lets the reveal be driven by the physics instead of a fixed timer.
  public func present(_ plan: DieRollPlan, onSettle: @escaping @MainActor () -> Void) {
    prepare()
    stopPlayback()

    let samples = plan.outcome.samples
    let settledTime = plan.outcome.settledTime
    guard let first = samples.first else {
      onSettle()
      return
    }
    die.transform = placement.transform(for: first)

    let clock = ContinuousClock()
    playback = Task { @MainActor [weak self] in
      guard let self else { return }
      let start = clock.now
      while !Task.isCancelled {
        let elapsed = start.duration(to: clock.now)
        let seconds =
          Double(elapsed.components.seconds) + Double(elapsed.components.attoseconds) * 1e-18
        if seconds >= settledTime {
          self.die.transform = self.placement.transform(
            for: ProbabilityDiePresenter.pose(in: samples, at: settledTime))
          onSettle()
          return
        }
        self.die.transform = self.placement.transform(
          for: ProbabilityDiePresenter.pose(in: samples, at: seconds))
        try? await Task.sleep(for: .milliseconds(8))
      }
    }
  }

  public func stopPlayback() {
    playback?.cancel()
    playback = nil
  }

  /// Linear position and shortest-arc rotation interpolation between baked samples.
  static func pose(in samples: [DiePoseSample], at time: Double) -> DiePoseSample {
    guard let first = samples.first, let last = samples.last else {
      return DiePoseSample(
        time: time, position: .zero, orientation: SIMD4(0, 0, 0, 1), impactSpeed: 0)
    }
    if time <= first.time { return first }
    if time >= last.time { return last }

    var low = 0
    var high = samples.count - 1
    while high - low > 1 {
      let mid = (low + high) / 2
      if samples[mid].time <= time { low = mid } else { high = mid }
    }
    let a = samples[low]
    let b = samples[high]
    let span = b.time - a.time
    let t = span > 1e-9 ? (time - a.time) / span : 0
    let from = DieQuaternion(
      x: a.orientation.x, y: a.orientation.y, z: a.orientation.z, w: a.orientation.w)
    let to = DieQuaternion(
      x: b.orientation.x, y: b.orientation.y, z: b.orientation.z, w: b.orientation.w)

    return DiePoseSample(
      time: time,
      position: a.position + (b.position - a.position) * t,
      orientation: DieQuaternion.interpolate(from, to, t).vector,
      impactSpeed: max(a.impactSpeed, b.impactSpeed))
  }

  // MARK: Geometry

  private func buildDie() {
    let size = Float(placement.visualSize)
    let chamfer = Float(placement.visualSize * placement.body.cornerRadius / placement.body.side)
    die.model = ModelComponent(
      mesh: .generateBox(size: size, cornerRadius: chamfer),
      materials: [ProbabilityDiePresenter.bodyMaterial()])
    die.transform = placement.transform(
      for: DiePoseSample(
        time: 0, position: SIMD3(0, placement.body.side / 2, 0),
        orientation: SIMD4(0, 0, 0, 1), impactSpeed: 0))
    addPips(size: size)
    root.addChild(die)
  }

  private func addPips(size: Float) {
    let half = Double(size) * 0.5
    let radius = Float(Double(size) * 0.044)
    // Cabochons sit slightly below the surface so the die reads as a cast object with inset
    // garnets rather than a cube with balls glued onto it.
    let offset = Float(half - Double(radius) * 0.75)
    let span = Float(Double(size) * 0.232)
    let materials = [ProbabilityDiePresenter.pipMaterial()]

    for placement in ProbabilityDiePresenter.pipPlacements {
      for position in ProbabilityDiePresenter.pipPattern(for: placement.face) {
        let pip = ModelEntity(mesh: .generateSphere(radius: radius), materials: materials)
        let u = position.x * span
        let v = position.y * span
        switch placement.axis {
        case .xPositive: pip.position = [offset, v, -u]
        case .xNegative: pip.position = [-offset, v, u]
        case .yPositive: pip.position = [u, offset, v]
        case .yNegative: pip.position = [u, -offset, -v]
        case .zPositive: pip.position = [u, v, offset]
        case .zNegative: pip.position = [-u, v, -offset]
        }
        die.addChild(pip)
      }
    }
  }

  private func buildLighting() {
    let key = Entity()
    key.components.set(
      DirectionalLightComponent(color: NSColor(Color.Mystic.spiritualBlue), intensity: 1400))
    key.look(at: .zero, from: [0.6, 1.4, 0.9], relativeTo: nil)
    root.addChild(key)

    let fill = Entity()
    fill.components.set(
      DirectionalLightComponent(color: NSColor(Color.Mystic.brassGoldPrimary), intensity: 600))
    fill.look(at: .zero, from: [-0.9, 0.5, -0.7], relativeTo: nil)
    root.addChild(fill)
  }

  private static func bodyMaterial() -> PhysicallyBasedMaterial {
    var material = PhysicallyBasedMaterial()
    material.baseColor = .init(tint: NSColor(Color.Mystic.parchmentCard))
    material.roughness = .init(floatLiteral: 0.34)
    material.metallic = .init(floatLiteral: 0.02)
    return material
  }

  private static func pipMaterial() -> PhysicallyBasedMaterial {
    var material = PhysicallyBasedMaterial()
    material.baseColor = .init(tint: NSColor(Color.Mystic.crimsonStar))
    material.roughness = .init(floatLiteral: 0.18)
    material.metallic = .init(floatLiteral: 0.0)
    material.emissiveColor = .init(color: NSColor(Color.Mystic.crimsonStar))
    material.emissiveIntensity = 0.12
    return material
  }

  /// Body-space face axes, unchanged from the layout the card already shipped.
  static let pipPlacements: [DieFacePlacement] = [
    DieFacePlacement(face: .one, axis: .yPositive),
    DieFacePlacement(face: .six, axis: .yNegative),
    DieFacePlacement(face: .two, axis: .zPositive),
    DieFacePlacement(face: .five, axis: .zNegative),
    DieFacePlacement(face: .three, axis: .xPositive),
    DieFacePlacement(face: .four, axis: .xNegative),
  ]

  /// Pip positions per face on a -1...1 square, centred.
  static func pipPattern(for face: ProbabilityDieFace) -> [SIMD2<Float>] {
    let topLeft = SIMD2<Float>(-1, 1)
    let topRight = SIMD2<Float>(1, 1)
    let bottomLeft = SIMD2<Float>(-1, -1)
    let bottomRight = SIMD2<Float>(1, -1)
    let middleLeft = SIMD2<Float>(-1, 0)
    let middleRight = SIMD2<Float>(1, 0)
    let centre = SIMD2<Float>(0, 0)
    switch face {
    case .one: return [centre]
    case .two: return [topLeft, bottomRight]
    case .three: return [topLeft, centre, bottomRight]
    case .four: return [topLeft, topRight, bottomLeft, bottomRight]
    case .five: return [topLeft, topRight, centre, bottomLeft, bottomRight]
    case .six:
      return [topLeft, middleLeft, bottomLeft, topRight, middleRight, bottomRight]
    }
  }
}
