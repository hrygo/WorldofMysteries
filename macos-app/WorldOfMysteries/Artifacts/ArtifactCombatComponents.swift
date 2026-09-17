import SwiftUI

// MARK: - 蠕动的饥饿

public struct GrazedSoulSlot: Identifiable, Hashable, Sendable {
  public var id: String
  public var displayName: String
  public var pathway: String
  public var abilityNames: [String]

  public init(id: String, displayName: String, pathway: String, abilityNames: [String]) {
    self.id = id
    self.displayName = displayName
    self.pathway = pathway
    self.abilityNames = abilityNames
  }
}

@MainActor
public struct CreepingHungerArtifactView: View {
  @Bindable private var model: ArtifactActionModel
  private let context: ArtifactContext
  private let souls: [GrazedSoulSlot]

  @State private var selectedSoulID: String?
  @State private var selectedAbility = ""

  public init(model: ArtifactActionModel, context: ArtifactContext, souls: [GrazedSoulSlot]) {
    self.model = model
    self.context = context
    self.souls = souls
  }

  public var body: some View {
    ArtifactComponentShell(artifactID: .creepingHunger) {
      VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
        hungerHeader

        ArtifactSection("放牧槽位", caption: "选择灵魂后再选择可调用能力", tone: .crimson) {
          LazyVGrid(
            columns: [GridItem(.adaptive(minimum: 150), spacing: DesignTokens.Spacing.sm)],
            spacing: DesignTokens.Spacing.sm
          ) {
            ForEach(souls) { soul in
              Button {
                selectedSoulID = soul.id
                selectedAbility = soul.abilityNames.first ?? ""
              } label: {
                VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
                  HStack {
                    Image(
                      systemName: selectedSoulID == soul.id
                        ? "person.crop.circle.fill" : "person.crop.circle"
                    )
                    .foregroundStyle(
                      selectedSoulID == soul.id
                        ? Color.Mystic.statusDanger : Color.Mystic.textTertiary
                    )
                    .accessibilityHidden(true)
                    Spacer()
                    Text("\(soul.abilityNames.count)")
                      .font(Font.Mystic.monoBadge)
                      .foregroundStyle(Color.Mystic.textTertiary)
                  }

                  Text(soul.displayName)
                    .font(Font.Mystic.titleSmall)
                    .foregroundStyle(Color.Mystic.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)

                  Text(soul.pathway)
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textTertiary)
                    .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(DesignTokens.Spacing.md)
                .background(Color.Mystic.obsidianElevated)
                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
                .mysticCardSelection(isSelected: selectedSoulID == soul.id)
              }
              .buttonStyle(.plain)
              .accessibilityLabel(soul.displayName)
              .accessibilityValue(selectedSoulID == soul.id ? "已选中" : "未选中")
            }
          }

          ArtifactMeterCard(
            "饥饿",
            value: hunger,
            detail: hunger > 0.72 ? "高风险：继续调用可能触发更强副作用。" : "每次能力调用都会提高饥饿。",
            systemIcon: "waveform.path.ecg",
            tone: hunger > 0.72 ? .crimson : .amber
          )
        }

        if let soul = selectedSoul {
          ArtifactSection(soul.displayName, caption: soul.pathway, tone: .crimson) {
            LazyVGrid(
              columns: [GridItem(.adaptive(minimum: 130))],
              alignment: .leading,
              spacing: DesignTokens.Spacing.xs
            ) {
              ForEach(soul.abilityNames, id: \.self) { ability in
                Button {
                  selectedAbility = ability
                } label: {
                  MysticBadge(
                    ability,
                    tone: selectedAbility == ability ? .crimson : .neutral,
                    systemIcon: "sparkles",
                    isEmphasized: selectedAbility == ability
                  )
                }
                .buttonStyle(.plain)
              }
            }

            ViewThatFits(in: .horizontal) {
              HStack(spacing: DesignTokens.Spacing.md) {
                soulInvocationNote
                Spacer(minLength: DesignTokens.Spacing.md)
                soulInvocationButton(soul)
              }

              VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
                soulInvocationNote
                soulInvocationButton(soul)
              }
            }
          }
        }

        ArtifactResolutionView(model: model)
      }
    }
  }

  private var hungerHeader: some View {
    ViewThatFits(in: .horizontal) {
      HStack(alignment: .top, spacing: DesignTokens.Spacing.md) {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
          Text("灵魂负载")
            .font(Font.Mystic.titleMedium)
            .foregroundStyle(Color.Mystic.textGoldAccent)
          Text("每个槽位代表具体灵魂，不是普通技能栏。")
            .mysticCaptionStyle()
            .fixedSize(horizontal: false, vertical: true)
        }
        Spacer(minLength: DesignTokens.Spacing.md)
        hungerPill
      }

      VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
          Text("灵魂负载")
            .font(Font.Mystic.titleMedium)
            .foregroundStyle(Color.Mystic.textGoldAccent)
          Text("每个槽位代表具体灵魂，不是普通技能栏。")
            .mysticCaptionStyle()
        }
        hungerPill
      }
    }
  }

  private var hungerPill: some View {
    ArtifactStatusPill(
      hungerLabel,
      systemImage: "waveform.path.ecg",
      tone: hunger > 0.72 ? .crimson : .amber
    )
  }

  private var soulInvocationNote: some View {
    Text("调用仍需经过 Character Capability / Outcome Resolver。")
      .mysticCaptionStyle()
      .fixedSize(horizontal: false, vertical: true)
  }

  private func soulInvocationButton(_ soul: GrazedSoulSlot) -> some View {
    ArtifactHoldToCommitButton(
      "调用灵魂能力",
      systemImage: "hand.tap",
      tone: .crimson,
      holdDuration: 0.7,
      disabled: selectedAbility.isEmpty || model.isBusy
    ) {
      model.performDetached(
        .init(
          artifactID: .creepingHunger,
          action: .invokeSoul,
          context: context,
          input: selectedAbility,
          selectionIDs: [soul.id],
          numericParameters: ["hunger": hunger]
        )
      )
    }
  }

  private var selectedSoul: GrazedSoulSlot? {
    souls.first(where: { $0.id == selectedSoulID })
  }

  private var hunger: Double {
    min(max(model.meters["hunger"] ?? 0.28, 0), 1)
  }

  private var hungerLabel: String {
    if hunger < 0.35 { return "轻微饥饿" }
    if hunger < 0.72 { return "饥饿" }
    return "强烈饥饿"
  }
}

// MARK: - 海神权杖

public struct ArtifactPrayerItem: Identifiable, Hashable, Sendable {
  public var id: String
  public var petitioner: String
  public var summary: String

  public init(id: String, petitioner: String, summary: String) {
    self.id = id
    self.petitioner = petitioner
    self.summary = summary
  }
}

@MainActor
public struct SeaGodScepterArtifactView: View {
  @Bindable private var model: ArtifactActionModel
  private let context: ArtifactContext
  private let prayers: [ArtifactPrayerItem]

  @State private var authority = "storm"
  @State private var intensity = 0.48
  @State private var selectedPrayerID: String?
  @State private var prayerResponse = "omen"

  public init(
    model: ArtifactActionModel,
    context: ArtifactContext,
    prayers: [ArtifactPrayerItem] = []
  ) {
    self.model = model
    self.context = context
    self.prayers = prayers
  }

  public var body: some View {
    ArtifactComponentShell(artifactID: .seaGodScepter) {
      VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
        authorityHeader
        authorityConsole

        if !prayers.isEmpty {
          prayerSection
        }

        ArtifactResolutionView(model: model)
      }
    }
  }

  private var authorityHeader: some View {
    ViewThatFits(in: .horizontal) {
      HStack(alignment: .top, spacing: DesignTokens.Spacing.md) {
        authorityHeaderText
        Spacer(minLength: DesignTokens.Spacing.md)
        authorityPill
      }

      VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
        authorityHeaderText
        authorityPill
      }
    }
  }

  private var authorityHeaderText: some View {
    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
      Text("海洋权柄")
        .font(Font.Mystic.titleMedium)
        .foregroundStyle(Color.Mystic.textGoldAccent)
      Text("环境权柄与祈祷回应是两套独立交互。")
        .mysticCaptionStyle()
        .fixedSize(horizontal: false, vertical: true)
    }
  }

  private var authorityPill: some View {
    ArtifactStatusPill(
      authorityTitle(authority),
      systemImage: authorityIcon(authority),
      tone: .azure
    )
  }

  private var authorityConsole: some View {
    ArtifactSection("权柄控制台", caption: "强度是 Gameplay 输入；最终影响范围由世界规则决定", tone: .azure) {
      Picker("环境权柄", selection: $authority) {
        Text("风暴").tag("storm")
        Text("雷电").tag("lightning")
        Text("海浪").tag("sea")
        Text("狂风").tag("wind")
      }
      .pickerStyle(.segmented)

      ZStack {
        ArtifactAmbientField(tone: .azure, intensity: intensity, particleCount: 24)
        Image(systemName: authorityIcon(authority))
          .font(.system(size: 56, weight: .ultraLight))
          .foregroundStyle(Color.Mystic.spiritualBlue)
          .accessibilityHidden(true)
      }
      .frame(maxWidth: .infinity, minHeight: 150)
      .background(Color.Mystic.abyssVoid)
      .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))

      ViewThatFits(in: .horizontal) {
        HStack(spacing: DesignTokens.Spacing.md) {
          intensityLabel
          Slider(value: $intensity, in: 0.15...1)
        }

        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
          intensityLabel
          Slider(value: $intensity, in: 0.15...1)
        }
      }

      ArtifactMeterCard(
        "权柄负载",
        value: model.meters["authorityLoad"] ?? 0.12,
        detail: "高强度调用应增加世界事件权重与后续负载。",
        systemIcon: "waveform.path.ecg",
        tone: .azure
      )

      HStack {
        Spacer()
        ArtifactHoldToCommitButton(
          "调用\(authorityTitle(authority))",
          systemImage: authorityIcon(authority),
          tone: .azure,
          holdDuration: 0.75,
          disabled: model.isBusy
        ) {
          model.performDetached(
            .init(
              artifactID: .seaGodScepter,
              action: .invokeAuthority,
              context: context,
              input: authorityTitle(authority),
              numericParameters: ["intensity": intensity],
              stringParameters: ["authority": authority]
            )
          )
        }
      }
    }
  }

  private var intensityLabel: some View {
    Text("调用强度 \(Int(intensity * 100))%")
      .font(Font.Mystic.caption)
      .foregroundStyle(Color.Mystic.textSecondary)
  }

  private var prayerSection: some View {
    ArtifactSection("祈祷", caption: "回应形成 WorldEvent Candidate，不直接覆盖角色状态", tone: .teal) {
      ForEach(prayers) { prayer in
        Button {
          selectedPrayerID = prayer.id
        } label: {
          HStack(alignment: .top, spacing: DesignTokens.Spacing.sm) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
              Text(prayer.petitioner)
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
              Text(prayer.summary)
                .mysticCaptionStyle()
                .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            Image(systemName: selectedPrayerID == prayer.id ? "checkmark.circle.fill" : "circle")
              .foregroundStyle(
                selectedPrayerID == prayer.id
                  ? Color.Mystic.statusOnline : Color.Mystic.textTertiary
              )
              .accessibilityHidden(true)
          }
          .padding(DesignTokens.Spacing.sm)
          .background(Color.Mystic.obsidianElevated)
          .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(prayer.petitioner)，\(prayer.summary)")
        .accessibilityValue(selectedPrayerID == prayer.id ? "已选中" : "未选中")
      }

      ViewThatFits(in: .horizontal) {
        HStack(spacing: DesignTokens.Spacing.md) {
          responsePicker
            .frame(width: 150)
          Spacer(minLength: DesignTokens.Spacing.md)
          responseButton
        }

        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
          responsePicker
          responseButton
        }
      }
    }
  }

  private var responsePicker: some View {
    Picker("回应", selection: $prayerResponse) {
      Text("征兆").tag("omen")
      Text("神迹").tag("miracle")
      Text("低语").tag("whisper")
    }
  }

  private var responseButton: some View {
    Button("回应所选祈祷") {
      guard let selectedPrayerID else { return }
      model.performDetached(
        .init(
          artifactID: .seaGodScepter,
          action: .answerPrayer,
          context: context,
          selectionIDs: [selectedPrayerID],
          stringParameters: ["response": prayerResponse]
        )
      )
    }
    .buttonStyle(WOMButtonStyle(.secondary))
    .disabled(selectedPrayerID == nil || model.isBusy)
  }

  private func authorityTitle(_ value: String) -> String {
    switch value {
    case "lightning": return "雷电"
    case "sea": return "海浪"
    case "wind": return "狂风"
    default: return "风暴"
    }
  }

  private func authorityIcon(_ value: String) -> String {
    switch value {
    case "lightning": return "bolt.fill"
    case "sea": return "water.waves"
    case "wind": return "wind"
    default: return "cloud.bolt.rain.fill"
    }
  }
}

// MARK: - 丧钟

public struct KnownArtifactWeakness: Identifiable, Hashable, Sendable {
  public var id: String
  public var title: String
  public var confidence: Double

  public init(id: String, title: String, confidence: Double) {
    self.id = id
    self.title = title
    self.confidence = min(max(confidence, 0), 1)
  }
}

@MainActor
public struct DeathKnellArtifactView: View {
  @Bindable private var model: ArtifactActionModel
  private let context: ArtifactContext
  private let targetID: String
  private let weaknesses: [KnownArtifactWeakness]
  private let roundsRemaining: Int?

  @State private var selectedID: String?
  @State private var lockedID: String?
  @State private var shotsFired = 0

  public init(
    model: ArtifactActionModel,
    context: ArtifactContext,
    targetID: String,
    weaknesses: [KnownArtifactWeakness],
    roundsRemaining: Int? = nil
  ) {
    self.model = model
    self.context = context
    self.targetID = targetID
    self.weaknesses = weaknesses
    self.roundsRemaining = roundsRemaining
  }

  public var body: some View {
    ArtifactComponentShell(artifactID: .deathKnell) {
      VStack(alignment: .leading, spacing: DesignTokens.LayoutInsets.stackSpacingLg) {
        deathKnellHeader
        targetSection
        ArtifactResolutionView(model: model)
        triggerSection
      }
    }
  }

  private var deathKnellHeader: some View {
    ViewThatFits(in: .horizontal) {
      HStack(alignment: .top, spacing: DesignTokens.Spacing.md) {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
          Text("弱点瞄准")
            .font(Font.Mystic.titleMedium)
            .foregroundStyle(Color.Mystic.textGoldAccent)
          Text("Weakness Candidate 必须有 Observation / Knowledge Evidence。")
            .mysticCaptionStyle()
            .fixedSize(horizontal: false, vertical: true)
        }
        Spacer(minLength: DesignTokens.Spacing.md)
        lockPill
      }

      VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
          Text("弱点瞄准")
            .font(Font.Mystic.titleMedium)
            .foregroundStyle(Color.Mystic.textGoldAccent)
          Text("Weakness Candidate 必须有 Observation / Knowledge Evidence。")
            .mysticCaptionStyle()
        }
        lockPill
      }
    }
  }

  private var lockPill: some View {
    ArtifactStatusPill(
      lockedID == nil ? "搜索弱点" : "已锁定",
      systemImage: "scope",
      tone: lockedID == nil ? .neutral : .crimson
    )
  }

  private var targetSection: some View {
    ArtifactSection("TARGET · \(targetID)", caption: "选择有证据支持的弱点，再建立锁定", tone: .crimson) {
      ViewThatFits(in: .horizontal) {
        HStack(alignment: .top, spacing: DesignTokens.Spacing.lg) {
          reticlePanel
          weaknessList
            .frame(maxWidth: .infinity, alignment: .leading)
        }

        VStack(alignment: .leading, spacing: DesignTokens.Spacing.md) {
          reticlePanel
            .frame(maxWidth: .infinity, alignment: .center)
          weaknessList
        }
      }
    }
  }

  private var reticlePanel: some View {
    ZStack {
      ArtifactReticleSurface(
        locked: lockedID != nil,
        confidence: selectedWeakness?.confidence ?? 0
      )

      VStack(spacing: DesignTokens.Spacing.xs) {
        Text(selectedWeakness?.title ?? "NO LOCK")
          .font(Font.Mystic.caption)
          .foregroundStyle(Color.Mystic.textPrimary)
          .multilineTextAlignment(.center)
          .fixedSize(horizontal: false, vertical: true)

        if let selectedWeakness {
          Text("\(Int(selectedWeakness.confidence * 100))% evidence")
            .font(Font.Mystic.monoBadge)
            .foregroundStyle(Color.Mystic.textTertiary)
        }
      }
      .frame(width: 125)
    }
    .frame(width: 200, height: 200)
  }

  private var weaknessList: some View {
    VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
      ForEach(weaknesses) { weakness in
        Button {
          selectedID = weakness.id
          if lockedID != weakness.id {
            lockedID = nil
          }
        } label: {
          HStack(spacing: DesignTokens.Spacing.sm) {
            VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
              Text(weakness.title)
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
              MysticMetricBar(value: weakness.confidence, tone: .crimson)
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            Text("\(Int(weakness.confidence * 100))%")
              .font(Font.Mystic.monoBadge)
              .foregroundStyle(Color.Mystic.textTertiary)
          }
          .padding(DesignTokens.Spacing.sm)
          .background(Color.Mystic.obsidianElevated)
          .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
          .mysticCardSelection(isSelected: selectedID == weakness.id)
        }
        .buttonStyle(.plain)
      }

      Button("验证并锁定") {
        lockSelectedWeakness()
      }
      .buttonStyle(WOMButtonStyle(.secondary))
      .disabled(selectedID == nil || model.isBusy)
    }
  }

  private var triggerSection: some View {
    ArtifactSection("扳机", caption: "锁定不是射击；扣动扳机才进入 Combat / Outcome Resolver", tone: .crimson) {
      ViewThatFits(in: .horizontal) {
        HStack(alignment: .center, spacing: DesignTokens.Spacing.md) {
          ammunitionStatus
          Spacer(minLength: DesignTokens.Spacing.md)
          fireButton
        }

        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
          ammunitionStatus
          fireButton
        }
      }
    }
  }

  private var ammunitionStatus: some View {
    VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
      if let roundsRemaining {
        Text("剩余弹药 \(max(0, roundsRemaining - shotsFired))")
          .font(Font.Mystic.titleSmall)
          .foregroundStyle(Color.Mystic.textPrimary)
        Text("弹药数量由装备系统输入，不在组件内硬编码 Canon。")
          .mysticCaptionStyle()
          .fixedSize(horizontal: false, vertical: true)
      } else {
        Text("弹药状态由装备系统决定")
          .mysticCaptionStyle()
      }
    }
  }

  private var fireButton: some View {
    ArtifactHoldToCommitButton(
      "扣动扳机",
      systemImage: "scope",
      tone: .crimson,
      holdDuration: 0.6,
      disabled: lockedID == nil || model.isBusy || noRounds
    ) {
      guard let lockedID else { return }
      Task {
        await model.perform(
          .init(
            artifactID: .deathKnell,
            action: .fireWeaknessShot,
            context: context,
            selectionIDs: [targetID, lockedID]
          )
        )
        if model.lastResolution?.disposition == .committed {
          shotsFired += 1
        }
      }
    }
  }

  private var selectedWeakness: KnownArtifactWeakness? {
    weaknesses.first(where: { $0.id == selectedID })
  }

  private var noRounds: Bool {
    roundsRemaining.map { $0 - shotsFired <= 0 } ?? false
  }

  private func lockSelectedWeakness() {
    guard let selectedID else { return }
    Task {
      await model.perform(
        .init(
          artifactID: .deathKnell,
          action: .targetWeakness,
          context: context,
          selectionIDs: [targetID, selectedID]
        )
      )
      if model.lastResolution?.state == "target_locked" {
        lockedID = selectedID
      }
    }
  }
}
