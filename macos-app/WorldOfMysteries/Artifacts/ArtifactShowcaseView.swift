import Foundation
import SwiftUI

/// 15 件 Canon Artifact Gameplay Component 的统一展览与预览入口。
/// 使用 Preview*Resolver 仅用于画廊演示；生产态应注入 Local Engine IPC Adapter。
@MainActor
public struct ArtifactShowcaseView: View {
  @Environment(\.accessibilityReduceMotion) private var reduceMotion

  @State private var selection: ArtifactID = .probabilityDie
  @State private var searchText = ""
  @State private var selectedFamily = "all"
  @State private var showcaseRevision = 0

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
      vaultHeader

      if filteredDescriptors.isEmpty {
        emptyVaultState
      } else {
        collectionShelf
        exhibitionDossier
        liveExhibitStage
      }
    }
    .padding(DesignTokens.LayoutInsets.panelPadding)
    .background(
      WOMPanelBackground(
        tone: .panel,
        cornerRadius: DesignTokens.Radii.lg,
        texture: .sacredSlate,
        textureOpacity: 0.025
      )
    )
    .accessibilityIdentifier("artifact-vault-exhibition")
  }

  // MARK: - Vault Header

  private var vaultHeader: some View {
    ZStack(alignment: .leading) {
      WOMArtworkView(
        assetName: WOMWorldArtworkAsset.artifactVault.wideHeaderAssetName,
        fallback: .asset(.artifact),
        fallbackTint: Color.Mystic.brassGoldMuted,
        contentMode: .fill
      )
      .opacity(0.28)
      .frame(maxWidth: .infinity)
      .frame(minHeight: 176)
      .allowsHitTesting(false)

      WOMArtworkScrim(edge: .leading, strength: 0.94)

      ViewThatFits(in: .horizontal) {
        HStack(alignment: .center, spacing: DesignTokens.Spacing.lg) {
          vaultIdentity
          Spacer(minLength: DesignTokens.Spacing.lg)
          searchAndFilterControls
        }

        VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
          vaultIdentity
          searchAndFilterControls
        }
      }
      .padding(DesignTokens.LayoutInsets.cardPadding)
    }
    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
    .overlay {
      RoundedRectangle(cornerRadius: DesignTokens.Radii.md)
        .stroke(
          Color.Mystic.brassGoldBorder.opacity(0.34),
          lineWidth: DesignTokens.Borders.hairline
        )
    }
  }

  private var vaultIdentity: some View {
    HStack(alignment: .top, spacing: DesignTokens.Spacing.md) {
      WOMIcon(.artifact, size: .prominent)
        .foregroundStyle(Color.Mystic.brassGoldPrimary)

      VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
        HStack(spacing: DesignTokens.Spacing.xs) {
          Text("神器展览 · Artifact Vault")
            .font(Font.Mystic.titleLarge)
            .foregroundStyle(Color.Mystic.textGoldAccent)
          MysticBadge(
            "\(ArtifactRegistry.all.count) 件馆藏",
            tone: .gold,
            variant: .panel,
            systemIcon: "archivebox"
          )
        }

        Text("正典神器原画展陈 × 真实玩法操作台")
          .font(Font.Mystic.monoBadge)
          .foregroundStyle(Color.Mystic.textSecondary)

        Text("展览层只负责浏览与 Preview；每件展品仍运行正式 Artifact gameplay component。")
          .mysticCaptionStyle(color: Color.Mystic.textSecondary)
          .fixedSize(horizontal: false, vertical: true)
      }
    }
  }

  private var searchAndFilterControls: some View {
    ViewThatFits(in: .horizontal) {
      HStack(spacing: DesignTokens.Spacing.sm) {
        familyPicker
        searchField
      }

      VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
        familyPicker
        searchField
      }
    }
  }

  private var familyPicker: some View {
    Picker("物品分组", selection: $selectedFamily) {
      Text("全部分组").tag("all")
      ForEach(ArtifactFamily.allCases, id: \.rawValue) { family in
        Text(family.localizedTitle).tag(family.rawValue)
      }
    }
    .pickerStyle(.menu)
    .frame(minWidth: 150, idealWidth: 170, maxWidth: 200)
    .onChange(of: selectedFamily) { _, _ in
      reconcileSelection()
    }
  }

  private var searchField: some View {
    HStack(spacing: DesignTokens.Spacing.xs) {
      WOMIcon(system: .search, size: .compact)
        .foregroundStyle(Color.Mystic.textTertiary)

      TextField("搜索神器", text: $searchText)
        .textFieldStyle(.plain)
        .frame(minWidth: 160, idealWidth: 200, maxWidth: 260)
        .onChange(of: searchText) { _, _ in
          reconcileSelection()
        }

      if !searchText.isEmpty {
        Button {
          searchText = ""
        } label: {
          Image(systemName: "xmark.circle.fill")
            .foregroundStyle(Color.Mystic.textTertiary)
        }
        .buttonStyle(.plain)
        .help("清除搜索")
      }
    }
    .padding(.horizontal, DesignTokens.Spacing.sm)
    .padding(.vertical, 6)
    .background(
      WOMPanelBackground(
        tone: .card,
        cornerRadius: DesignTokens.Radii.sm,
        texture: .sacredSlate,
        textureOpacity: 0.018
      )
    )
  }

  // MARK: - Collection Shelf

  private var collectionShelf: some View {
    VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
      HStack(spacing: DesignTokens.Spacing.sm) {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
          Text("馆藏展柜")
            .font(Font.Mystic.titleSmall)
            .foregroundStyle(Color.Mystic.textPrimary)
          Text("\(filteredDescriptors.count) 件可浏览 · 选择展品进入真实操作台")
            .mysticCaptionStyle(color: Color.Mystic.textTertiary)
        }

        Spacer(minLength: DesignTokens.Spacing.sm)

        if let ordinal = selectedOrdinal {
          Text(String(format: "%02d / %02d", ordinal, ArtifactRegistry.all.count))
            .font(Font.Mystic.monoBadge)
            .foregroundStyle(Color.Mystic.brassGoldMuted)
        }
      }

      ScrollView(.horizontal, showsIndicators: false) {
        LazyHStack(alignment: .top, spacing: DesignTokens.Spacing.sm) {
          ForEach(filteredDescriptors) { descriptor in
            collectionCard(descriptor)
          }
        }
        .padding(.vertical, DesignTokens.Spacing.xs)
      }
    }
  }

  private func collectionCard(_ descriptor: ArtifactDescriptor) -> some View {
    let isSelected = selection == descriptor.id

    return Button {
      selectArtifact(descriptor.id)
    } label: {
      VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
        ZStack(alignment: .topTrailing) {
          WOMArtworkView(
            assetName: descriptor.id.artworkAsset.thumbnailAssetName,
            fallback: .systemImage(descriptor.systemIcon),
            fallbackTint: descriptor.tone.accent,
            contentMode: .fit,
            accessibilityLabel: descriptor.displayName
          )
          .frame(width: 118, height: 88)
          .frame(maxWidth: .infinity)
          .background(Color.Mystic.abyssVoid)
          .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))

          if let index = ArtifactRegistry.all.firstIndex(where: { $0.id == descriptor.id }) {
            Text(String(format: "%02d", index + 1))
              .font(Font.Mystic.monoBadge)
              .foregroundStyle(isSelected ? descriptor.tone.readableForeground : Color.Mystic.textTertiary)
              .padding(.horizontal, DesignTokens.Spacing.xs)
              .padding(.vertical, DesignTokens.Spacing.xxs)
              .background(Color.Mystic.obsidianGlass)
              .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.xs))
              .padding(DesignTokens.Spacing.xs)
          }
        }

        Text(descriptor.displayName)
          .font(Font.Mystic.caption)
          .foregroundStyle(isSelected ? Color.Mystic.textPrimary : Color.Mystic.textSecondary)
          .lineLimit(2)
          .fixedSize(horizontal: false, vertical: true)

        Text(descriptor.canonClass.localizedTitle)
          .font(Font.Mystic.monoBadge)
          .foregroundStyle(isSelected ? descriptor.tone.accent : Color.Mystic.textTertiary)
      }
      .frame(width: 146, alignment: .leading)
      .padding(DesignTokens.Spacing.sm)
      .womCardChrome(
        tone: .card,
        texture: .sacredSlate,
        isSelected: isSelected,
        cornerRadius: DesignTokens.Radii.md
      )
    }
    .buttonStyle(.plain)
    .accessibilityLabel("展品：\(descriptor.displayName)")
    .accessibilityAddTraits(isSelected ? .isSelected : [])
  }

  // MARK: - Selected Exhibit

  private var exhibitionDossier: some View {
    let descriptor = ArtifactRegistry.descriptor(for: selection)

    return VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
      ViewThatFits(in: .horizontal) {
        HStack(alignment: .top, spacing: DesignTokens.Spacing.lg) {
          exhibitIdentity(descriptor)
          Spacer(minLength: DesignTokens.Spacing.lg)
          exhibitControls
        }

        VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
          exhibitIdentity(descriptor)
          exhibitControls
        }
      }

      MysticDivider(tone: descriptor.tone, label: "馆藏档案")

      Text(descriptor.shortGameplay)
        .font(Font.Mystic.bodyLarge)
        .foregroundStyle(Color.Mystic.textSecondary)
        .fixedSize(horizontal: false, vertical: true)
    }
    .padding(DesignTokens.LayoutInsets.cardPadding)
    .background(
      WOMPanelBackground(
        tone: .card,
        cornerRadius: DesignTokens.Radii.md,
        texture: .sacredSlate,
        textureOpacity: 0.025
      )
    )
    .overlay {
      RoundedRectangle(cornerRadius: DesignTokens.Radii.md)
        .stroke(descriptor.tone.accent.opacity(0.22), lineWidth: DesignTokens.Borders.hairline)
    }
  }

  private func exhibitIdentity(_ descriptor: ArtifactDescriptor) -> some View {
    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
      HStack(spacing: DesignTokens.Spacing.xs) {
        MysticBadge(
          "CURRENT EXHIBIT",
          tone: descriptor.tone,
          variant: .panel,
          systemIcon: "sparkles"
        )
        MysticBadge(descriptor.family.localizedTitle, tone: descriptor.tone, variant: .panel)
        MysticBadge(descriptor.canonClass.localizedTitle, tone: .neutral, variant: .panel)
      }

      Text(descriptor.displayName)
        .font(Font.Mystic.displayLarge)
        .foregroundStyle(Color.Mystic.textGoldAccent)
        .fixedSize(horizontal: false, vertical: true)

      Text(descriptor.subtitle)
        .font(Font.Mystic.monoBadge)
        .foregroundStyle(Color.Mystic.textSecondary)
    }
  }

  private var exhibitControls: some View {
    HStack(spacing: DesignTokens.Spacing.sm) {
      Button {
        selectAdjacent(offset: -1)
      } label: {
        Label("上一件", systemImage: "chevron.left")
      }
      .buttonStyle(WOMButtonStyle(.secondary))
      .disabled(filteredDescriptors.count < 2)

      Button {
        selectAdjacent(offset: 1)
      } label: {
        Label("下一件", systemImage: "chevron.right")
      }
      .buttonStyle(WOMButtonStyle(.secondary))
      .disabled(filteredDescriptors.count < 2)

      Button("重置演示") {
        resetShowcase()
      }
      .buttonStyle(WOMButtonStyle(.secondary))
    }
  }

  private var liveExhibitStage: some View {
    let descriptor = ArtifactRegistry.descriptor(for: selection)

    return VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
      HStack(spacing: DesignTokens.Spacing.sm) {
        MysticStatusDot(tone: .teal)
        Text("LIVE ARTIFACT WORKBENCH")
          .font(Font.Mystic.monoBadge)
          .foregroundStyle(Color.Mystic.textSecondary)
        Spacer()
        Text("Production component · Preview resolver")
          .font(Font.Mystic.caption)
          .foregroundStyle(Color.Mystic.textTertiary)
      }

      selectedComponent
        .id(showcaseRevision)
    }
    .padding(.top, DesignTokens.Spacing.xs)
    .accessibilityElement(children: .contain)
    .accessibilityLabel("\(descriptor.displayName) 实时神器操作台")
  }

  private var emptyVaultState: some View {
    WOMEmptyState(
      source: .asset(.artifact),
      title: "没有匹配的神器",
      message: "调整分组或搜索条件后继续浏览 15 件真实玩法组件。",
      tone: .info,
      actionTitle: "清除筛选"
    ) {
      selectedFamily = "all"
      searchText = ""
    }
  }

  // MARK: - Browsing

  private var filteredDescriptors: [ArtifactDescriptor] {
    let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
    return ArtifactRegistry.all.filter { descriptor in
      let familyMatches = selectedFamily == "all" || descriptor.family.rawValue == selectedFamily
      let queryMatches = query.isEmpty
        || descriptor.displayName.localizedCaseInsensitiveContains(query)
        || descriptor.subtitle.localizedCaseInsensitiveContains(query)
        || descriptor.shortGameplay.localizedCaseInsensitiveContains(query)
      return familyMatches && queryMatches
    }
  }

  private var selectedOrdinal: Int? {
    ArtifactRegistry.all.firstIndex(where: { $0.id == selection }).map { $0 + 1 }
  }

  private func selectArtifact(_ id: ArtifactID) {
    guard id != selection else { return }
    withAnimation(reduceMotion ? nil : DesignTokens.Interaction.selectionSpring) {
      selection = id
    }
    genericModel.resetPresentation(keepHistory: false)
    showcaseRevision += 1
  }

  private func selectAdjacent(offset: Int) {
    guard filteredDescriptors.count > 1 else { return }
    let current = filteredDescriptors.firstIndex(where: { $0.id == selection }) ?? 0
    let count = filteredDescriptors.count
    let next = (current + offset % count + count) % count
    selectArtifact(filteredDescriptors[next].id)
  }

  private func reconcileSelection() {
    guard let first = filteredDescriptors.first else { return }
    guard filteredDescriptors.contains(where: { $0.id == selection }) else {
      selection = first.id
      resetShowcase()
      return
    }
  }

  private func resetShowcase() {
    genericModel = ArtifactActionModel(
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
    dieModel = ProbabilityDieModel(
      artifactState: .init(awakening: 0.22, resentment: 0.08, sealed: false),
      resolver: PreviewProbabilityDieResolver()
    )
    quillModel = AlzuhodQuillModel(
      artifactState: .init(awakening: 0.18, exposure: 0.12, narrativeDebt: 0.8, sealed: false),
      orchestrator: PreviewAlzuhodQuillOrchestrator()
    )
    showcaseRevision += 1
  }

  // MARK: - Production Components

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
        model: genericModel,
        context: context,
        participantIDs: ["character.demo", "character.companion"]
      )
    case .azikCopperWhistle:
      AzikCopperWhistleArtifactView(
        model: genericModel,
        context: context,
        recipients: ["阿兹克·艾格斯", "character.companion"]
      )
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
        model: genericModel,
        context: context,
        targetID: "entity.demo.target",
        weaknesses: weaknesses,
        roundsRemaining: 5
      )
    case .unshadowedCrucifix:
      UnshadowedCrucifixArtifactView(
        model: genericModel,
        context: context,
        targetIDs: ["material.polluted.001", "material.characteristic.002"]
      )
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
        id: "soul.demo.1",
        displayName: "示例灵魂 A",
        pathway: "Pathway Unknown",
        abilityNames: ["能力 A", "能力 B"]
      ),
      .init(
        id: "soul.demo.2",
        displayName: "示例灵魂 B",
        pathway: "Pathway Unknown",
        abilityNames: ["能力 C"]
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
