import SwiftUI

// MARK: - 许愿神灯

@MainActor
public struct MagicWishingLampArtifactView: View {
  @Bindable private var model: ArtifactActionModel
  private let context: ArtifactContext

  @State private var wish = ""
  @State private var rubProgress = 0.0
  @State private var dragStart = 0.0

  public init(model: ArtifactActionModel, context: ArtifactContext) {
    self.model = model
    self.context = context
  }

  public var body: some View {
    ArtifactComponentShell(artifactID: .magicWishingLamp) {
      VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
        ArtifactSection("擦拭神灯", caption: "来回拖动完成唤醒仪式", tone: .amber) {
          ZStack {
            ArtifactAmbientField(tone: .amber, intensity: rubProgress, particleCount: 18)
            HStack(spacing: DesignTokens.Spacing.lg) {
              Image(systemName: rubProgress >= 0.98 ? "lamp.desk.fill" : "lamp.desk")
                .font(.system(size: 38, weight: .light))
                .foregroundStyle(
                  rubProgress >= 0.98 ? Color.Mystic.brassGoldPrimary : Color.Mystic.textTertiary)
              VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                Text(rubProgress >= 0.98 ? "灯神已经注意到你" : "擦拭以唤醒")
                  .font(Font.Mystic.titleSmall)
                  .foregroundStyle(Color.Mystic.textPrimary)
                MysticMetricBar(value: rubProgress, tone: .amber)
                Text("\(Int(rubProgress * 100))%")
                  .font(Font.Mystic.monoBadge)
                  .foregroundStyle(Color.Mystic.statusWarning)
              }
            }
          }
          .frame(height: 100)
          .contentShape(Rectangle())
          .gesture(
            DragGesture(minimumDistance: 4)
              .onChanged { value in
                let distance = abs(value.translation.width) + abs(value.translation.height) * 0.25
                rubProgress = min(1, dragStart + distance / 520)
              }
              .onEnded { _ in dragStart = rubProgress }
          )
        }

        ArtifactSection("说出你的愿望", caption: "解释树、漏洞与代价不会全部提前展示", tone: .amber) {
          TextEditor(text: $wish)
            .font(Font.Mystic.narrativeSubtitle)
            .scrollContentBackground(.hidden)
            .frame(minHeight: 112)
            .padding(DesignTokens.Spacing.sm)
            .background(Color.Mystic.abyssVoid.opacity(0.72))
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
            .disabled(rubProgress < 0.98 || model.isBusy)

          HStack {
            ArtifactMeterCard(
              "暴露", value: model.meters["wishExposure"] ?? 0.05, systemIcon: "eye", tone: .amber
            )
            .frame(maxWidth: 230)
            Spacer()
            ArtifactHoldToCommitButton(
              "许下愿望", systemImage: "sparkles", tone: .amber, holdDuration: 1.0,
              disabled: rubProgress < 0.98
                || wish.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || model.isBusy
            ) {
              let body = wish.trimmingCharacters(in: .whitespacesAndNewlines)
              Task {
                await model.perform(
                  .init(
                    artifactID: .magicWishingLamp, action: .wish, context: context, input: body,
                    numericParameters: ["ritualCharge": rubProgress]))
                if model.lastResolution?.disposition == .committed {
                  wish = ""
                  rubProgress = 0
                  dragStart = 0
                }
              }
            }
          }
        }

        ArtifactResolutionView(model: model)

        if model.lastResolution != nil {
          ArtifactSection("解释仍被封住", tone: .crimson) {
            HStack(spacing: DesignTokens.Spacing.sm) {
              ForEach(
                [
                  ("字面解释", "text.quote"), ("漏洞", "lock.trianglebadge.exclamationmark"),
                  ("代价", "seal"),
                ], id: \.0
              ) { item in
                VStack(spacing: DesignTokens.Spacing.xs) {
                  Image(systemName: item.1).foregroundStyle(Color.Mystic.statusDanger)
                  Text(item.0).font(Font.Mystic.caption).foregroundStyle(Color.Mystic.textSecondary)
                  Text("SEALED").font(Font.Mystic.monoBadge).foregroundStyle(
                    Color.Mystic.textTertiary)
                }
                .frame(maxWidth: .infinity)
                .padding(DesignTokens.Spacing.md)
                .background(Color.Mystic.obsidianElevated)
                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
              }
            }
          }
        }
      }
    }
  }
}
