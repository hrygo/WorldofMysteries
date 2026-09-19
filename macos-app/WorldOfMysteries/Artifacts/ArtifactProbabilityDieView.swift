import AppKit
import RealityKit
import SwiftUI
import simd

// MARK: - 概率之骰

/// 表现层：骰子真的滚。
///
/// 结果由 Domain Engine 先提交；这里只做两件事——在一族**物理合法**的投掷里挑出自然停在
/// 该面的那一掷，然后把这族解里的那一条播放出来。视觉轨迹依然不决定 Domain face。
@MainActor
public struct ProbabilityDieArtifactView: View {
  @Bindable private var model: ProbabilityDieModel
  private let context: ArtifactContext
  private let stakes: ArtifactRiskBand

  @State private var presenter = ProbabilityDiePresenter()
  @State private var planner = DieRollPlanner()
  @State private var dragVector = CGSize.zero
  @State private var isDragging = false
  @State private var lastPlan: DieRollPlan?
  @State private var planning: Task<Void, Never>?

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
            presenter.prepare()
            content.add(presenter.root)
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
          beginPhysicalRoll()
        }
        .onDisappear {
          planning?.cancel()
          presenter.stopPlayback()
        }

        physicalRollDiagnostics

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

  // MARK: 物理投掷

  /// Runs the search off the main actor, then lets the physics drive the reveal.
  private func beginPhysicalRoll() {
    guard let resolution = model.currentResolution else { return }
    let input = throwInput(for: model.throwVector)
    let planner = self.planner
    planning?.cancel()
    planning = Task { @MainActor in
      let plan = await Task.detached(priority: .userInitiated) {
        planner.plan(
          committedFace: resolution.face, seed: resolution.deterministicSeed, throwInput: input)
      }.value
      guard !Task.isCancelled else { return }
      lastPlan = plan
      if let plan {
        presenter.present(plan) { model.presentationDidSettle() }
      } else {
        // 预算内没有任何一次投掷收敛：直接揭示已提交的面，绝不用动画冒充物理。
        model.presentationDidSettle()
      }
    }
  }

  private func throwInput(for vector: CGSize) -> DieThrowInput {
    let dx = Double(vector.width)
    let dy = Double(vector.height)
    let magnitude = (dx * dx + dy * dy).squareRoot()
    guard magnitude > 1 else { return .neutral }
    // 屏幕 y 向下，世界 z 朝向观察者，所以垂直分量取反。
    let direction = SIMD2<Double>(dx / magnitude, -dy / magnitude)
    return DieThrowInput(direction: direction, impulse: min(magnitude / 900, 1))
  }

  @ViewBuilder
  private var physicalRollDiagnostics: some View {
    if let plan = lastPlan {
      HStack(spacing: DesignTokens.Spacing.sm) {
        MysticBadge(
          "物理候选 \(plan.candidatesEvaluated)",
          tone: plan.landsOnCommittedFace ? .teal : .amber,
          systemIcon: "cube.transparent")
        MysticBadge(
          String(format: "落定 %.2fs · 弹跳 %d", plan.outcome.settledTime, plan.outcome.bounces),
          tone: .azure, systemIcon: "arrow.down.to.line")
        if plan.landsOnCommittedFace {
          MysticBadge("面吻合", tone: .teal, systemIcon: "checkmark.seal")
        } else {
          MysticBadge("该掷未落到裁决面", tone: .amber, systemIcon: "exclamationmark.triangle")
        }
      }
      .font(Font.Mystic.monoBadge)
    }
  }

  private var dieHeaderText: some View {
    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
      Text("命运偏转")
        .font(Font.Mystic.titleMedium)
        .foregroundStyle(Color.Mystic.textGoldAccent)
      Text("拖拽骰面后释放，或点击按钮。引擎先裁决结果，物理再选出自然停在该面的那一掷。")
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
            systemIcon: "die.face.\(face.rawValue)")
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
