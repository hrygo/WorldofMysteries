import SwiftUI

// MARK: - 无暗十字架

@MainActor
public struct UnshadowedCrucifixArtifactView: View {
  @Bindable private var model: ArtifactActionModel
  private let context: ArtifactContext
  private let targetIDs: [String]

  @State private var selected: Set<String>
  @State private var mode = "purify"
  @State private var intensity = 0.55

  public init(model: ArtifactActionModel, context: ArtifactContext, targetIDs: [String]) {
    self.model = model
    self.context = context
    self.targetIDs = targetIDs
    self._selected = State(initialValue: Set(targetIDs))
  }

  public var body: some View {
    ArtifactComponentShell(artifactID: .unshadowedCrucifix) {
      VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
        header

        ArtifactSection("处理对象", caption: "只显示 Engine 已判定可处理的目标", tone: .gold) {
          if targetIDs.isEmpty {
            MysticEmptyState(
              systemIcon: "tray",
              title: "没有目标",
              message: "当前没有可处理的材料或污染。",
              tone: .neutral
            )
          } else {
            LazyVGrid(
              columns: [GridItem(.adaptive(minimum: 155))],
              spacing: DesignTokens.Spacing.sm
            ) {
              ForEach(targetIDs, id: \.self) { id in
                Button {
                  if selected.contains(id) {
                    selected.remove(id)
                  } else {
                    selected.insert(id)
                  }
                } label: {
                  HStack(alignment: .top, spacing: DesignTokens.Spacing.sm) {
                    Image(systemName: selected.contains(id) ? "checkmark.circle.fill" : "circle")
                      .foregroundStyle(
                        selected.contains(id)
                          ? Color.Mystic.brassGoldPrimary : Color.Mystic.textTertiary
                      )
                      .accessibilityHidden(true)

                    Text(id)
                      .font(Font.Mystic.monoBadge)
                      .foregroundStyle(Color.Mystic.textSecondary)
                      .fixedSize(horizontal: false, vertical: true)

                    Spacer(minLength: DesignTokens.Spacing.xs)
                  }
                  .frame(maxWidth: .infinity, alignment: .leading)
                  .padding(DesignTokens.Spacing.sm)
                  .background(Color.Mystic.obsidianElevated)
                  .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(id)
                .accessibilityValue(selected.contains(id) ? "已选中" : "未选中")
              }
            }
          }

          Picker("处理方式", selection: $mode) {
            Text("净化").tag("purify")
            Text("分离").tag("separate")
            Text("提取").tag("extract")
          }
          .pickerStyle(.segmented)

          ViewThatFits(in: .horizontal) {
            HStack(spacing: DesignTokens.Spacing.md) {
              intensityLabel
              Slider(value: $intensity, in: 0.1...1)
            }

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
              intensityLabel
              Slider(value: $intensity, in: 0.1...1)
            }
          }

          ViewThatFits(in: .horizontal) {
            HStack(spacing: DesignTokens.Spacing.md) {
              selectionBadge
              Spacer(minLength: DesignTokens.Spacing.md)
              commitButton
            }

            VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
              selectionBadge
              commitButton
            }
          }
        }

        ArtifactSection("处理流程", caption: "实际产物仍由材料规则与高位污染规则决定", tone: .gold) {
          LazyVGrid(
            columns: [GridItem(.adaptive(minimum: 96), spacing: DesignTokens.Spacing.sm)],
            alignment: .leading,
            spacing: DesignTokens.Spacing.sm
          ) {
            stage("输入", icon: "shippingbox", active: true)
            stage(
              modeTitle,
              icon: modeIcon,
              active: model.isBusy || model.lastResolution?.state == "purified"
            )
            stage(
              "产物",
              icon: "diamond",
              active: model.lastResolution?.state == "purified"
            )
          }

          ArtifactMeterCard(
            "当前处理结果",
            value: model.meters["purification"] ?? 0,
            detail: "Gameplay State，不写入 canon.db。",
            systemIcon: "sun.max",
            tone: .gold
          )
        }

        ArtifactResolutionView(model: model)
      }
    }
  }

  private var header: some View {
    ViewThatFits(in: .horizontal) {
      HStack(alignment: .top, spacing: DesignTokens.Spacing.md) {
        headerText
        Spacer(minLength: DesignTokens.Spacing.md)
        modePill
      }

      VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
        headerText
        modePill
      }
    }
  }

  private var headerText: some View {
    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
      Text("净化工台")
        .font(Font.Mystic.titleMedium)
        .foregroundStyle(Color.Mystic.textGoldAccent)
      Text("净化、分离、提取属于材料与污染处理流程。")
        .mysticCaptionStyle()
        .fixedSize(horizontal: false, vertical: true)
    }
  }

  private var modePill: some View {
    ArtifactStatusPill(modeTitle, systemImage: modeIcon, tone: .gold)
  }

  private var intensityLabel: some View {
    Text("处理强度 \(Int(intensity * 100))%")
      .font(Font.Mystic.caption)
      .foregroundStyle(Color.Mystic.textSecondary)
  }

  private var selectionBadge: some View {
    MysticBadge("\(selected.count) 个目标", tone: .gold, systemIcon: "seal")
  }

  private var commitButton: some View {
    ArtifactHoldToCommitButton(
      "开始\(modeTitle)",
      systemImage: modeIcon,
      tone: .gold,
      disabled: selected.isEmpty || model.isBusy
    ) {
      model.performDetached(
        .init(
          artifactID: .unshadowedCrucifix,
          action: .purify,
          context: context,
          selectionIDs: Array(selected),
          numericParameters: ["intensity": intensity],
          stringParameters: ["mode": mode]
        )
      )
    }
  }

  private func stage(_ title: String, icon: String, active: Bool) -> some View {
    VStack(spacing: DesignTokens.Spacing.xs) {
      ZStack {
        Circle()
          .fill(active ? Color.Mystic.brassGoldPrimary.opacity(0.15) : Color.Mystic.obsidianElevated)
          .frame(width: 38, height: 38)
        Image(systemName: icon)
          .foregroundStyle(active ? Color.Mystic.brassGoldPrimary : Color.Mystic.textTertiary)
      }
      .accessibilityHidden(true)

      Text(title)
        .font(Font.Mystic.caption)
        .foregroundStyle(Color.Mystic.textSecondary)
    }
    .frame(maxWidth: .infinity, minHeight: 62)
    .accessibilityElement(children: .combine)
    .accessibilityLabel(title)
  }

  private var modeTitle: String {
    switch mode {
    case "separate": return "分离"
    case "extract": return "提取"
    default: return "净化"
    }
  }

  private var modeIcon: String {
    switch mode {
    case "separate": return "square.split.2x1"
    case "extract": return "arrow.up.right.and.arrow.down.left.rectangle"
    default: return "sun.max.fill"
    }
  }
}
