import SwiftUI

// MARK: - 旧日之盒

@MainActor
public struct BoxOfGreatOldOnesArtifactView: View {
  @Bindable private var model: ArtifactActionModel
  private let context: ArtifactContext

  @State private var selectedLayer = 1
  @State private var mode = "swap"

  public init(model: ArtifactActionModel, context: ArtifactContext) {
    self.model = model
    self.context = context
  }

  public var body: some View {
    ArtifactComponentShell(artifactID: .boxOfGreatOldOnes) {
      VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
        HStack {
          VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
            Text("三层空间容器").font(Font.Mystic.titleMedium).foregroundStyle(
              Color.Mystic.textGoldAccent)
            Text("三层不是难度等级，而是三种性质不同的空间机制。").mysticCaptionStyle()
          }
          Spacer()
          ArtifactStatusPill(
            "第 \(selectedLayer) 层",
            systemImage: selectedLayer == 3 ? "lock.trianglebadge.exclamationmark" : "shippingbox",
            tone: selectedLayer == 3 ? .crimson : .amber)
        }

        ArtifactSection("旧日之盒", caption: "选择一层查看当前允许的操作", tone: .amber) {
          VStack(spacing: DesignTokens.Spacing.sm) {
            ForEach([1, 2, 3], id: \.self) { layer in
              Button {
                selectedLayer = layer
                mode = layer == 1 ? "swap" : (layer == 2 ? "travel" : "observe")
              } label: {
                HStack {
                  VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
                    Text("LAYER \(layer)").font(Font.Mystic.monoBadge).foregroundStyle(
                      Color.Mystic.textTertiary)
                    Text(layerTitle(layer)).font(Font.Mystic.titleSmall).foregroundStyle(
                      Color.Mystic.textPrimary)
                  }
                  Spacer()
                  Image(systemName: layer == 3 ? "lock.fill" : "chevron.right")
                    .foregroundStyle(
                      layer == 3 ? Color.Mystic.statusDanger : Color.Mystic.statusWarning)
                }
                .padding(DesignTokens.Spacing.md)
                .background(Color.Mystic.obsidianElevated)
                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
                .mysticCardSelection(isSelected: selectedLayer == layer)
              }
              .buttonStyle(.plain)
            }
          }
        }

        layerInspector
        ArtifactResolutionView(model: model)
      }
    }
  }

  @ViewBuilder
  private var layerInspector: some View {
    if selectedLayer == 1 {
      ArtifactSection("第一层 · 空间交换", caption: "目标仍需由 Engine 校验", tone: .amber) {
        Picker("模式", selection: $mode) {
          Text("交换").tag("swap")
          Text("微缩").tag("miniaturize")
        }.pickerStyle(.segmented)
        actionButton(title: "开启第一层", icon: "shippingbox.and.arrow.backward", tone: .amber)
      }
    } else if selectedLayer == 2 {
      ArtifactSection("第二层 · 空间旅行", caption: "目的地与异常风险由世界状态结算", tone: .azure) {
        Picker("模式", selection: $mode) {
          Text("定向旅行").tag("travel")
          Text("未知空间").tag("unknown")
        }.pickerStyle(.segmented)
        actionButton(title: "开启第二层", icon: "arrow.up.right.square", tone: .azure)
      }
    } else {
      ArtifactSection("第三层 · 禁忌", caption: "不提供客户端强制开启后门", tone: .crimson) {
        Label("High-Level Story / Lore Gate", systemImage: "lock.shield.fill")
          .foregroundStyle(Color.Mystic.statusDanger)
        Text("可以请求观察，但默认结果是拒绝；真正开放必须来自世界条件。")
          .mysticCaptionStyle()
        actionButton(
          title: "尝试观察第三层", icon: "eye.trianglebadge.exclamationmark", tone: .crimson, hold: 1.4)
      }
    }
  }

  private func actionButton(title: String, icon: String, tone: MysticTone, hold: Double = 0.8)
    -> some View
  {
    HStack {
      Spacer()
      ArtifactHoldToCommitButton(
        title, systemImage: icon, tone: tone, holdDuration: hold, disabled: model.isBusy
      ) {
        model.performDetached(
          .init(
            artifactID: .boxOfGreatOldOnes, action: .openLayer, context: context,
            stringParameters: ["layer": String(selectedLayer), "mode": mode]))
      }
    }
  }

  private func layerTitle(_ layer: Int) -> String {
    switch layer {
    case 1: return "交换 / 微缩"
    case 2: return "空间旅行"
    default: return "禁忌"
    }
  }
}
