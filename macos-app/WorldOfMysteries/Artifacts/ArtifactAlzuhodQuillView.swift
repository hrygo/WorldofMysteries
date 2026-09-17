import SwiftUI

// MARK: - 阿勒苏霍德之笔

@MainActor
public struct AlzuhodQuillArtifactView: View {
  @Bindable private var model: AlzuhodQuillModel
  private let context: ArtifactContext

  public init(model: AlzuhodQuillModel, context: ArtifactContext) {
    self.model = model
    self.context = context
  }

  public var body: some View {
    ArtifactComponentShell(artifactID: .alzuhodQuill) {
      VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
        HStack(spacing: DesignTokens.Spacing.md) {
          ArtifactMeterCard(
            "苏醒", value: model.artifactState.awakening, detail: "自主书写风险", systemIcon: "eye",
            tone: .amber)
          ArtifactMeterCard(
            "暴露", value: model.artifactState.exposure, detail: "它知道你的程度",
            systemIcon: "person.crop.circle.badge.questionmark", tone: .azure)
          VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
            Text("叙事债").font(Font.Mystic.caption).foregroundStyle(Color.Mystic.textSecondary)
            Text(model.artifactState.narrativeDebt.formatted(.number.precision(.fractionLength(1))))
              .font(Font.Mystic.displayLarge)
              .foregroundStyle(Color.Mystic.statusWarning)
            Text("Gameplay abstraction").mysticCaptionStyle(color: Color.Mystic.textTertiary)
          }
          .padding(DesignTokens.LayoutInsets.compactCardPadding)
          .background(Color.Mystic.obsidianElevated)
          .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
        }

        ArtifactSection("写下目标", caption: "写的是 Desired Outcome，不是数据库命令", tone: .amber) {
          TextEditor(text: $model.desiredOutcome)
            .font(Font.Mystic.narrativeSubtitle)
            .scrollContentBackground(.hidden)
            .padding(DesignTokens.Spacing.sm)
            .frame(minHeight: 120)
            .background(Color.Mystic.abyssVoid.opacity(0.75))
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
            .onTapGesture { model.beginEditing() }

          HStack {
            Picker("范围", selection: $model.horizon) {
              ForEach(QuillHorizon.allCases, id: \.self) { horizon in
                Text(horizon.localizedTitle).tag(horizon)
              }
            }
            .pickerStyle(.segmented)

            Picker("风险", selection: $model.riskTolerance) {
              ForEach(ArtifactRiskBand.allCases, id: \.self) { risk in
                Text(risk.localizedTitle).tag(risk)
              }
            }
            .frame(width: 140)
          }
        }

        quillState

        HStack {
          if model.draft != nil {
            Button("撤回草稿") { model.discardDraft() }
              .mysticPressable()
          }
          Spacer()
          if model.phase == .awaitingConfirmation {
            ArtifactHoldToCommitButton(
              "让它落笔", systemImage: "pencil.tip", tone: .amber, holdDuration: 0.95
            ) {
              Task { await model.commit(context: context) }
            }
          } else {
            Button {
              Task { await model.requestDraft(context: context) }
            } label: {
              Label("构造合理的发展", systemImage: "point.3.connected.trianglepath.dotted")
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.textPrimary)
            }
            .mysticPressable()
            .disabled(!model.canDraft)
          }
        }
      }
    }
  }

  @ViewBuilder
  private var quillState: some View {
    switch model.phase {
    case .drafting:
      ArtifactSection("构造因果链", tone: .amber) {
        HStack {
          ProgressView()
          Text("正在寻找足够合理的桥接事件…").mysticCaptionStyle()
        }
      }
    case .awaitingConfirmation:
      if let draft = model.draft {
        ArtifactSection("因果草稿", caption: "隐藏节点会在发生时才显露", tone: .amber) {
          ArtifactTypewriterText("“\(draft.openingSentence)”", font: Font.Mystic.narrativeSubtitle)
          HStack(spacing: DesignTokens.Spacing.sm) {
            MysticBadge(
              "\(Int(draft.coherence * 100))% 合理性", tone: draft.coherence >= 0.7 ? .teal : .amber,
              systemIcon: "point.3.connected.trianglepath.dotted")
            MysticBadge(
              "风险 \(draft.risk.localizedTitle)", tone: .amber, systemIcon: "exclamationmark.shield")
            MysticBadge(
              "叙事债 +\(draft.predictedDebt.formatted(.number.precision(.fractionLength(1))))",
              tone: .neutral, systemIcon: "scribble.variable")
          }
          ForEach(draft.causalSteps.filter { $0.visibility == .visible }) { step in
            HStack(spacing: DesignTokens.Spacing.sm) {
              MysticStatusDot(tone: .amber)
              VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
                Text(step.summary).font(Font.Mystic.bodyMedium).foregroundStyle(
                  Color.Mystic.textPrimary)
                MysticMetricBar(value: step.plausibility, tone: .amber)
              }
            }
          }
        }
      }
    case .writing:
      ArtifactSection("墨迹进入现实", caption: "COMMIT 后表达层重试不能改写因果事实", tone: .crimson) {
        ProgressView()
      }
    case .backlash:
      ArtifactSection("自主补写", tone: .crimson) {
        if let sentence = model.commitResult?.autonomousSentence {
          ArtifactTypewriterText(
            "“\(sentence)”", font: Font.Mystic.narrativeSubtitle,
            intervalSeconds: DesignTokens.Motion.typewriterInterval)
        }
      }
    case .resolved:
      ArtifactSection("已提交", tone: .teal) {
        Label("故事已经开始按照提交条件推进。", systemImage: "checkmark.seal.fill")
          .foregroundStyle(Color.Mystic.statusOnline)
      }
    case .sealed:
      ArtifactSection("封印中", tone: .neutral) { Text("不可书写。").mysticCaptionStyle() }
    case .error(let message):
      ArtifactSection("错误", tone: .crimson) {
        Text(message).mysticCaptionStyle(color: Color.Mystic.statusDanger)
      }
    default:
      ArtifactSection("书写原则", tone: .gold) {
        Label("操纵情境，不直接覆盖 Character Core", systemImage: "person.crop.circle.badge.checkmark")
        Label("不能改写已提交过去", systemImage: "clock.badge.checkmark")
        Label("Canon / Capability / Knowledge Hard Gate 仍然有效", systemImage: "lock.shield")
      }
      .font(Font.Mystic.bodyMedium)
      .foregroundStyle(Color.Mystic.textSecondary)
    }
  }
}
