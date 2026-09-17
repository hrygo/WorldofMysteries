import SwiftUI

/// 15 件 Canon Artifact Gameplay Component 的统一预览入口。
/// 使用 `Preview*Resolver` 仅用于画廊演示；生产态应注入 Local Engine IPC Adapter。
@MainActor
public struct ArtifactShowcaseView: View {
  @State private var selection: ArtifactID = .probabilityDie
  @State private var searchText = ""

  @State private var genericModel = ArtifactActionModel(
    resolver: PreviewArtifactResolver(),
    meters: [
      "exchangeDebt": 0.12,
      "rulePressure": 0.18,
      "wishExposure": 0.08,
      "hunger": 0.31,
      "authorityLoad": 0.14,
      "projectionConfidence": 0.68,
      "purification": 0.0,
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

  public init() {}

  public var body: some View {
    VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
      HStack(spacing: DesignTokens.Spacing.md) {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
          Text("Canon Artifact Component Library")
            .font(Font.Mystic.titleMedium)
            .foregroundStyle(Color.Mystic.textGoldAccent)
          Text("15 件原著高辨识度特殊物品 · 共用现有 DesignTokens / MysticTone / MysticPrimitives")
            .mysticCaptionStyle()
        }

        Spacer()

        TextField("搜索特殊物品", text: $searchText)
          .textFieldStyle(.roundedBorder)
          .frame(width: 190)
      }

      ScrollView(.horizontal, showsIndicators: false) {
        HStack(spacing: DesignTokens.Spacing.sm) {
          ForEach(filteredDescriptors) { descriptor in
            Button {
              withAnimation(DesignTokens.Interaction.selectionSpring) {
                selection = descriptor.id
                genericModel.resetPresentation(keepHistory: false)
              }
            } label: {
              HStack(spacing: DesignTokens.Spacing.xs) {
                Image(systemName: descriptor.systemIcon)
                Text(descriptor.displayName)
              }
              .font(Font.Mystic.caption)
              .foregroundStyle(
                selection == descriptor.id ? descriptor.tone.accent : Color.Mystic.textSecondary
              )
              .padding(.horizontal, DesignTokens.Spacing.md)
              .padding(.vertical, DesignTokens.Spacing.sm)
              .background(Color.Mystic.obsidianElevated)
              .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
              .mysticCardSelection(isSelected: selection == descriptor.id)
            }
            .buttonStyle(.plain)
          }
        }
        .padding(.vertical, DesignTokens.Spacing.xs)
      }

      selectedComponent
    }
    .padding(DesignTokens.LayoutInsets.panelPadding)
    .background(Color.Mystic.abyssVoid.opacity(0.45))
    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.lg))
    .overlay(
      RoundedRectangle(cornerRadius: DesignTokens.Radii.lg)
        .stroke(
          Color.Mystic.brassGoldBorder.opacity(0.55), lineWidth: DesignTokens.Borders.standard)
    )
  }

  private var filteredDescriptors: [ArtifactDescriptor] {
    let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !query.isEmpty else { return ArtifactRegistry.all }
    return ArtifactRegistry.all.filter {
      $0.displayName.localizedCaseInsensitiveContains(query)
        || $0.subtitle.localizedCaseInsensitiveContains(query)
        || $0.shortGameplay.localizedCaseInsensitiveContains(query)
    }
  }

  @ViewBuilder
  private var selectedComponent: some View {
    switch selection {
    case .probabilityDie:
      ProbabilityDieArtifactView(model: dieModel, context: context, stakes: .high)
    case .arrodesMirror:
      ArrodesMirrorArtifactView(model: genericModel, context: context)
    case .alzuhodQuill:
      AlzuhodQuillArtifactView(model: quillModel, context: context)
    case .trunsoestBrassBook:
      TrunsoestBrassBookArtifactView(
        model: genericModel,
        context: context,
        activeRules: [
          "午夜以后，未经允许者不得进入档案室。",
          "禁止故意破坏本区域封印结构。",
        ]
      )
    case .magicWishingLamp:
      MagicWishingLampArtifactView(model: genericModel, context: context)
    case .creepingHunger:
      CreepingHungerArtifactView(model: genericModel, context: context, souls: souls)
    case .leymanoTravels:
      LeymanoTravelsArtifactView(model: genericModel, context: context, pages: pages)
    case .groselleTravels:
      GroselleTravelsArtifactView(
        model: genericModel, context: context,
        participantIDs: ["character.demo", "character.companion"])
    case .azikCopperWhistle:
      AzikCopperWhistleArtifactView(
        model: genericModel, context: context, recipients: ["阿兹克·艾格斯", "character.companion"])
    case .cardsOfBlasphemy:
      CardsOfBlasphemyArtifactView(model: genericModel, context: context, cards: pathwayCards)
    case .seaGodScepter:
      SeaGodScepterArtifactView(model: genericModel, context: context, prayers: prayers)
    case .staffOfStars:
      StaffOfStarsArtifactView(model: genericModel, context: context, knowledgeCompleteness: 0.68)
    case .boxOfGreatOldOnes:
      BoxOfGreatOldOnesArtifactView(model: genericModel, context: context)
    case .deathKnell:
      DeathKnellArtifactView(
        model: genericModel, context: context, targetID: "entity.demo.target",
        weaknesses: weaknesses, roundsRemaining: 5)
    case .unshadowedCrucifix:
      UnshadowedCrucifixArtifactView(
        model: genericModel, context: context,
        targetIDs: ["material.polluted.001", "material.characteristic.002"])
    }
  }

  private var context: ArtifactContext {
    .init(
      worldID: "world.demo",
      worldlineID: "main",
      storySessionID: "story.demo",
      storyRevision: 7,
      actorID: "character.demo"
    )
  }

  private var souls: [GrazedSoulSlot] {
    [
      .init(
        id: "soul.demo.1", displayName: "示例灵魂 A", pathway: "Pathway Unknown",
        abilityNames: ["能力 A", "能力 B"]),
      .init(
        id: "soul.demo.2", displayName: "示例灵魂 B", pathway: "Pathway Unknown", abilityNames: ["能力 C"]
      ),
    ]
  }

  private var pages: [RecordedAbilityPage] {
    [
      .init(id: "page.1", page: 1, abilityName: "记录能力 A", sourceCharacterID: "character.x"),
      .init(id: "page.2", page: 2),
      .init(id: "page.3", page: 3),
      .init(id: "page.4", page: 4),
    ]
  }

  private var pathwayCards: [BlasphemyPathwayCardState] {
    [
      .init(id: "pathway.fool", displayName: "愚者途径", revealFraction: 0.35),
      .init(id: "pathway.door", displayName: "门途径", revealFraction: 0.18),
      .init(id: "pathway.error", displayName: "错误途径", revealFraction: 0.05),
    ]
  }

  private var prayers: [ArtifactPrayerItem] {
    [
      .init(id: "prayer.1", petitioner: "示例信徒", summary: "请求海上风暴暂时平息。"),
      .init(id: "prayer.2", petitioner: "示例船员", summary: "祈求在迷雾中找到航路。"),
    ]
  }

  private var weaknesses: [KnownArtifactWeakness] {
    [
      .init(id: "weakness.1", title: "已观察到的结构弱点", confidence: 0.82),
      .init(id: "weakness.2", title: "疑似灵体连接薄弱处", confidence: 0.56),
    ]
  }
}
