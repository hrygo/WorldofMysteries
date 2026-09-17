import SwiftUI

// MARK: - 阿罗德斯

@MainActor
public struct ArrodesMirrorArtifactView: View {
  @Bindable private var model: ArtifactActionModel
  private let context: ArtifactContext

  @State private var question = ""
  @State private var exchangeAnswer = ""
  @State private var focus = "事件"

  public init(model: ArtifactActionModel, context: ArtifactContext) {
    self.model = model
    self.context = context
  }

  public var body: some View {
    ArtifactComponentShell(artifactID: .arrodesMirror) {
      VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
        header
        mirrorStage
        questionSection
        ArtifactResolutionView(model: model)

        if exchangeIsDue {
          exchangeSection
        }

        ArtifactSection("最近问答", tone: .neutral) {
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
        availabilityPill
      }

      VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
        headerText
        availabilityPill
      }
    }
  }

  private var headerText: some View {
    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
      Text("真相交换")
        .font(Font.Mystic.titleMedium)
        .foregroundStyle(Color.Mystic.textGoldAccent)
      Text("询问不是免费检索；回答与反问都受到知识边界约束。")
        .mysticCaptionStyle()
        .fixedSize(horizontal: false, vertical: true)
    }
  }

  private var availabilityPill: some View {
    ArtifactStatusPill(
      exchangeIsDue ? "等待交换" : "镜面可用",
      systemImage: exchangeIsDue ? "arrow.left.arrow.right" : "eye",
      tone: exchangeIsDue ? .amber : .azure
    )
  }

  private var mirrorStage: some View {
    ZStack {
      ArtifactMirrorSurface(
        active: model.isBusy || exchangeIsDue,
        warning: model.lastResolution?.severity == .dangerous
      )

      VStack(spacing: DesignTokens.Spacing.sm) {
        Image(systemName: "eye")
          .font(.system(size: 30, weight: .ultraLight))
          .foregroundStyle(Color.Mystic.spiritualBlue)
          .accessibilityHidden(true)

        Text(exchangeIsDue ? "轮到我了。" : (model.isBusy ? "镜面正在寻找可回答的真相…" : "你想知道什么？"))
          .font(Font.Mystic.narrativeSubtitle)
          .foregroundStyle(Color.Mystic.textPrimary)
          .multilineTextAlignment(.center)
          .fixedSize(horizontal: false, vertical: true)
      }
      .padding(DesignTokens.Spacing.md)
    }
    .frame(height: 190)
    .background(Color.Mystic.abyssVoid)
    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
    .overlay(
      RoundedRectangle(cornerRadius: DesignTokens.Radii.md).stroke(
        Color.Mystic.spiritualBlue.opacity(0.25),
        lineWidth: DesignTokens.Borders.hairline
      )
    )
  }

  private var questionSection: some View {
    ArtifactSection(
      "提出问题",
      caption: "Question → Context Compiler → Reveal Policy → Answer",
      tone: .azure
    ) {
      LazyVGrid(
        columns: [GridItem(.adaptive(minimum: 82, maximum: 120), spacing: DesignTokens.Spacing.xs)],
        alignment: .leading,
        spacing: DesignTokens.Spacing.xs
      ) {
        ForEach(["人物", "事件", "地点", "物品"], id: \.self) { item in
          Button {
            focus = item
          } label: {
            MysticBadge(
              item,
              tone: focus == item ? .azure : .neutral,
              systemIcon: focusIcon(item),
              isEmphasized: focus == item
            )
          }
          .buttonStyle(.plain)
          .accessibilityLabel("询问范围：\(item)")
          .accessibilityValue(focus == item ? "已选中" : "未选中")
        }
      }

      TextEditor(text: $question)
        .font(Font.Mystic.narrativeSubtitle)
        .foregroundStyle(Color.Mystic.textPrimary)
        .scrollContentBackground(.hidden)
        .frame(minHeight: 96)
        .padding(DesignTokens.Spacing.sm)
        .background(Color.Mystic.abyssVoid.opacity(0.72))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))

      ViewThatFits(in: .horizontal) {
        HStack(spacing: DesignTokens.Spacing.md) {
          questionCount
          Spacer(minLength: DesignTokens.Spacing.md)
          askButton
        }

        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
          questionCount
          askButton
        }
      }
    }
  }

  private var questionCount: some View {
    Text("\(question.count) 字")
      .font(Font.Mystic.monoBadge)
      .foregroundStyle(Color.Mystic.textTertiary)
  }

  private var askButton: some View {
    Button {
      ask()
    } label: {
      Label("询问阿罗德斯", systemImage: "sparkles")
        .font(Font.Mystic.titleSmall)
    }
    .buttonStyle(WOMButtonStyle(.secondary))
    .disabled(
      question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || model.isBusy
        || exchangeIsDue
    )
  }

  private var exchangeSection: some View {
    ArtifactSection("对等原则", caption: "回答或拒绝都形成后果", tone: .amber) {
      if let prompt = model.lastResolution?.followUpPrompt {
        ArtifactTypewriterText(
          "“\(prompt)”",
          font: Font.Mystic.narrativeSubtitle,
          intervalSeconds: DesignTokens.Motion.typewriterInterval
        )
      }

      TextEditor(text: $exchangeAnswer)
        .font(Font.Mystic.bodyMedium)
        .foregroundStyle(Color.Mystic.textPrimary)
        .scrollContentBackground(.hidden)
        .frame(minHeight: 76)
        .padding(DesignTokens.Spacing.sm)
        .background(Color.Mystic.abyssVoid.opacity(0.72))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))

      ViewThatFits(in: .horizontal) {
        HStack(spacing: DesignTokens.Spacing.md) {
          refuseExchangeButton
          Spacer(minLength: DesignTokens.Spacing.md)
          completeExchangeButton
        }

        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
          refuseExchangeButton
          completeExchangeButton
        }
      }
    }
  }

  private var refuseExchangeButton: some View {
    Button("拒绝回答") {
      model.performDetached(
        .init(
          artifactID: .arrodesMirror,
          action: .refuseExchange,
          context: context,
          input: "refused"
        )
      )
    }
    .buttonStyle(WOMButtonStyle(.danger))
  }

  private var completeExchangeButton: some View {
    ArtifactHoldToCommitButton(
      "完成交换",
      systemImage: "arrow.left.arrow.right",
      tone: .azure,
      disabled: exchangeAnswer.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    ) {
      let answer = exchangeAnswer
      Task {
        await model.perform(
          .init(
            artifactID: .arrodesMirror,
            action: .answerExchange,
            context: context,
            input: answer
          )
        )
        if model.lastResolution?.state == "exchange_complete" {
          exchangeAnswer = ""
        }
      }
    }
  }

  private var exchangeIsDue: Bool {
    model.lastResolution?.state == "exchange_due"
  }

  private func ask() {
    let body = question.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !body.isEmpty else { return }
    model.performDetached(
      .init(
        artifactID: .arrodesMirror,
        action: .ask,
        context: context,
        input: body,
        stringParameters: ["focus": focus]
      )
    )
  }

  private func focusIcon(_ item: String) -> String {
    switch item {
    case "人物": return "person"
    case "地点": return "mappin.and.ellipse"
    case "物品": return "shippingbox"
    default: return "clock.arrow.circlepath"
    }
  }
}
