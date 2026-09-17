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
        HStack {
          VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
            Text("世界内通信").font(Font.Mystic.titleMedium).foregroundStyle(Color.Mystic.textGoldAccent)
            Text("Compose → Seal → Messenger → Transit → Delivery → CharacterKnowledge")
              .font(Font.Mystic.monoBadge).foregroundStyle(Color.Mystic.textTertiary)
          }
          Spacer()
          ArtifactStatusPill(
            sealed ? "已封缄" : "正在书写", systemImage: sealed ? "envelope.fill" : "square.and.pencil",
            tone: sealed ? .teal : .neutral)
        }

        ArtifactSection("信件", caption: "送出后进入真实 Message / Event 流", tone: .teal) {
          Picker("收信人", selection: $recipient) {
            ForEach(recipients, id: \.self) { Text($0).tag($0) }
          }
          .disabled(sealed)

          TextEditor(text: $letter)
            .font(Font.Mystic.narrativeSubtitle)
            .scrollContentBackground(.hidden)
            .frame(minHeight: 130)
            .padding(DesignTokens.Spacing.sm)
            .background(Color.Mystic.abyssVoid.opacity(0.72))
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
            .disabled(sealed)

          HStack {
            Text("\(letter.count) 字").font(Font.Mystic.monoBadge).foregroundStyle(
              Color.Mystic.textTertiary)
            Spacer()
            if sealed {
              Button("拆开重写") { sealed = false }.mysticPressable()
            } else {
              Button {
                sealed = true
              } label: {
                Label("封缄", systemImage: "seal")
              }
              .mysticPressable()
              .disabled(
                recipient.isEmpty || letter.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
          }
        }

        if sealed {
          ArtifactSection("召唤白骨信使", caption: "送达速度、可达性与死灵副作用由 Engine 决定", tone: .teal) {
            ZStack {
              ArtifactAmbientField(tone: .teal, intensity: 0.85, particleCount: 18)
              HStack(spacing: DesignTokens.Spacing.lg) {
                Image(systemName: "person.crop.circle.badge.clock")
                  .font(.system(size: 40, weight: .ultraLight))
                  .foregroundStyle(Color.Mystic.statusOnline)
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
                  Text("白骨信使等待接信").font(Font.Mystic.titleSmall).foregroundStyle(
                    Color.Mystic.textPrimary)
                  Text("Recipient · \(recipient)").font(Font.Mystic.monoBadge).foregroundStyle(
                    Color.Mystic.textTertiary)
                }
                Spacer()
              }
              .padding(DesignTokens.Spacing.md)
            }
            .frame(height: 100)
            .background(Color.Mystic.abyssVoid)
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))

            HStack {
              MysticBadge("世界内运输", tone: .teal, systemIcon: "figure.walk.motion")
              Spacer()
              ArtifactHoldToCommitButton(
                "吹响铜哨并送出", systemImage: "waveform", tone: .teal, disabled: model.isBusy
              ) {
                let target = recipient
                let body = letter
                Task {
                  await model.perform(
                    .init(
                      artifactID: .azikCopperWhistle, action: .sendLetter, context: context,
                      input: body, selectionIDs: [target]))
                  if model.lastResolution?.disposition == .committed {
                    lastSentRecipient = target
                    sealed = false
                    letter = ""
                  }
                }
              }
            }
          }
        }

        ArtifactResolutionView(model: model)

        if let lastSentRecipient {
          ArtifactSection("最近一次投递", caption: "最终 Delivery 状态应由 Local Engine 更新", tone: .teal) {
            HStack(spacing: 0) {
              timelineNode("已交付", icon: "envelope.fill", active: true)
              timelineLine(active: true)
              timelineNode("运输中", icon: "figure.walk.motion", active: true)
              timelineLine(active: false)
              timelineNode("待送达", icon: "person.crop.circle", active: false)
            }
            Text("目标 · \(lastSentRecipient)").font(Font.Mystic.monoBadge).foregroundStyle(
              Color.Mystic.textTertiary)
          }
        }
      }
    }
  }

  private func timelineNode(_ title: String, icon: String, active: Bool) -> some View {
    VStack(spacing: DesignTokens.Spacing.xs) {
      ZStack {
        Circle().fill(
          active ? Color.Mystic.statusOnline.opacity(0.16) : Color.Mystic.obsidianElevated
        ).frame(width: 34, height: 34)
        Image(systemName: icon).font(.system(size: 11)).foregroundStyle(
          active ? Color.Mystic.statusOnline : Color.Mystic.textTertiary)
      }
      Text(title).font(.system(size: 9)).foregroundStyle(Color.Mystic.textTertiary)
    }
  }

  private func timelineLine(active: Bool) -> some View {
    Rectangle().fill(
      active ? Color.Mystic.statusOnline.opacity(0.45) : Color.Mystic.brassGoldBorder.opacity(0.35)
    ).frame(height: DesignTokens.Borders.hairline).frame(maxWidth: .infinity).padding(
      .horizontal, DesignTokens.Spacing.xs)
  }
}
