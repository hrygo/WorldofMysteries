import SwiftUI

// MARK: - Token-unified artifact primitives

public struct ArtifactSection<Content: View>: View {
  let title: String
  let caption: String?
  let tone: MysticTone
  @ViewBuilder let content: Content

  public init(
    _ title: String,
    caption: String? = nil,
    tone: MysticTone = .gold,
    @ViewBuilder content: () -> Content
  ) {
    self.title = title
    self.caption = caption
    self.tone = tone
    self.content = content()
  }

  public var body: some View {
    VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingMd) {
      MysticSectionHeader(title: title, caption: caption, tone: tone)
      content
    }
    .padding(DesignTokens.LayoutInsets.cardPadding)
    .background(Color.Mystic.obsidianCard.opacity(0.72))
    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
    .overlay {
      RoundedRectangle(cornerRadius: DesignTokens.Radii.md)
        .stroke(tone.accent.opacity(0.18), lineWidth: DesignTokens.Borders.hairline)
    }
  }
}

public struct ArtifactMeterCard: View {
  let title: String
  let value: Double
  let detail: String?
  let systemIcon: String?
  let tone: MysticTone

  public init(
    _ title: String,
    value: Double,
    detail: String? = nil,
    systemIcon: String? = nil,
    tone: MysticTone = .azure
  ) {
    self.title = title
    self.value = min(max(value, 0), 1)
    self.detail = detail
    self.systemIcon = systemIcon
    self.tone = tone
  }

  public var body: some View {
    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
      HStack(spacing: DesignTokens.Spacing.xs) {
        if let systemIcon {
          Image(systemName: systemIcon).foregroundStyle(tone.accent)
        }
        Text(title).font(Font.Mystic.caption).foregroundStyle(Color.Mystic.textSecondary)
        Spacer()
        Text("\(Int(value * 100))%")
          .font(Font.Mystic.monoBadge)
          .foregroundStyle(Color.Mystic.textPrimary)
      }
      MysticMetricBar(value: value, tone: tone)
      if let detail {
        Text(detail)
          .mysticCaptionStyle(color: Color.Mystic.textTertiary)
          .fixedSize(horizontal: false, vertical: true)
      }
    }
    .padding(DesignTokens.LayoutInsets.compactCardPadding)
    .background(Color.Mystic.obsidianElevated.opacity(0.78))
    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
  }
}

public struct ArtifactStatusPill: View {
  let text: String
  let systemImage: String
  let tone: MysticTone

  public init(_ text: String, systemImage: String, tone: MysticTone) {
    self.text = text
    self.systemImage = systemImage
    self.tone = tone
  }

  public var body: some View {
    MysticBadge(text, tone: tone, systemIcon: systemImage, isEmphasized: true)
  }
}

public struct ArtifactHoldToCommitButton: View {
  let title: String
  let systemImage: String
  let tone: MysticTone
  let holdDuration: Double
  let disabled: Bool
  let action: @MainActor () -> Void

  @State private var pressing = false
  @State private var progress = 0.0
  @Environment(\.accessibilityReduceMotion) private var reduceMotion

  public init(
    _ title: String,
    systemImage: String,
    tone: MysticTone = .gold,
    holdDuration: Double = 0.8,
    disabled: Bool = false,
    action: @escaping @MainActor () -> Void
  ) {
    self.title = title
    self.systemImage = systemImage
    self.tone = tone
    self.holdDuration = holdDuration
    self.disabled = disabled
    self.action = action
  }

  public var body: some View {
    Button(action: {}) {
      HStack(spacing: DesignTokens.Spacing.sm) {
        ZStack {
          Circle().stroke(tone.accent.opacity(0.22), lineWidth: DesignTokens.Borders.standard)
          Circle()
            .trim(from: 0, to: progress)
            .stroke(
              tone.accent,
              style: StrokeStyle(lineWidth: DesignTokens.Borders.heavy, lineCap: .round)
            )
            .rotationEffect(.degrees(-90))
          Image(systemName: systemImage).font(.system(size: 10, weight: .bold)).foregroundStyle(
            tone.accent)
        }
        .frame(width: 24, height: 24)
        Text(pressing ? "保持…" : title).font(Font.Mystic.titleSmall).foregroundStyle(
          Color.Mystic.textPrimary)
      }
      .padding(.horizontal, DesignTokens.Spacing.md)
      .padding(.vertical, DesignTokens.Spacing.sm)
      .background(Color.Mystic.obsidianCard)
      .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
      .overlay {
        RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
          .stroke(tone.accent.opacity(0.5), lineWidth: DesignTokens.Borders.standard)
      }
    }
    .buttonStyle(MysticPressableButtonStyle())
    .disabled(disabled)
    .onLongPressGesture(
      minimumDuration: holdDuration,
      maximumDistance: 28,
      pressing: { state in
        guard !disabled else { return }
        pressing = state
        if state {
          progress = 0
          withAnimation(.linear(duration: reduceMotion ? 0.12 : holdDuration)) { progress = 1 }
        } else if progress < 0.995 {
          withAnimation(DesignTokens.Interaction.hoverAnimation) { progress = 0 }
        }
      },
      perform: {
        guard !disabled else { return }
        progress = 1
        action()
        Task { @MainActor in
          try? await Task.sleep(for: .milliseconds(220))
          withAnimation(DesignTokens.Interaction.hoverAnimation) { progress = 0 }
        }
      }
    )
    .help("长按确认，避免误触不可逆操作")
    .accessibilityLabel(title)
    .accessibilityHint("长按以确认")
  }
}

public struct ArtifactComponentShell<Content: View>: View {
  let artifactID: ArtifactID
  @ViewBuilder let content: Content
  @State private var hovered = false

  public init(artifactID: ArtifactID, @ViewBuilder content: () -> Content) {
    self.artifactID = artifactID
    self.content = content()
  }

  public var body: some View {
    let descriptor = ArtifactRegistry.descriptor(for: artifactID)

    ViewThatFits(in: .horizontal) {
      HStack(spacing: 0) {
        identityPanel(descriptor)
          .frame(minWidth: 250, idealWidth: 300, maxWidth: 340)

        MysticDivider(tone: .gold).frame(width: DesignTokens.Borders.standard)

        detailPanel
          .frame(minWidth: 430)
      }

      VStack(spacing: 0) {
        identityPanel(descriptor)
          .frame(maxWidth: .infinity, minHeight: 300)

        MysticDivider(tone: .gold)
          .padding(.horizontal, DesignTokens.Spacing.lg)

        detailPanel
          .frame(maxWidth: .infinity)
      }
    }
    .frame(minHeight: 520)
    .background(Color.Mystic.obsidianBase)
    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.lg))
    .overlay {
      RoundedRectangle(cornerRadius: DesignTokens.Radii.lg)
        .stroke(
          Color.Mystic.brassGoldBorder.opacity(0.55), lineWidth: DesignTokens.Borders.standard)
    }
  }

  private func identityPanel(_ descriptor: ArtifactDescriptor) -> some View {
    ZStack {
      Color.Mystic.abyssVoid
      ArtifactAmbientField(tone: descriptor.tone, intensity: hovered ? 1 : 0.65)
      VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
        MysticBadge(
          descriptor.family.localizedTitle,
          tone: descriptor.tone,
          systemIcon: descriptor.systemIcon
        )

        WOMArtworkView(
          assetName: artifactID.artworkAsset.detailAssetName,
          fallback: .systemImage(descriptor.systemIcon),
          fallbackTint: descriptor.tone.accent,
          contentMode: .fit,
          accessibilityLabel: descriptor.displayName
        )
        .aspectRatio(1, contentMode: .fit)
        .frame(maxWidth: .infinity, maxHeight: 220)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
        .overlay {
          RoundedRectangle(cornerRadius: DesignTokens.Radii.md)
            .stroke(
              descriptor.tone.accent.opacity(hovered ? 0.42 : 0.24),
              lineWidth: DesignTokens.Borders.hairline
            )
        }

        Spacer(minLength: DesignTokens.Spacing.xs)

        Text(descriptor.displayName)
          .font(Font.Mystic.titleLarge)
          .foregroundStyle(Color.Mystic.textGoldAccent)
          .fixedSize(horizontal: false, vertical: true)

        Text(descriptor.subtitle)
          .font(Font.Mystic.monoBadge)
          .foregroundStyle(Color.Mystic.textSecondary)
          .fixedSize(horizontal: false, vertical: true)

        Text(descriptor.shortGameplay)
          .mysticCaptionStyle(color: Color.Mystic.textSecondary)
          .fixedSize(horizontal: false, vertical: true)

        LazyVGrid(
          columns: [GridItem(.adaptive(minimum: 98), spacing: DesignTokens.Spacing.xs)],
          alignment: .leading,
          spacing: DesignTokens.Spacing.xs
        ) {
          MysticBadge(descriptor.canonClass.localizedTitle, tone: .gold, systemIcon: "seal")
          MysticBadge(
            "World-bound", tone: .neutral, systemIcon: "point.3.connected.trianglepath.dotted")
        }
      }
      .padding(DesignTokens.LayoutInsets.panelPadding)
    }
    .onHover { hovered = $0 }
  }

  private var detailPanel: some View {
    ScrollView {
      content
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(DesignTokens.LayoutInsets.panelPadding)
    }
    .background(Color.Mystic.obsidianBase)
  }
}

public struct ArtifactResolutionView: View {
  @Bindable var model: ArtifactActionModel

  public init(model: ArtifactActionModel) { self.model = model }

  public var body: some View {
    switch model.phase {
    case .idle:
      EmptyView()
    case .resolving(let action):
      ArtifactSection("世界正在结算", caption: action.rawValue, tone: .amber) {
        HStack {
          ProgressView().controlSize(.small)
          Text("等待 Local Engine / Resolver 返回类型化结果。").mysticCaptionStyle()
          Spacer()
          Button("取消") { model.cancelCurrentOperation() }.mysticPressable()
        }
      }
    case .resolved:
      if let result = model.lastResolution {
        ArtifactSection(result.title, tone: severityTone(result.severity)) {
          MysticBadge(
            dispositionTitle(result.disposition), tone: dispositionTone(result.disposition),
            systemIcon: dispositionIcon(result.disposition))
          ArtifactTypewriterText(result.message)
          ForEach(result.detailLines, id: \.self) {
            Text("• \($0)")
              .mysticCaptionStyle()
              .fixedSize(horizontal: false, vertical: true)
          }
          if let followUp = result.followUpPrompt {
            MysticDivider(tone: severityTone(result.severity))
            ArtifactTypewriterText(followUp, font: Font.Mystic.narrativeSubtitle)
          }
        }
      }
    case .error(let message):
      ArtifactSection("操作失败", tone: .crimson) {
        Label(message, systemImage: "xmark.octagon.fill")
          .foregroundStyle(Color.Mystic.textPrimary)
      }
    }
  }

  private func severityTone(_ severity: ArtifactResolutionSeverity) -> MysticTone {
    switch severity {
    case .neutral: .neutral
    case .favorable: .teal
    case .warning: .amber
    case .dangerous: .crimson
    }
  }
  private func dispositionTone(_ value: ArtifactCommitDisposition) -> MysticTone {
    switch value {
    case .observation: .azure
    case .proposed: .amber
    case .committed: .teal
    case .rejected: .crimson
    }
  }
  private func dispositionTitle(_ value: ArtifactCommitDisposition) -> String {
    switch value {
    case .observation: "观察"
    case .proposed: "候选"
    case .committed: "已提交"
    case .rejected: "已阻止"
    }
  }
  private func dispositionIcon(_ value: ArtifactCommitDisposition) -> String {
    switch value {
    case .observation: "eye"
    case .proposed: "doc.badge.ellipsis"
    case .committed: "checkmark.seal"
    case .rejected: "hand.raised"
    }
  }
}

public struct ArtifactActionHistoryView: View {
  let model: ArtifactActionModel
  let maxRows: Int
  public init(model: ArtifactActionModel, maxRows: Int = 5) {
    self.model = model
    self.maxRows = maxRows
  }

  public var body: some View {
    if model.history.isEmpty {
      MysticEmptyState(
        systemIcon: "clock.arrow.circlepath", title: "尚无交互记录", message: "最近的类型化结果会显示在这里。",
        tone: .neutral)
    } else {
      VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
        ForEach(Array(model.history.suffix(maxRows).reversed())) { record in
          HStack {
            MysticStatusDot(tone: record.resolution.disposition == .committed ? .teal : .neutral)
            Text(record.resolution.title).font(Font.Mystic.caption).foregroundStyle(
              Color.Mystic.textPrimary)
            Spacer()
            Text(record.timestamp, style: .time).font(Font.Mystic.monoBadge).foregroundStyle(
              Color.Mystic.textTertiary)
          }
        }
      }
    }
  }
}
