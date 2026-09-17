import SwiftUI

// MARK: - 莱曼诺的旅行笔记

public struct RecordedAbilityPage: Identifiable, Hashable, Sendable {
  public var id: String
  public var page: Int
  public var abilityName: String?
  public var sourceCharacterID: String?
  public var risk: ArtifactRiskBand

  public init(
    id: String, page: Int, abilityName: String? = nil, sourceCharacterID: String? = nil,
    risk: ArtifactRiskBand = .guarded
  ) {
    self.id = id
    self.page = page
    self.abilityName = abilityName
    self.sourceCharacterID = sourceCharacterID
    self.risk = risk
  }
}

@MainActor
public struct LeymanoTravelsArtifactView: View {
  @Bindable private var model: ArtifactActionModel
  private let context: ArtifactContext

  @State private var pages: [RecordedAbilityPage]
  @State private var selectedIndex = 0
  @State private var observedAbility = ""

  public init(model: ArtifactActionModel, context: ArtifactContext, pages: [RecordedAbilityPage]) {
    self.model = model
    self.context = context
    self._pages = State(initialValue: pages)
  }

  public var body: some View {
    ArtifactComponentShell(artifactID: .leymanoTravels) {
      VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
        HStack {
          VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
            Text("能力记录器").font(Font.Mystic.titleMedium).foregroundStyle(Color.Mystic.textGoldAccent)
            Text("Observation → Record → Page → Invoke → Empty").font(Font.Mystic.monoBadge)
              .foregroundStyle(Color.Mystic.textTertiary)
          }
          Spacer()
          ArtifactStatusPill(
            "\(occupiedCount)/\(pages.count) 已记录", systemImage: "book.pages", tone: .teal)
        }

        ArtifactSection("当前页面", caption: "记录成功率与承载上限由 Engine 决定", tone: .teal) {
          if pages.isEmpty {
            MysticEmptyState(
              systemIcon: "book.closed", title: "没有页面", message: "当前没有可用记录页。", tone: .neutral)
          } else {
            HStack(spacing: DesignTokens.Spacing.md) {
              Button {
                selectedIndex = max(0, selectedIndex - 1)
              } label: {
                Image(systemName: "chevron.left")
              }
              .mysticPressable().disabled(selectedIndex == 0)
              pageCard(pages[selectedIndex])
              Button {
                selectedIndex = min(pages.count - 1, selectedIndex + 1)
              } label: {
                Image(systemName: "chevron.right")
              }
              .mysticPressable().disabled(selectedIndex >= pages.count - 1)
            }
          }
        }

        ArtifactSection("观察到的能力", tone: .azure) {
          TextField("绑定当前 Observation 中可记录的能力", text: $observedAbility)
          HStack {
            if !pages.isEmpty {
              MysticBadge(
                pages[selectedIndex].abilityName == nil ? "目标页为空" : "目标页已占用",
                tone: pages[selectedIndex].abilityName == nil ? .teal : .amber,
                systemIcon: pages[selectedIndex].abilityName == nil
                  ? "checkmark.circle" : "xmark.circle")
            }
            Spacer()
            Button {
              recordIntoSelectedPage()
            } label: {
              Label("尝试记录", systemImage: "pencil.and.outline")
            }
            .mysticPressable()
            .disabled(
              pages.isEmpty || pages[selectedIndex].abilityName != nil
                || observedAbility.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                || model.isBusy)
          }
        }

        ArtifactResolutionView(model: model)
      }
    }
  }

  private func pageCard(_ page: RecordedAbilityPage) -> some View {
    VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
      HStack {
        Text("PAGE \(page.page)").font(Font.Mystic.monoBadge).foregroundStyle(
          Color.Mystic.textTertiary)
        Spacer()
        MysticBadge(
          page.risk.localizedTitle, tone: page.risk == .extreme ? .crimson : .neutral,
          systemIcon: "exclamationmark.shield")
      }
      Spacer()
      if let ability = page.abilityName {
        Text(ability).font(Font.Mystic.titleLarge).foregroundStyle(Color.Mystic.textGoldAccent)
        if let source = page.sourceCharacterID {
          Text("Source · \(source)").font(Font.Mystic.monoBadge).foregroundStyle(
            Color.Mystic.textTertiary)
        }
        Spacer()
        ArtifactHoldToCommitButton(
          "释放并消耗此页", systemImage: "sparkles", tone: .teal, disabled: model.isBusy
        ) {
          Task {
            await model.perform(
              .init(
                artifactID: .leymanoTravels, action: .invokeRecordedAbility, context: context,
                input: ability, selectionIDs: [page.id]))
            if model.lastResolution?.state == "page_consumed",
              let index = pages.firstIndex(where: { $0.id == page.id })
            {
              pages[index].abilityName = nil
              pages[index].sourceCharacterID = nil
            }
          }
        }
      } else {
        MysticEmptyState(systemIcon: "doc", title: "空白页", message: "可用于记录一次合规的非凡能力。", tone: .teal)
        Spacer()
      }
    }
    .padding(DesignTokens.LayoutInsets.cardPadding)
    .frame(maxWidth: .infinity, minHeight: 230)
    .background(Color.Mystic.obsidianElevated)
    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
    .overlay(
      RoundedRectangle(cornerRadius: DesignTokens.Radii.md).stroke(
        Color.Mystic.statusOnline.opacity(0.18), lineWidth: DesignTokens.Borders.hairline))
  }

  private func recordIntoSelectedPage() {
    guard !pages.isEmpty else { return }
    let text = observedAbility.trimmingCharacters(in: .whitespacesAndNewlines)
    let page = pages[selectedIndex]
    Task {
      await model.perform(
        .init(
          artifactID: .leymanoTravels, action: .recordAbility, context: context, input: text,
          selectionIDs: [page.id]))
      if model.lastResolution?.state == "recorded" {
        pages[selectedIndex].abilityName = text
        observedAbility = ""
      }
    }
  }

  private var occupiedCount: Int { pages.filter { $0.abilityName != nil }.count }
}
