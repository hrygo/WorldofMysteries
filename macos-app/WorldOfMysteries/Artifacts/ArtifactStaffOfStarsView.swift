import SwiftUI

// MARK: - 星之杖

@MainActor
public struct StaffOfStarsArtifactView: View {
  @Bindable private var model: ArtifactActionModel
  private let context: ArtifactContext
  private let knowledgeCompleteness: Double

  @State private var target = ""
  @State private var targetKind = "location"

  public init(
    model: ArtifactActionModel, context: ArtifactContext, knowledgeCompleteness: Double = 0.65
  ) {
    self.model = model
    self.context = context
    self.knowledgeCompleteness = min(max(knowledgeCompleteness, 0), 1)
  }

  public var body: some View {
    ArtifactComponentShell(artifactID: .staffOfStars) {
      VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
        HStack {
          VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
            Text("认知投射")
              .font(Font.Mystic.titleMedium)
              .foregroundStyle(Color.Mystic.textGoldAccent)
            Text("Knowledge 不足意味着投射误差，而不是 Fast Travel 自动补全。")
              .mysticCaptionStyle()
          }
          Spacer()
          ArtifactStatusPill(confidenceLabel, systemImage: "scope", tone: confidenceTone)
        }

        ArtifactSection("星图重建", caption: "认知完整度由 Knowledge / Memory Engine 提供", tone: .azure) {
          ZStack {
            ArtifactAmbientField(tone: .azure, intensity: knowledgeCompleteness, particleCount: 28)
            ArtifactPulseRing(tone: .azure, active: model.isBusy)
              .frame(width: 180, height: 180)
            VStack(spacing: DesignTokens.Spacing.xs) {
              Image(systemName: targetKindIcon)
                .font(.system(size: 34, weight: .ultraLight))
                .foregroundStyle(Color.Mystic.spiritualBlue)
              Text(target.isEmpty ? "尚未指定目标" : target)
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.textPrimary)
                .lineLimit(2)
              Text("\(Int(knowledgeCompleteness * 100))% reconstruction")
                .font(Font.Mystic.monoBadge)
                .foregroundStyle(Color.Mystic.textTertiary)
            }
          }
          .frame(maxWidth: .infinity, minHeight: 230)
          .background(Color.Mystic.abyssVoid)
          .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))

          ArtifactMeterCard(
            "认知完整度", value: knowledgeCompleteness,
            detail: knowledgeCompleteness >= 0.8 ? "重建稳定。" : "存在缺口：Engine 应提高误差或拒绝。",
            systemIcon: "brain.head.profile", tone: confidenceTone)
        }

        ArtifactSection("投射目标", tone: .azure) {
          Picker("目标类型", selection: $targetKind) {
            Text("地点").tag("location")
            Text("人物").tag("person")
            Text("能力").tag("ability")
          }
          .pickerStyle(.segmented)

          TextField("输入角色已经合法认知的目标", text: $target)

          HStack {
            MysticBadge(
              knowledgeCompleteness < 0.5 ? "高误差" : "可尝试投射",
              tone: knowledgeCompleteness < 0.5 ? .crimson : .teal,
              systemIcon: knowledgeCompleteness < 0.5
                ? "exclamationmark.triangle" : "checkmark.circle")
            Spacer()
            ArtifactHoldToCommitButton(
              "执行投射", systemImage: "sparkles", tone: .azure,
              disabled: target.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                || model.isBusy
            ) {
              model.performDetached(
                .init(
                  artifactID: .staffOfStars, action: .projectLocation, context: context,
                  input: target,
                  numericParameters: ["knowledgeCompleteness": knowledgeCompleteness],
                  stringParameters: ["targetKind": targetKind]))
            }
          }
        }

        ArtifactResolutionView(model: model)
      }
    }
  }

  private var confidenceTone: MysticTone {
    knowledgeCompleteness >= 0.8 ? .teal : (knowledgeCompleteness >= 0.5 ? .amber : .crimson)
  }

  private var confidenceLabel: String {
    knowledgeCompleteness >= 0.8 ? "重建稳定" : (knowledgeCompleteness >= 0.5 ? "存在缺口" : "高度不确定")
  }

  private var targetKindIcon: String {
    switch targetKind {
    case "person": return "person.crop.circle"
    case "ability": return "sparkles.rectangle.stack"
    default: return "mappin.and.ellipse"
    }
  }
}
