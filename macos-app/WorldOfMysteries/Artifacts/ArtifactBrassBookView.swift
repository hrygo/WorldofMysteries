import SwiftUI

// MARK: - 特伦索斯特黄铜书

@MainActor
public struct TrunsoestBrassBookArtifactView: View {
  @Bindable private var model: ArtifactActionModel
  private let context: ArtifactContext

  @State private var ruleText = ""
  @State private var scope = "scene"
  @State private var enforcement = "standard"
  @State private var activeRules: [String]

  public init(model: ArtifactActionModel, context: ArtifactContext, activeRules: [String] = []) {
    self.model = model
    self.context = context
    self._activeRules = State(initialValue: activeRules)
  }

  public var body: some View {
    ArtifactComponentShell(artifactID: .trunsoestBrassBook) {
      VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
        header

        ArtifactMeterCard(
          "规则压力",
          value: model.meters["rulePressure"] ?? 0.18,
          detail: "规则越多、越强，环境越接近高压裁决状态。",
          systemIcon: "scalemass",
          tone: .amber
        )

        ArtifactSection("黄铜页", caption: "已提交且正在当前作用域生效的规则", tone: .gold) {
          if activeRules.isEmpty {
            MysticEmptyState(
              systemIcon: "book.pages",
              title: "暂无新增规则",
              message: "页面暂时保持沉默。",
              tone: .gold
            )
          } else {
            ForEach(Array(activeRules.enumerated()), id: \.offset) { index, rule in
              HStack(alignment: .top, spacing: DesignTokens.Spacing.sm) {
                Text("§\(index + 1)")
                  .font(Font.Mystic.monoBadge)
                  .foregroundStyle(Color.Mystic.brassGoldPrimary)
                ArtifactTypewriterText(rule, font: Font.Mystic.bodyMedium)
                  .frame(maxWidth: .infinity, alignment: .leading)
              }
              .padding(DesignTokens.Spacing.sm)
              .background(Color.Mystic.obsidianElevated)
              .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
            }
          }
        }

        candidateRuleSection
        ArtifactResolutionView(model: model)
        ArtifactSection("裁决记录", tone: .neutral) {
          ArtifactActionHistoryView(model: model)
        }
      }
    }
  }

  private var header: some View {
    ViewThatFits(in: .horizontal) {
      HStack(alignment: .top, spacing: DesignTokens.Spacing.md) {
        headerText
        Spacer(minLength: DesignTokens.Spacing.md)
        activeRulePill
      }

      VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
        headerText
        activeRulePill
      }
    }
  }

  private var headerText: some View {
    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
      Text("规则覆盖层")
        .font(Font.Mystic.titleMedium)
        .foregroundStyle(Color.Mystic.textGoldAccent)
      Text("规则不是 UI 禁用；角色仍可违规，然后由世界法则裁决。")
        .mysticCaptionStyle()
        .fixedSize(horizontal: false, vertical: true)
    }
  }

  private var activeRulePill: some View {
    ArtifactStatusPill(
      "\(activeRules.count) 条有效规则",
      systemImage: "book.closed",
      tone: .gold
    )
  }

  private var candidateRuleSection: some View {
    ArtifactSection(
      "候选规则",
      caption: "Rule Candidate → Hard Gates → Rule Validator → COMMIT",
      tone: .amber
    ) {
      TextEditor(text: $ruleText)
        .font(Font.Mystic.narrativeSubtitle)
        .foregroundStyle(Color.Mystic.textPrimary)
        .scrollContentBackground(.hidden)
        .frame(minHeight: 96)
        .padding(DesignTokens.Spacing.sm)
        .background(Color.Mystic.abyssVoid.opacity(0.72))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))

      ViewThatFits(in: .horizontal) {
        HStack(spacing: DesignTokens.Spacing.md) {
          scopePicker
            .frame(maxWidth: .infinity)
          enforcementPicker
            .frame(width: 140)
        }

        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
          scopePicker
          enforcementPicker
        }
      }

      ViewThatFits(in: .horizontal) {
        HStack(spacing: DesignTokens.Spacing.md) {
          rulePrincipleBadge
          Spacer(minLength: DesignTokens.Spacing.md)
          commitRuleButton
        }

        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
          rulePrincipleBadge
          commitRuleButton
        }
      }
    }
  }

  private var scopePicker: some View {
    Picker("作用域", selection: $scope) {
      Text("场景").tag("scene")
      Text("地点").tag("location")
      Text("本篇").tag("episode")
    }
    .pickerStyle(.segmented)
  }

  private var enforcementPicker: some View {
    Picker("裁决", selection: $enforcement) {
      Text("常规").tag("standard")
      Text("严格").tag("strict")
      Text("绝对").tag("absolute")
    }
  }

  private var rulePrincipleBadge: some View {
    MysticBadge(
      "违反 ≠ 禁止操作",
      tone: .amber,
      systemIcon: "exclamationmark.shield"
    )
  }

  private var commitRuleButton: some View {
    ArtifactHoldToCommitButton(
      "写入黄铜页",
      systemImage: "text.book.closed",
      tone: .gold,
      disabled: ruleText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || model.isBusy
    ) {
      let candidate = ruleText.trimmingCharacters(in: .whitespacesAndNewlines)
      Task {
        await model.perform(
          .init(
            artifactID: .trunsoestBrassBook,
            action: .enactRule,
            context: context,
            input: candidate,
            stringParameters: ["scope": scope, "enforcement": enforcement]
          )
        )
        if model.lastResolution?.disposition == .committed, !candidate.isEmpty {
          activeRules.append(candidate)
          ruleText = ""
        }
      }
    }
  }
}
