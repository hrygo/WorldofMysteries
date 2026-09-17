import SwiftUI

/// Fate 页面中的世界内特殊物品入口。
///
/// 这里不是第二套“道具背包”导航，而是把少数高影响 Artifact 作为命运干预工具，
/// 直接嵌入当前 Story / World 上下文。生产态只使用 Local Engine IPC；引擎未连接时
/// 可以进入明确标识的本地 Preview，不产生持久世界事实。
@MainActor
public struct FateArtifactInterventionView: View {
  @Environment(AppState.self) private var appState

  @State private var presentedArtifact: ArtifactID?
  @State private var hoveredArtifact: ArtifactID?

  public init() {}

  public var body: some View {
    VictorianCard(style: .obsidianGlass) {
      VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
        header

        HStack(spacing: DesignTokens.Spacing.sm) {
          ForEach(Self.primaryArtifacts) { descriptor in
            quickAccessCard(descriptor)
          }
        }

        runtimeHint
      }
    }
    .sheet(item: $presentedArtifact) { artifactID in
      artifactSheet(for: artifactID)
    }
  }

  private var header: some View {
    HStack(alignment: .top, spacing: DesignTokens.Spacing.md) {
      MysticSectionHeader(
        title: "特殊物品 · 命运干预",
        caption: "只将与当前局势直接相关的高影响物品放在 Fate；完整组件库仍留在 Gallery。",
        tone: .gold,
        isProminent: true
      )

      Spacer(minLength: DesignTokens.Spacing.md)

      MysticBadge(
        runtimeBadgeText,
        tone: runtimeTone,
        variant: .panel,
        systemIcon: runtimeIcon,
        isEmphasized: true
      )
    }
  }

  private func quickAccessCard(_ descriptor: ArtifactDescriptor) -> some View {
    let isHovered = hoveredArtifact == descriptor.id
    let isEnabled = runtimeAvailability != .unavailable

    return Button {
      guard isEnabled else { return }
      presentedArtifact = descriptor.id
    } label: {
      VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
        HStack {
          ZStack {
            RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
              .fill(descriptor.tone.accent.opacity(0.12))

            Image(systemName: descriptor.systemIcon)
              .font(.system(size: 18, weight: .semibold))
              .foregroundStyle(descriptor.tone.accent)
          }
          .frame(width: 38, height: 38)

          Spacer()

          Image(systemName: "arrow.up.right")
            .font(.system(size: 10, weight: .semibold))
            .foregroundStyle(Color.Mystic.textTertiary)
        }

        Text(descriptor.displayName)
          .font(Font.Mystic.titleSmall)
          .foregroundStyle(isEnabled ? Color.Mystic.textPrimary : Color.Mystic.textTertiary)
          .lineLimit(1)

        Text(descriptor.subtitle)
          .font(Font.Mystic.monoBadge)
          .foregroundStyle(descriptor.tone.accent.opacity(isEnabled ? 0.9 : 0.45))
          .lineLimit(1)

        Text(descriptor.shortGameplay)
          .font(Font.Mystic.caption)
          .foregroundStyle(Color.Mystic.textSecondary.opacity(isEnabled ? 1 : 0.55))
          .lineLimit(3)
          .multilineTextAlignment(.leading)
      }
      .frame(maxWidth: .infinity, minHeight: 138, alignment: .topLeading)
      .padding(DesignTokens.LayoutInsets.compactCardPadding)
      .background(Color.Mystic.obsidianCard.opacity(isEnabled ? 0.72 : 0.38))
      .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
      .mysticCardSelection(isSelected: false, isHovered: isHovered)
    }
    .buttonStyle(.plain)
    .disabled(!isEnabled)
    .onHover { isHovering in
      withAnimation(DesignTokens.Interaction.hoverAnimation) {
        hoveredArtifact = isHovering ? descriptor.id : nil
      }
    }
    .help(helpText(for: descriptor))
    .accessibilityLabel("\(descriptor.displayName)，\(descriptor.shortGameplay)")
  }

  @ViewBuilder
  private var runtimeHint: some View {
    switch runtimeAvailability {
    case .preview:
      HStack(spacing: DesignTokens.Spacing.xs) {
        MysticStatusDot(tone: .amber, diameter: 7, isPulsing: true)
        Text("当前为演示模式：Artifact 仅运行本地 Preview Resolver，不写入世界状态。")
          .mysticCaptionStyle(color: Color.Mystic.statusWarning)
      }

    case .live:
      HStack(spacing: DesignTokens.Spacing.xs) {
        MysticStatusDot(tone: .teal, diameter: 7, isPulsing: true)
        Text("已绑定活动 Worldline / Story Revision；所有效果通过 Local Engine IPC 提交。")
          .mysticCaptionStyle(color: Color.Mystic.statusOnline)
      }

    case .unavailable:
      HStack(spacing: DesignTokens.Spacing.xs) {
        MysticStatusDot(tone: .amber, diameter: 7)
        Text("Local Engine 已连接，但尚未提供活动世界上下文。为避免伪造世界事实，特殊物品暂不可用。")
          .mysticCaptionStyle(color: Color.Mystic.statusWarning)
      }
    }
  }

  @ViewBuilder
  private func artifactSheet(for artifactID: ArtifactID) -> some View {
    switch runtimeAvailability {
    case .preview:
      PreviewFateArtifactSheet(artifactID: artifactID)
        .frame(minWidth: 980, minHeight: 680)

    case .live:
      if let context = appState.activeArtifactContext {
        LiveFateArtifactSheet(
          artifactID: artifactID,
          context: context,
          client: appState.ipcClient
        )
        .frame(minWidth: 980, minHeight: 680)
      } else {
        unavailableSheet
      }

    case .unavailable:
      unavailableSheet
    }
  }

  private var unavailableSheet: some View {
    ContentUnavailableView(
      "缺少活动世界上下文",
      systemImage: "lock.shield",
      description: Text("等待 World / Story Session 向 AppState 注入 ArtifactContext 后再使用。")
    )
    .frame(minWidth: 720, minHeight: 420)
    .background(Color.Mystic.obsidianBase)
  }

  private var runtimeAvailability: ArtifactRuntimeAvailability {
    ArtifactRuntimeAvailability.resolve(
      engineReady: appState.isEngineReady,
      hasActiveContext: appState.activeArtifactContext != nil
    )
  }

  private var runtimeBadgeText: String {
    switch runtimeAvailability {
    case .preview: return "Preview"
    case .live: return "Engine Live"
    case .unavailable: return "Awaiting Context"
    }
  }

  private var runtimeTone: MysticTone {
    switch runtimeAvailability {
    case .preview, .unavailable: return .amber
    case .live: return .teal
    }
  }

  private var runtimeIcon: String {
    switch runtimeAvailability {
    case .preview: return "play.rectangle"
    case .live: return "bolt.horizontal.circle.fill"
    case .unavailable: return "lock.shield"
    }
  }

  private func helpText(for descriptor: ArtifactDescriptor) -> String {
    switch runtimeAvailability {
    case .preview:
      return "打开 \(descriptor.displayName) 的非持久化交互预览"
    case .live:
      return "在当前世界上下文中使用 \(descriptor.displayName)"
    case .unavailable:
      return "等待活动 World / Story Context"
    }
  }

  private static let primaryArtifacts: [ArtifactDescriptor] = [
    ArtifactRegistry.descriptor(for: .probabilityDie),
    ArtifactRegistry.descriptor(for: .arrodesMirror),
    ArtifactRegistry.descriptor(for: .alzuhodQuill),
    ArtifactRegistry.descriptor(for: .trunsoestBrassBook),
    ArtifactRegistry.descriptor(for: .magicWishingLamp),
  ]
}

/// 明确区分 App 的三种运行态，避免“引擎已连接但缺少 Domain Context”时退回假数据。
public enum ArtifactRuntimeAvailability: Equatable, Sendable {
  case preview
  case live
  case unavailable

  public static func resolve(engineReady: Bool, hasActiveContext: Bool) -> Self {
    if !engineReady { return .preview }
    return hasActiveContext ? .live : .unavailable
  }
}

@MainActor
private struct PreviewFateArtifactSheet: View {
  let artifactID: ArtifactID

  @State private var genericModel = ArtifactActionModel(
    resolver: PreviewArtifactResolver(),
    meters: [
      "exchangeDebt": 0.12,
      "rulePressure": 0.18,
      "wishExposure": 0.08,
    ]
  )
  @State private var dieModel = ProbabilityDieModel(
    artifactState: .init(awakening: 0.22, resentment: 0.08, sealed: false),
    resolver: PreviewProbabilityDieResolver()
  )
  @State private var quillModel = AlzuhodQuillModel(
    artifactState: .init(awakening: 0.18, exposure: 0.12, narrativeDebt: 0.8, sealed: false),
    orchestrator: PreviewAlzuhodQuillOrchestrator()
  )

  var body: some View {
    VStack(spacing: 0) {
      previewBanner

      ScrollView {
        selectedArtifact
          .padding(DesignTokens.LayoutInsets.panelPadding)
      }
    }
    .background(Color.Mystic.obsidianBase)
  }

  private var previewBanner: some View {
    HStack(spacing: DesignTokens.Spacing.sm) {
      MysticBadge(
        "PREVIEW ONLY",
        tone: .amber,
        variant: .panel,
        systemIcon: "play.rectangle",
        isEmphasized: true
      )
      Text("此窗口不会通过 IPC 提交 World / Story State。")
        .mysticCaptionStyle(color: Color.Mystic.statusWarning)
      Spacer()
    }
    .padding(.horizontal, DesignTokens.Spacing.xl)
    .padding(.vertical, DesignTokens.Spacing.md)
    .background(Color.Mystic.statusWarning.opacity(0.08))
  }

  @ViewBuilder
  private var selectedArtifact: some View {
    switch artifactID {
    case .probabilityDie:
      ProbabilityDieArtifactView(model: dieModel, context: Self.previewContext, stakes: .high)
    case .arrodesMirror:
      ArrodesMirrorArtifactView(model: genericModel, context: Self.previewContext)
    case .alzuhodQuill:
      AlzuhodQuillArtifactView(model: quillModel, context: Self.previewContext)
    case .trunsoestBrassBook:
      TrunsoestBrassBookArtifactView(
        model: genericModel,
        context: Self.previewContext,
        activeRules: ["午夜以后，未经允许者不得进入档案室。"]
      )
    case .magicWishingLamp:
      MagicWishingLampArtifactView(model: genericModel, context: Self.previewContext)
    default:
      ContentUnavailableView(
        "Fate 快捷入口未启用此物品",
        systemImage: "square.grid.2x2",
        description: Text("完整 15 件特殊物品组件请在 Gallery 中查看。")
      )
    }
  }

  private static let previewContext = ArtifactContext(
    worldID: "preview.world",
    worldlineID: "preview.main",
    storySessionID: "preview.fate",
    storyRevision: 0,
    actorID: "preview.actor"
  )
}

@MainActor
private struct LiveFateArtifactSheet: View {
  let artifactID: ArtifactID
  let context: ArtifactContext

  @State private var genericModel: ArtifactActionModel
  @State private var dieModel: ProbabilityDieModel
  @State private var quillModel: AlzuhodQuillModel

  init(artifactID: ArtifactID, context: ArtifactContext, client: EngineIPCClient) {
    self.artifactID = artifactID
    self.context = context
    self._genericModel = State(
      initialValue: ArtifactActionModel(
        resolver: EngineArtifactActionResolver(client: client)
      )
    )
    self._dieModel = State(
      initialValue: ProbabilityDieModel(
        artifactState: .init(awakening: 0, resentment: 0, sealed: false),
        resolver: EngineProbabilityDieResolver(client: client)
      )
    )
    self._quillModel = State(
      initialValue: AlzuhodQuillModel(
        artifactState: .init(awakening: 0, exposure: 0, narrativeDebt: 0, sealed: false),
        orchestrator: EngineAlzuhodQuillOrchestrator(client: client)
      )
    )
  }

  var body: some View {
    VStack(spacing: 0) {
      liveBanner

      ScrollView {
        selectedArtifact
          .padding(DesignTokens.LayoutInsets.panelPadding)
      }
    }
    .background(Color.Mystic.obsidianBase)
  }

  private var liveBanner: some View {
    HStack(spacing: DesignTokens.Spacing.sm) {
      MysticBadge(
        "ENGINE LIVE",
        tone: .teal,
        variant: .panel,
        systemIcon: "bolt.horizontal.circle.fill",
        isEmphasized: true
      )
      Text(
        "Worldline · \(context.worldlineID) · Revision \(context.storyRevision.map { String($0) } ?? "—")"
      )
      .font(Font.Mystic.monoBadge)
      .foregroundStyle(Color.Mystic.textSecondary)
      Spacer()
    }
    .padding(.horizontal, DesignTokens.Spacing.xl)
    .padding(.vertical, DesignTokens.Spacing.md)
    .background(Color.Mystic.statusOnline.opacity(0.06))
  }

  @ViewBuilder
  private var selectedArtifact: some View {
    switch artifactID {
    case .probabilityDie:
      ProbabilityDieArtifactView(model: dieModel, context: context, stakes: .high)
    case .arrodesMirror:
      ArrodesMirrorArtifactView(model: genericModel, context: context)
    case .alzuhodQuill:
      AlzuhodQuillArtifactView(model: quillModel, context: context)
    case .trunsoestBrassBook:
      TrunsoestBrassBookArtifactView(model: genericModel, context: context)
    case .magicWishingLamp:
      MagicWishingLampArtifactView(model: genericModel, context: context)
    default:
      ContentUnavailableView(
        "当前 Fate 快捷入口未启用此物品",
        systemImage: "square.grid.2x2",
        description: Text("完整特殊物品组件库仍可在 Gallery 中浏览。")
      )
    }
  }
}
