import SwiftUI

// MARK: - 格罗塞尔游记

@MainActor
public struct GroselleTravelsArtifactView: View {
  @Bindable private var model: ArtifactActionModel
  private let context: ArtifactContext
  private let participantIDs: [String]

  @State private var confirmed = false
  @State private var insideBookWorld: Bool

  public init(
    model: ArtifactActionModel,
    context: ArtifactContext,
    participantIDs: [String] = [],
    insideBookWorld: Bool = false
  ) {
    self.model = model
    self.context = context
    self.participantIDs = participantIDs
    self._insideBookWorld = State(initialValue: insideBookWorld)
  }

  public var body: some View {
    ArtifactComponentShell(artifactID: .groselleTravels) {
      VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
        header

        ArtifactSection(
          insideBookWorld ? "返回边界" : "书页入口",
          caption: "Worldline · \(context.worldlineID)",
          tone: .azure
        ) {
          ZStack {
            ArtifactPortalSurface(active: model.isBusy || insideBookWorld, tone: .azure)
              .frame(width: 210, height: 210)
            VStack(spacing: DesignTokens.Spacing.xs) {
              Image(systemName: insideBookWorld ? "arrow.uturn.backward.circle" : "book.pages")
                .font(.system(size: 30, weight: .ultraLight))
                .foregroundStyle(Color.Mystic.spiritualBlue)
                .accessibilityHidden(true)
              Text(insideBookWorld ? "返回主世界" : "页面正在形成空间")
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.textPrimary)
            }
          }
          .frame(maxWidth: .infinity)
        }

        ArtifactSection(
          "参与者快照",
          caption: "进入前固定 Story Session 参与者；状态与记忆可回流",
          tone: .neutral
        ) {
          if participantIDs.isEmpty {
            MysticBadge(
              context.actorID ?? "当前角色",
              tone: .neutral,
              systemIcon: "person.crop.circle"
            )
          } else {
            LazyVGrid(
              columns: [GridItem(.adaptive(minimum: 150))],
              alignment: .leading,
              spacing: DesignTokens.Spacing.xs
            ) {
              ForEach(participantIDs, id: \.self) { id in
                MysticBadge(id, tone: .neutral, systemIcon: "person.crop.circle")
              }
            }
          }

          MysticDivider(tone: .azure)
          Label("角色状态会带入书中", systemImage: "arrow.down.doc")
          Label("Memory / Knowledge 可以带回", systemImage: "brain.head.profile")
          Label("不是可随意读档的副本", systemImage: "lock.shield")
        }
        .font(Font.Mystic.caption)
        .foregroundStyle(Color.Mystic.textSecondary)

        ArtifactResolutionView(model: model)

        ArtifactSection(
          insideBookWorld ? "离开书中世界" : "进入确认",
          caption: "这是世界状态转换，不是普通页面导航",
          tone: insideBookWorld ? .amber : .azure
        ) {
          if !insideBookWorld {
            Toggle("我确认进入书中世界", isOn: $confirmed)
          }

          HStack {
            Spacer()
            ArtifactHoldToCommitButton(
              insideBookWorld ? "返回主世界" : "穿过书页",
              systemImage: insideBookWorld ? "arrow.uturn.backward" : "arrow.forward.circle",
              tone: insideBookWorld ? .amber : .azure,
              holdDuration: insideBookWorld ? 0.7 : 0.95,
              disabled: (!insideBookWorld && !confirmed) || model.isBusy
            ) {
              let action: ArtifactActionKind = insideBookWorld ? .exitBookWorld : .enterBookWorld
              Task {
                await model.perform(
                  .init(
                    artifactID: .groselleTravels,
                    action: action,
                    context: context,
                    selectionIDs: participantIDs
                  )
                )
                if model.lastResolution?.disposition == .committed {
                  insideBookWorld.toggle()
                  confirmed = false
                }
              }
            }
          }
        }
      }
    }
  }

  private var header: some View {
    ViewThatFits(in: .horizontal) {
      HStack(alignment: .top, spacing: DesignTokens.Spacing.md) {
        headerText
        Spacer(minLength: DesignTokens.Spacing.md)
        worldStatePill
      }

      VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
        headerText
        worldStatePill
      }
    }
  }

  private var headerText: some View {
    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
      Text("书中世界")
        .font(Font.Mystic.titleMedium)
        .foregroundStyle(Color.Mystic.textGoldAccent)
      Text("StorySpace 不是与主世界无关的副本菜单。")
        .mysticCaptionStyle()
        .fixedSize(horizontal: false, vertical: true)
    }
  }

  private var worldStatePill: some View {
    ArtifactStatusPill(
      insideBookWorld ? "书中" : "主世界",
      systemImage: insideBookWorld ? "book.fill" : "globe",
      tone: insideBookWorld ? .amber : .azure
    )
  }
}
