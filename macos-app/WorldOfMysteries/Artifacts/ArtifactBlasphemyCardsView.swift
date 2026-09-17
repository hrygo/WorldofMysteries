import SwiftUI

// MARK: - 亵渎之牌

public struct BlasphemyPathwayCardState: Identifiable, Hashable, Sendable {
  public var id: String
  public var displayName: String
  public var revealFraction: Double

  public init(id: String, displayName: String, revealFraction: Double = 0) {
    self.id = id
    self.displayName = displayName
    self.revealFraction = min(max(revealFraction, 0), 1)
  }
}

@MainActor
public struct CardsOfBlasphemyArtifactView: View {
  @Bindable private var model: ArtifactActionModel
  private let context: ArtifactContext

  @State private var cards: [BlasphemyPathwayCardState]
  @State private var selectedID: String?

  public init(
    model: ArtifactActionModel, context: ArtifactContext, cards: [BlasphemyPathwayCardState]
  ) {
    self.model = model
    self.context = context
    self._cards = State(initialValue: cards)
    self._selectedID = State(initialValue: cards.first?.id)
  }

  public var body: some View {
    ArtifactComponentShell(artifactID: .cardsOfBlasphemy) {
      VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
        HStack {
          Text("途径知识圣典").font(Font.Mystic.titleMedium).foregroundStyle(Color.Mystic.textGoldAccent)
          Spacer()
          ArtifactStatusPill(
            "\(cards.count) 张已持有", systemImage: "rectangle.stack.fill", tone: .gold)
        }

        ArtifactSection("亵渎之牌", caption: "持有不等于一次性知道全部内容", tone: .gold) {
          LazyVGrid(
            columns: [GridItem(.adaptive(minimum: 120), spacing: DesignTokens.Spacing.sm)],
            spacing: DesignTokens.Spacing.sm
          ) {
            ForEach(cards) { card in
              Button {
                selectedID = card.id
              } label: {
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                  ZStack {
                    RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                      .fill(Color.Mystic.obsidianElevated)
                    ArtifactPulseRing(tone: .gold, active: selectedID == card.id).padding(
                      DesignTokens.Spacing.lg)
                    Image(systemName: "eye.trianglebadge.exclamationmark")
                      .font(.system(size: 26, weight: .ultraLight))
                      .foregroundStyle(Color.Mystic.brassGoldPrimary)
                  }
                  .frame(height: 86)
                  Text(card.displayName).font(Font.Mystic.caption).foregroundStyle(
                    Color.Mystic.textPrimary
                  ).lineLimit(1)
                  MysticMetricBar(value: card.revealFraction, tone: .gold)
                  Text("\(Int(card.revealFraction * 100))% 已知").font(Font.Mystic.monoBadge)
                    .foregroundStyle(Color.Mystic.textTertiary)
                }
                .padding(DesignTokens.Spacing.sm)
                .mysticCardSelection(isSelected: selectedID == card.id)
              }
              .buttonStyle(.plain)
            }
          }
        }

        if let card = selectedCard {
          ArtifactSection(
            card.displayName, caption: "Knowledge / Spoiler Gate 决定可展开层级", tone: .gold
          ) {
            ForEach(
              [("序列框架", 0.12), ("能力与象征", 0.28), ("魔药知识", 0.46), ("晋升与仪式", 0.66), ("高位知识", 0.86)],
              id: \.0
            ) { row in
              HStack {
                Image(
                  systemName: card.revealFraction >= row.1 ? "checkmark.seal.fill" : "lock.fill"
                )
                .foregroundStyle(
                  card.revealFraction >= row.1
                    ? Color.Mystic.brassGoldPrimary : Color.Mystic.textTertiary)
                Text(row.0).font(Font.Mystic.bodyMedium).foregroundStyle(Color.Mystic.textPrimary)
                Spacer()
                Text(card.revealFraction >= row.1 ? "已揭示" : "未知").font(Font.Mystic.caption)
                  .foregroundStyle(Color.Mystic.textTertiary)
              }
            }
            HStack {
              Spacer()
              ArtifactHoldToCommitButton(
                "注入灵性并展开", systemImage: "sparkles", tone: .gold,
                disabled: card.revealFraction >= 1 || model.isBusy
              ) {
                Task {
                  await model.perform(
                    .init(
                      artifactID: .cardsOfBlasphemy, action: .unlockLore, context: context,
                      selectionIDs: [card.id],
                      numericParameters: ["knownFraction": card.revealFraction]))
                  if model.lastResolution?.state == "lore_unlocked",
                    let index = cards.firstIndex(where: { $0.id == card.id })
                  {
                    cards[index].revealFraction = min(
                      1,
                      cards[index].revealFraction
                        + (model.lastResolution?.meters["revealBoost"] ?? 0))
                  }
                }
              }
            }
          }
        }

        ArtifactResolutionView(model: model)
      }
    }
  }

  private var selectedCard: BlasphemyPathwayCardState? {
    cards.first(where: { $0.id == selectedID })
  }
}
