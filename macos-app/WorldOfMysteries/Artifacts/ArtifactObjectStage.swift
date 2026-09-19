import SwiftUI

/// Pure geometry used by the Object Stage and its contract tests.
public enum ArtifactObjectStageMetrics {
  public static let aspectRatio: CGFloat = 1.6
  public static let maximumParallax: CGFloat = 8

  public static func mountSide(
    for stageSize: CGSize,
    profile: ArtifactPresentationProfile
  ) -> CGFloat {
    guard stageSize.width > 0, stageSize.height > 0 else { return 0 }

    let heightBudget = stageSize.height * 0.68
    let widthBudget = stageSize.width * 0.48
    return max(0, min(heightBudget, widthBudget))
  }

  public static func anchorOffset(
    for stageSize: CGSize,
    anchor: ArtifactStageAnchor
  ) -> CGSize {
    CGSize(
      width: stageSize.width * anchor.horizontalBias * 0.24,
      height: stageSize.height * anchor.verticalBias * 0.24
    )
  }

  public static func parallaxOffset(
    for location: CGPoint?,
    in stageSize: CGSize,
    enabled: Bool
  ) -> CGSize {
    guard enabled, let location, stageSize.width > 0, stageSize.height > 0 else {
      return .zero
    }

    let normalizedX = min(max((location.x / stageSize.width) - 0.5, -0.5), 0.5)
    let normalizedY = min(max((location.y / stageSize.height) - 0.5, -0.5), 0.5)
    return CGSize(
      width: min(max(-normalizedX * maximumParallax, -maximumParallax), maximumParallax),
      height: min(max(-normalizedY * maximumParallax, -maximumParallax), maximumParallax)
    )
  }
}

/// A rectangular exhibition stage that keeps the canonical square artwork intact.
///
/// The stage is deliberately presentation-only: it owns no Artifact action, resolver or
/// Domain state. The current component remains the only source of gameplay interaction.
@MainActor
public struct ArtifactObjectStage: View {
  @Environment(\.accessibilityReduceMotion) private var reduceMotion
  @Environment(\.colorSchemeContrast) private var colorSchemeContrast

  private let descriptor: ArtifactDescriptor
  private let profile: ArtifactPresentationProfile
  private let revision: Int

  @State private var hoverLocation: CGPoint?

  public init(artifactID: ArtifactID, revision: Int = 0) {
    self.descriptor = ArtifactRegistry.descriptor(for: artifactID)
    self.profile = ArtifactPresentationProfiles.profile(for: artifactID)
    self.revision = revision
  }

  public var body: some View {
    GeometryReader { proxy in
      let stageSize = resolvedStageSize(for: proxy.size)

      stageContent(size: stageSize)
        .frame(width: stageSize.width, height: stageSize.height)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .onContinuousHover(coordinateSpace: .local) { phase in
          guard !reduceMotion, profile.assetCapabilities.coarseDepth else {
            hoverLocation = nil
            return
          }

          switch phase {
          case .active(let location):
            hoverLocation = location
          case .ended:
            hoverLocation = nil
          @unknown default:
            hoverLocation = nil
          }
        }
    }
    .frame(maxWidth: .infinity)
    .aspectRatio(ArtifactObjectStageMetrics.aspectRatio, contentMode: .fit)
    .frame(minHeight: 300, maxHeight: 520)
    .id(revision)
    .accessibilityElement(children: .ignore)
    .accessibilityLabel(
      "当前展品：\(descriptor.displayName)，\(profile.archetype.localizedTitle)"
    )
    .accessibilityValue("方形原图等比挂载在长方形展台中")
    .accessibilityHint("展台装饰不影响神器操作；操作请使用下方实时神器操作台")
  }

  private func resolvedStageSize(for proposedSize: CGSize) -> CGSize {
    let width = proposedSize.width.isFinite && proposedSize.width > 0
      ? proposedSize.width
      : 720
    return CGSize(
      width: width,
      height: width / ArtifactObjectStageMetrics.aspectRatio
    )
  }

  @ViewBuilder
  private func stageContent(size: CGSize) -> some View {
    let mountSide = max(
      180,
      ArtifactObjectStageMetrics.mountSide(for: size, profile: profile)
    )
    let anchorOffset = ArtifactObjectStageMetrics.anchorOffset(
      for: size,
      anchor: profile.stageAnchor
    )
    let parallax = ArtifactObjectStageMetrics.parallaxOffset(
      for: hoverLocation,
      in: size,
      enabled: !reduceMotion && profile.assetCapabilities.coarseDepth
    )

    stageBackdrop
      .frame(width: size.width, height: size.height)
      .overlay {
        stageAtmosphere
          .frame(width: size.width, height: size.height)
      }
      .overlay {
        objectMount(side: mountSide, parallax: parallax)
          .offset(x: anchorOffset.width, y: anchorOffset.height)
      }
      .overlay(alignment: .bottom) {
        stagePlaque
          .padding(.bottom, max(10, size.height * 0.035))
      }
      .overlay {
        stageBorder
          .frame(width: size.width, height: size.height)
      }
    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.lg, style: .continuous))
    .contentShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.lg, style: .continuous))
  }

  private var stageBackdrop: some View {
    ZStack {
      Color.Mystic.deepVoid

      WOMArtworkView(
        assetName: WOMWorldArtworkAsset.artifactVault.runtimeAssetName,
        fallback: .asset(.artifact),
        fallbackTint: environmentAccent,
        contentMode: .fill
      )
      .opacity(colorSchemeContrast == .increased ? 0.10 : 0.18)
      .accessibilityHidden(true)

      LinearGradient(
        colors: [
          Color.Mystic.abyssVoid.opacity(0.32),
          Color.Mystic.deepVoid.opacity(0.08),
          Color.Mystic.abyssVoid.opacity(0.58),
        ],
        startPoint: .topLeading,
        endPoint: .bottomTrailing
      )

      WOMTextureLayer(.sacredSlate, opacity: colorSchemeContrast == .increased ? 0.018 : 0.035)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .allowsHitTesting(false)
  }

  private var stageAtmosphere: some View {
    ZStack {
      Circle()
        .fill(environmentAccent.opacity(0.08))
        .frame(width: 360, height: 360)
        .blur(radius: 40)
        .offset(x: 110, y: -80)

      RoundedRectangle(cornerRadius: 18, style: .continuous)
        .stroke(environmentAccent.opacity(0.13), lineWidth: DesignTokens.Borders.hairline)
        .padding(18)

      VStack {
        HStack {
          stageCornerMark
          Spacer()
          stageCornerMark
        }
        Spacer()
        HStack {
          stageCornerMark
          Spacer()
          stageCornerMark
        }
      }
      .padding(16)
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .allowsHitTesting(false)
    .accessibilityHidden(true)
  }

  private var stageCornerMark: some View {
    Image(systemName: "diamond")
      .font(.system(size: 10, weight: .light))
      .foregroundStyle(environmentAccent.opacity(0.42))
  }

  @ViewBuilder
  private func objectMount(side: CGFloat, parallax: CGSize) -> some View {
    let artworkSide = max(0, side * 0.80)

    ZStack {
      mountSurface(side: side)

      RoundedRectangle(cornerRadius: max(8, side * 0.08), style: .continuous)
        .fill(Color.Mystic.abyssVoid.opacity(0.62))
        .frame(width: artworkSide, height: artworkSide)
        .overlay {
          WOMArtworkView(
            assetName: descriptor.id.artworkAsset.assetName(for: profile.artworkVariant)
              ?? descriptor.id.artworkAsset.detailAssetName,
            fallback: .systemImage(descriptor.systemIcon),
            fallbackTint: descriptor.tone.accent,
            contentMode: .fit,
            accessibilityLabel: descriptor.displayName
          )
          .frame(width: artworkSide, height: artworkSide)
          .clipShape(RoundedRectangle(cornerRadius: max(6, side * 0.06), style: .continuous))
          .shadow(
            color: Color.black.opacity(profile.assetCapabilities.contactShadow ? 0.60 : 0.42),
            radius: profile.assetCapabilities.contactShadow ? 16 : 10,
            y: 10
          )
          .offset(parallax)
        }

      if profile.assetCapabilities.rimLight {
        RoundedRectangle(cornerRadius: max(8, side * 0.08), style: .continuous)
          .stroke(
            LinearGradient(
              colors: [
                environmentAccent.opacity(0.72),
                Color.clear,
                Color.Mystic.brassGoldBorder.opacity(0.50),
              ],
              startPoint: .topLeading,
              endPoint: .bottomTrailing
            ),
            lineWidth: DesignTokens.Borders.standard
          )
          .frame(width: side, height: side)
          .offset(parallax)
          .allowsHitTesting(false)
      }
    }
    .frame(width: side, height: side)
  }

  @ViewBuilder
  private func mountSurface(side: CGFloat) -> some View {
    switch profile.mount {
    case .framedSquare:
      RoundedRectangle(cornerRadius: max(12, side * 0.10), style: .continuous)
        .fill(Color.Mystic.obsidianElevated.opacity(0.92))
        .overlay {
          RoundedRectangle(cornerRadius: max(12, side * 0.10), style: .continuous)
            .stroke(Color.Mystic.brassGoldBorder.opacity(0.72), lineWidth: 2)
        }
        .shadow(color: Color.black.opacity(0.44), radius: 18, y: 12)

    case .plinthSquare:
      RoundedRectangle(cornerRadius: max(14, side * 0.12), style: .continuous)
        .fill(
          LinearGradient(
            colors: [Color.Mystic.obsidianElevated, Color.Mystic.abyssVoid],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
          )
        )
        .overlay {
          RoundedRectangle(cornerRadius: max(14, side * 0.12), style: .continuous)
            .stroke(environmentAccent.opacity(0.60), lineWidth: DesignTokens.Borders.standard)
        }
        .shadow(color: Color.black.opacity(0.48), radius: 22, y: 16)

    case .bookCradle:
      RoundedRectangle(cornerRadius: max(10, side * 0.08), style: .continuous)
        .fill(Color.Mystic.parchmentCard.opacity(0.18))
        .overlay {
          RoundedRectangle(cornerRadius: max(10, side * 0.08), style: .continuous)
            .stroke(Color.Mystic.brassGoldBorder.opacity(0.72), lineWidth: 2)
        }
        .overlay(alignment: .bottom) {
          Rectangle()
            .fill(Color.Mystic.brassGoldPrimary.opacity(0.62))
            .frame(height: 8)
            .padding(.horizontal, side * 0.14)
            .padding(.bottom, side * 0.06)
        }
        .shadow(color: Color.black.opacity(0.42), radius: 18, y: 12)

    case .suspendedSquare:
      RoundedRectangle(cornerRadius: max(12, side * 0.10), style: .continuous)
        .fill(Color.Mystic.deepVoid.opacity(0.78))
        .overlay {
          RoundedRectangle(cornerRadius: max(12, side * 0.10), style: .continuous)
            .stroke(environmentAccent.opacity(0.72), style: StrokeStyle(lineWidth: 1, dash: [5, 6]))
        }
        .shadow(color: environmentAccent.opacity(0.20), radius: 26, y: 8)

    case .ritualTray:
      RoundedRectangle(cornerRadius: max(16, side * 0.14), style: .continuous)
        .fill(Color.Mystic.obsidianElevated.opacity(0.92))
        .overlay {
          RoundedRectangle(cornerRadius: max(16, side * 0.14), style: .continuous)
            .stroke(Color.Mystic.brassGoldBorder.opacity(0.66), lineWidth: 2)
        }
        .overlay {
          Circle()
            .stroke(environmentAccent.opacity(0.28), lineWidth: 1)
            .padding(side * 0.17)
        }
        .shadow(color: Color.black.opacity(0.46), radius: 20, y: 14)
    }
  }

  private var stagePlaque: some View {
    HStack(spacing: DesignTokens.Spacing.sm) {
      Image(systemName: profile.mount.systemImage)
        .font(.system(size: 11, weight: .medium))
        .foregroundStyle(environmentAccent)

      Text(descriptor.displayName)
        .font(Font.Mystic.monoBadge)
        .foregroundStyle(Color.Mystic.textPrimary)
        .lineLimit(1)

      Text("·")
        .foregroundStyle(Color.Mystic.textTertiary)

      Text(profile.archetype.localizedTitle)
        .font(Font.Mystic.monoBadge)
        .foregroundStyle(Color.Mystic.textTertiary)
        .lineLimit(1)
    }
    .padding(.horizontal, DesignTokens.Spacing.md)
    .padding(.vertical, DesignTokens.Spacing.xs)
    .background(Color.Mystic.obsidianGlass.opacity(0.90))
    .clipShape(Capsule())
    .overlay {
      Capsule().stroke(environmentAccent.opacity(0.36), lineWidth: DesignTokens.Borders.hairline)
    }
    .accessibilityHidden(true)
  }

  private var stageBorder: some View {
    RoundedRectangle(cornerRadius: DesignTokens.Radii.lg, style: .continuous)
      .stroke(
        colorSchemeContrast == .increased
          ? Color.Mystic.textGoldAccent
          : Color.Mystic.brassGoldBorder.opacity(0.52),
        lineWidth: colorSchemeContrast == .increased
          ? DesignTokens.Borders.standard
          : DesignTokens.Borders.hairline
      )
      .allowsHitTesting(false)
      .accessibilityHidden(true)
  }

  private var environmentAccent: Color {
    switch profile.environmentToken {
    case .obsidian: Color.Mystic.textSecondary
    case .brass: Color.Mystic.brassGoldPrimary
    case .azure: Color.Mystic.spiritualBlue
    case .teal: Color.Mystic.statusOnline
    case .amber: Color.Mystic.statusWarning
    case .ritual: Color.Mystic.statusDanger
    }
  }
}
