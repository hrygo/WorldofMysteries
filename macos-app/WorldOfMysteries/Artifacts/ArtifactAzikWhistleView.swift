import SwiftUI

// MARK: - 阿兹克铜哨

@MainActor
public struct AzikCopperWhistleArtifactView: View {
  @Bindable private var model: ArtifactActionModel
  private let context: ArtifactContext
  private let recipients: [String]

  @State private var recipient = ""
  @State private var letter = ""
  @State private var sealed = false
  @State private var lastSentRecipient: String?

  public init(model: ArtifactActionModel, context: ArtifactContext, recipients: [String]) {
    self.model = model
    self.context = context
    self.recipients = recipients
    self._recipient = State(initialValue: recipients.first ?? "")
  }

  public var body: some View {
    ArtifactComponentShell(artifactID: .azikCopperWhistle) {
      VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
        header
        letterSection

        if sealed {
          messengerSection
        }

        ArtifactResolutionView(model: model)

        if let lastSentRecipient {
          deliverySection(lastSentRecipient)
        }
      }
    }
  }

  private var header: some View {
    ViewThatFits(in: .horizontal) {
      HStack(alignment: .top, spacing: DesignTokens.Spacing.md) {
        headerText
        Spacer(minLength: DesignTokens.Spacing.md)
        sealPill
      }

      VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
        headerText
        sealPill
      }
    }
  }

  private var headerText: some View {
    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
      Text("世界内通信")
        .font(Font.Mystic.titleMedium)
        .foregroundStyle(Color.Mystic.textGoldAccent)
      Text("Compose → Seal → Messenger → Transit → Delivery → CharacterKnowledge")
        .font(Font.Mystic.monoBadge)
        .foregroundStyle(Color.Mystic.textTertiary)
        .fixedSize(horizontal: false, vertical: true)
    }
  }

  private var sealPill: some View {
    ArtifactStatusPill(
      sealed ? "已封缄" : "正在书写",
      systemImage: sealed ? "envelope.fill" : "square.and.pencil",
      tone: sealed ? .teal : .neutral
    )
  }

  private var letterSection: some View {
    ArtifactSection("信件", caption: "送出后进入真实 Message / Event 流", tone: .teal) {
      Picker("收信人", selection: $recipient) {
        ForEach(recipients, id: \.self) { Text($0).tag($0) }
      }
      .disabled(sealed)

      TextEditor(text: $letter)
        .font(Font.Mystic.narrativeSubtitle)
        .foregroundStyle(Color.Mystic.textPrimary)
        .scrollContentBackground(.hidden)
        .frame(minHeight: 130)
        .padding(DesignTokens.Spacing.sm)
        .background(Color.Mystic.abyssVoid.opacity(0.72))
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
        .disabled(sealed)

      ViewThatFits(in: .horizontal) {
        HStack(spacing: DesignTokens.Spacing.md) {
          letterCount
          Spacer(minLength: DesignTokens.Spacing.md)
          sealAction
        }

        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
          letterCount
          sealAction
        }
      }
    }
  }

  private var letterCount: some View {
    Text("\(letter.count) 字")
      .font(Font.Mystic.monoBadge)
      .foregroundStyle(Color.Mystic.textTertiary)
  }

  @ViewBuilder
  private var sealAction: some View {
    if sealed {
      Button("拆开重写") {
        sealed = false
      }
      .buttonStyle(WOMButtonStyle(.tertiary))
    } else {
      Button {
        sealed = true
      } label: {
        Label("封缄", systemImage: "seal")
          .font(Font.Mystic.titleSmall)
      }
      .buttonStyle(WOMButtonStyle(.secondary))
      .disabled(
        recipient.isEmpty || letter.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      )
    }
  }

  private var messengerSection: some View {
    ArtifactSection("召唤白骨信使", caption: "送达速度、可达性与死灵副作用由 Engine 决定", tone: .teal) {
      ZStack {
        ArtifactAmbientField(tone: .teal, intensity: 0.85, particleCount: 18)
        HStack(spacing: DesignTokens.Spacing.lg) {
          Image(systemName: "person.crop.circle.badge.clock")
            .font(.system(size: 40, weight: .ultraLight))
            .foregroundStyle(Color.Mystic.statusOnline)
            .accessibilityHidden(true)

          VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
            Text("白骨信使等待接信")
              .font(Font.Mystic.titleSmall)
              .foregroundStyle(Color.Mystic.textPrimary)
            Text("Recipient · \(recipient)")
              .font(Font.Mystic.monoBadge)
              .foregroundStyle(Color.Mystic.textTertiary)
              .fixedSize(horizontal: false, vertical: true)
          }
          .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(DesignTokens.Spacing.md)
      }
      .frame(minHeight: 100)
      .background(Color.Mystic.abyssVoid)
      .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))

      ViewThatFits(in: .horizontal) {
        HStack(spacing: DesignTokens.Spacing.md) {
          messengerBadge
          Spacer(minLength: DesignTokens.Spacing.md)
          sendButton
        }

        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
          messengerBadge
          sendButton
        }
      }
    }
  }

  private var messengerBadge: some View {
    MysticBadge("世界内运输", tone: .teal, systemIcon: "figure.walk.motion")
  }

  private var sendButton: some View {
    ArtifactHoldToCommitButton(
      "吹响铜哨并送出",
      systemImage: "waveform",
      tone: .teal,
      disabled: model.isBusy
    ) {
      let target = recipient
      let body = letter
      Task {
        await model.perform(
          .init(
            artifactID: .azikCopperWhistle,
            action: .sendLetter,
            context: context,
            input: body,
            selectionIDs: [target]
          )
        )
        if model.lastResolution?.disposition == .committed {
          lastSentRecipient = target
          sealed = false
          letter = ""
        }
      }
    }
  }

  private func deliverySection(_ lastSentRecipient: String) -> some View {
    ArtifactSection("最近一次投递", caption: "最终 Delivery 状态应由 Local Engine 更新", tone: .teal) {
      LazyVGrid(
        columns: [GridItem(.adaptive(minimum: 98), spacing: DesignTokens.Spacing.sm)],
        alignment: .leading,
        spacing: DesignTokens.Spacing.sm
      ) {
        timelineNode("已交付", icon: "envelope.fill", active: true)
        timelineNode("运输中", icon: "figure.walk.motion", active: true)
        timelineNode("待送达", icon: "person.crop.circle", active: false)
      }

      Text("目标 · \(lastSentRecipient)")
        .font(Font.Mystic.monoBadge)
        .foregroundStyle(Color.Mystic.textTertiary)
        .fixedSize(horizontal: false, vertical: true)
    }
  }

  private func timelineNode(_ title: String, icon: String, active: Bool) -> some View {
    VStack(spacing: DesignTokens.Spacing.xs) {
      ZStack {
        Circle()
          .fill(active ? Color.Mystic.statusOnline.opacity(0.16) : Color.Mystic.obsidianElevated)
          .frame(width: 34, height: 34)
        Image(systemName: icon)
          .font(.system(size: 11))
          .foregroundStyle(active ? Color.Mystic.statusOnline : Color.Mystic.textTertiary)
      }
      .accessibilityHidden(true)

      Text(title)
        .font(Font.Mystic.caption)
        .foregroundStyle(active ? Color.Mystic.textSecondary : Color.Mystic.textTertiary)
    }
    .frame(maxWidth: .infinity, minHeight: 62)
    .padding(DesignTokens.Spacing.xs)
    .background(Color.Mystic.obsidianElevated.opacity(active ? 0.72 : 0.46))
    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
    .accessibilityElement(children: .combine)
    .accessibilityLabel(title)
  }
}
