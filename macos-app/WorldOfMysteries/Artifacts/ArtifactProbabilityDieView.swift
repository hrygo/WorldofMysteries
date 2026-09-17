import AppKit
import RealityKit
import SwiftUI
import simd

// MARK: - 概率之骰

@MainActor
private final class ProbabilityDieRealityController {
  let root = Entity()
  private let die = ModelEntity()
  private var isPrepared = false

  func prepare() {
    guard !isPrepared else { return }
    isPrepared = true

    let cubeMesh = MeshResource.generateBox(size: 0.82, cornerRadius: 0.08)
    let ivory = SimpleMaterial(
      color: NSColor(Color.Mystic.parchmentCard),
      roughness: 0.32,
      isMetallic: false
    )
    die.model = ModelComponent(mesh: cubeMesh, materials: [ivory])
    die.position = [0, 0.1, 0]
    addPips()
    root.addChild(die)
  }

  func roll(to face: ProbabilityDieFace, seed: UInt64, visualVector: CGSize) {
    prepare()
    die.stopAllAnimations(recursive: true)

    let dx = Float(max(-1, min(1, visualVector.width / 240)))
    let dz = Float(max(-1, min(1, visualVector.height / 180)))
    let start = Transform(
      scale: .one,
      rotation: randomOrientation(seed: seed),
      translation: [0, 0.18, 0]
    )
    die.transform = start

    let mid = Transform(
      scale: .one,
      rotation: randomOrientation(seed: seed &+ 17),
      translation: [dx * 0.22, 0.62, -dz * 0.18]
    )
    die.move(to: mid, relativeTo: root, duration: 0.46, timingFunction: .easeInOut)

    Task { @MainActor [weak self] in
      try? await Task.sleep(for: .milliseconds(430))
      guard let self else { return }
      let final = Transform(
        scale: .one,
        rotation: self.orientation(forTopFace: face, yaw: Float(seed % 6283) / 1000),
        translation: [0, 0.08, 0]
      )
      self.die.move(to: final, relativeTo: self.root, duration: 0.52, timingFunction: .easeOut)
    }
  }

  private func addPips() {
    let red = UnlitMaterial(color: NSColor(Color.Mystic.crimsonStar))
    let radius: Float = 0.038
    let offset: Float = 0.426
    let span: Float = 0.19

    func pattern(_ face: ProbabilityDieFace) -> [SIMD2<Float>] {
      let c = SIMD2<Float>(0, 0)
      let tl = SIMD2<Float>(-1, 1)
      let tr = SIMD2<Float>(1, 1)
      let bl = SIMD2<Float>(-1, -1)
      let br = SIMD2<Float>(1, -1)
      let ml = SIMD2<Float>(-1, 0)
      let mr = SIMD2<Float>(1, 0)
      switch face {
      case .one: return [c]
      case .two: return [tl, br]
      case .three: return [tl, c, br]
      case .four: return [tl, tr, bl, br]
      case .five: return [tl, tr, c, bl, br]
      case .six: return [tl, tr, ml, mr, bl, br]
      }
    }

    enum Axis { case xp, xn, yp, yn, zp, zn }
    let faces: [(ProbabilityDieFace, Axis)] = [
      (.one, .yp), (.six, .yn), (.two, .zp), (.five, .zn), (.three, .xp), (.four, .xn),
    ]

    for (face, axis) in faces {
      for uv in pattern(face) {
        let pip = ModelEntity(mesh: .generateSphere(radius: radius), materials: [red])
        let u = uv.x * span
        let v = uv.y * span
        switch axis {
        case .xp: pip.position = [offset, v, -u]
        case .xn: pip.position = [-offset, v, u]
        case .yp: pip.position = [u, offset, v]
        case .yn: pip.position = [u, -offset, -v]
        case .zp: pip.position = [u, v, offset]
        case .zn: pip.position = [-u, v, -offset]
        }
        die.addChild(pip)
      }
    }
  }

  private func randomOrientation(seed: UInt64) -> simd_quatf {
    let a = Float(seed % 6283) / 1000
    let b = Float((seed >> 12) % 6283) / 1000
    return simd_quatf(angle: a, axis: [1, 0, 0]) * simd_quatf(angle: b, axis: [0, 1, 0])
  }

  private func orientation(forTopFace face: ProbabilityDieFace, yaw: Float) -> simd_quatf {
    let target: simd_quatf
    switch face {
    case .one: target = simd_quatf(angle: 0, axis: [1, 0, 0])
    case .six: target = simd_quatf(angle: .pi, axis: [1, 0, 0])
    case .two: target = simd_quatf(angle: -.pi / 2, axis: [1, 0, 0])
    case .five: target = simd_quatf(angle: .pi / 2, axis: [1, 0, 0])
    case .three: target = simd_quatf(angle: .pi / 2, axis: [0, 0, 1])
    case .four: target = simd_quatf(angle: -.pi / 2, axis: [0, 0, 1])
    }
    return simd_quatf(angle: yaw, axis: [0, 1, 0]) * target
  }
}

@MainActor
public struct ProbabilityDieArtifactView: View {
  @Bindable private var model: ProbabilityDieModel
  private let context: ArtifactContext
  private let stakes: ArtifactRiskBand

  @State private var scene = ProbabilityDieRealityController()
  @State private var dragVector = CGSize.zero
  @State private var isDragging = false

  public init(
    model: ProbabilityDieModel, context: ArtifactContext, stakes: ArtifactRiskBand = .guarded
  ) {
    self.model = model
    self.context = context
    self.stakes = stakes
  }

  public var body: some View {
    ArtifactComponentShell(artifactID: .probabilityDie) {
      VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
        ViewThatFits(in: .horizontal) {
          HStack(alignment: .top, spacing: DesignTokens.Spacing.md) {
            dieHeaderText
            Spacer(minLength: DesignTokens.Spacing.md)
            riskPill
          }

          VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            dieHeaderText
            riskPill
          }
        }

        ZStack {
          RealityView { content in
            scene.prepare()
            content.add(scene.root)
          }
          .gesture(
            DragGesture(minimumDistance: 5)
              .onChanged { value in
                guard model.canRoll else { return }
                isDragging = true
                dragVector = value.translation
              }
              .onEnded { value in
                defer {
                  isDragging = false
                  dragVector = .zero
                }
                guard model.canRoll else { return }
                Task {
                  await model.roll(
                    context: context, stakes: stakes, throwVector: value.predictedEndTranslation)
                }
              }
          )

          ArtifactAmbientField(tone: .azure, intensity: isDragging ? 1 : 0.45, particleCount: 20)
            .allowsHitTesting(false)

          if isDragging {
            Text("释放投掷 · Δ(\(Int(dragVector.width)), \(Int(dragVector.height)))")
              .font(Font.Mystic.monoBadge)
              .foregroundStyle(Color.Mystic.spiritualBlue)
              .padding(DesignTokens.Spacing.sm)
              .background(Color.Mystic.obsidianGlass)
              .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
          }
        }
        .frame(height: 290)
        .background(Color.Mystic.abyssVoid)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
        .overlay(
          RoundedRectangle(cornerRadius: DesignTokens.Radii.md).stroke(
            Color.Mystic.spiritualBlue.opacity(0.25), lineWidth: DesignTokens.Borders.hairline)
        )
        .onChange(of: model.presentationRevision) { _, _ in
          guard let resolution = model.currentResolution else { return }
          scene.roll(
            to: resolution.face, seed: resolution.deterministicSeed, visualVector: model.throwVector
          )
        }

        LazyVGrid(
          columns: [GridItem(.adaptive(minimum: 180), spacing: DesignTokens.Spacing.md)],
          alignment: .leading,
          spacing: DesignTokens.Spacing.md
        ) {
          ArtifactMeterCard(
            "苏醒", value: model.artifactState.awakening, detail: "高苏醒状态可由 World Pulse 触发自主投掷。",
            systemIcon: "eye", tone: .azure)
          ArtifactMeterCard(
            "怨意", value: model.artifactState.resentment, detail: "Gameplay State，不属于 Canon 数值。",
            systemIcon: "waveform.path.ecg", tone: .amber)
        }

        ArtifactSection("投掷结果", caption: "Commit first · Presentation second", tone: .azure) {
          ViewThatFits(in: .horizontal) {
            HStack(alignment: .top, spacing: DesignTokens.Spacing.md) {
              resolutionSummary
              Spacer(minLength: DesignTokens.Spacing.md)
              rollButton
            }

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
              resolutionSummary
              rollButton
            }
          }

          if !model.history.isEmpty {
            MysticDivider(tone: .azure, label: "最近命运")
            LazyVGrid(
              columns: [GridItem(.adaptive(minimum: 72, maximum: 104), spacing: DesignTokens.Spacing.sm)],
              alignment: .leading,
              spacing: DesignTokens.Spacing.sm
            ) {
              ForEach(model.history.suffix(6)) { record in
                VStack(spacing: DesignTokens.Spacing.xxs) {
                  Text("\(record.face.rawValue)")
                    .font(Font.Mystic.titleSmall)
                    .foregroundStyle(record.face.bias.tone.readableForeground)
                  Text(record.face.bias.localizedTitle)
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textTertiary)
                    .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, minHeight: 56)
                .padding(DesignTokens.Spacing.sm)
                .background(Color.Mystic.obsidianElevated)
                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
              }
            }
          }
        }
      }
    }
  }

  private var dieHeaderText: some View {
    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
      Text("命运偏转")
        .font(Font.Mystic.titleMedium)
        .foregroundStyle(Color.Mystic.textGoldAccent)
      Text("拖拽骰面后释放，或点击按钮。视觉轨迹不决定 Domain face。")
        .mysticCaptionStyle()
        .fixedSize(horizontal: false, vertical: true)
    }
  }

  private var riskPill: some View {
    ArtifactStatusPill(
      stakes.localizedTitle + "风险",
      systemImage: "exclamationmark.triangle",
      tone: stakes == .extreme ? .crimson : .amber
    )
  }

  @ViewBuilder
  private var resolutionSummary: some View {
    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
      switch model.phase {
      case .dormant:
        Text("等待一次命运偏转").mysticCaptionStyle()
      case .requesting:
        Text("Engine 正在枚举合法结果…").mysticCaptionStyle()
      case .rolling:
        Text("概率正在重排…").mysticCaptionStyle()
      case .revealed(let face):
        HStack(spacing: DesignTokens.Spacing.sm) {
          Text("\(face.rawValue)")
            .font(Font.Mystic.displayLarge)
            .foregroundStyle(face.bias.tone.readableForeground)
          MysticBadge(
            face.bias.localizedTitle,
            tone: face.bias.tone,
            systemIcon: "die.face.\(face.rawValue)"
          )
        }
      case .sealed:
        Text("封印中").mysticCaptionStyle()
      case .error(let message):
        Text(message)
          .mysticCaptionStyle(color: Color.Mystic.textPrimary)
          .fixedSize(horizontal: false, vertical: true)
      }
    }
  }

  private var rollButton: some View {
    Button {
      Task { await model.roll(context: context, stakes: stakes) }
    } label: {
      Label("投掷", systemImage: "die.face.5")
        .font(Font.Mystic.titleSmall)
    }
    .buttonStyle(WOMButtonStyle(.secondary))
    .disabled(!model.canRoll)
    .keyboardShortcut(.space, modifiers: [])
  }
}
