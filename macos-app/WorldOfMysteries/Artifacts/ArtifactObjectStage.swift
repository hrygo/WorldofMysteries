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
        objectMount(side: mountSide, parallax: parallax)
          .offset(x: anchorOffset.width, y: anchorOffset.height)
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
      Color.Mystic.obsidianBase

      RadialGradient(
        colors: [
          environmentAccent.opacity(colorSchemeContrast == .increased ? 0.08 : 0.13),
          Color.clear,
        ],
        center: .center,
        startRadius: 20,
        endRadius: 360
      )

      floorGlow

      LinearGradient(
        colors: [
          Color.clear,
          Color.Mystic.deepVoid.opacity(0.30),
        ],
        startPoint: .top,
        endPoint: .bottom
      )

      WOMTextureLayer(.sacredSlate, opacity: colorSchemeContrast == .increased ? 0.014 : 0.026)

      VStack(spacing: 0) {
        Spacer()
        Rectangle()
          .fill(Color.Mystic.brassGoldBorder.opacity(0.22))
          .frame(height: DesignTokens.Borders.hairline)
          .padding(.horizontal, 34)
          .padding(.bottom, 26)
      }
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .allowsHitTesting(false)
    .accessibilityHidden(true)
  }

  private var floorGlow: some View {
    Ellipse()
      .fill(environmentAccent.opacity(0.13))
      .frame(width: 300, height: 72)
      .blur(radius: 24)
      .offset(y: 122)
      .accessibilityHidden(true)
  }

  @ViewBuilder
  private func objectMount(side: CGFloat, parallax: CGSize) -> some View {
    let artworkSide = max(0, side * 0.78)
    let tiltX = Double(parallax.height) * 0.18
    let tiltY = Double(-parallax.width) * 0.18

    ZStack(alignment: .bottom) {
      objectShadow(side: side)
      objectPedestal(side: side)
      mountDepth(side: side)

      ZStack {
        mountSurface(side: side)

        RoundedRectangle(cornerRadius: max(8, side * 0.08), style: .continuous)
          .fill(Color.Mystic.abyssVoid.opacity(0.68))
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
              color: Color.black.opacity(profile.assetCapabilities.contactShadow ? 0.62 : 0.46),
              radius: profile.assetCapabilities.contactShadow ? 18 : 12,
              y: 12
            )
            .offset(parallax)
            .rotation3DEffect(
              .degrees(tiltX),
              axis: (x: 1, y: 0, z: 0),
              perspective: 0.55
            )
            .rotation3DEffect(
              .degrees(tiltY),
              axis: (x: 0, y: 1, z: 0),
              perspective: 0.55
            )
          }
          .overlay {
            LinearGradient(
              colors: [
                Color.white.opacity(0.16),
                Color.clear,
                Color.black.opacity(0.18),
              ],
              startPoint: .topLeading,
              endPoint: .bottomTrailing
            )
            .clipShape(RoundedRectangle(cornerRadius: max(6, side * 0.06), style: .continuous))
            .allowsHitTesting(false)
            .offset(parallax)
            .rotation3DEffect(
              .degrees(tiltX),
              axis: (x: 1, y: 0, z: 0),
              perspective: 0.55
            )
            .rotation3DEffect(
              .degrees(tiltY),
              axis: (x: 0, y: 1, z: 0),
              perspective: 0.55
            )
          }
      }
      .frame(width: side, height: side)

      if profile.assetCapabilities.rimLight {
        RoundedRectangle(cornerRadius: max(8, side * 0.08), style: .continuous)
          .stroke(
            LinearGradient(
              colors: [
                mountAccent.opacity(0.58),
                Color.clear,
                mountAccent.opacity(0.24),
              ],
              startPoint: .topLeading,
              endPoint: .bottomTrailing
            ),
            lineWidth: DesignTokens.Borders.hairline
          )
          .frame(width: side * 0.92, height: side * 0.92)
          .offset(parallax)
          .allowsHitTesting(false)
      }
    }
    .frame(width: side, height: side)
  }

  private func mountDepth(side: CGFloat) -> some View {
    RoundedRectangle(cornerRadius: max(12, side * 0.10), style: .continuous)
      .fill(Color.black.opacity(0.62))
      .frame(width: side * 0.96, height: side * 0.96)
      .offset(y: side * 0.035)
      .accessibilityHidden(true)
  }

  private func objectPedestal(side: CGFloat) -> some View {
    RoundedRectangle(cornerRadius: max(8, side * 0.045), style: .continuous)
      .fill(
        LinearGradient(
          colors: [Color.Mystic.obsidianElevated, Color.Mystic.deepVoid],
          startPoint: .top,
          endPoint: .bottom
        )
      )
      .frame(width: side * 0.72, height: side * 0.12)
      .overlay {
        RoundedRectangle(cornerRadius: max(8, side * 0.045), style: .continuous)
          .stroke(mountAccent.opacity(0.34), lineWidth: DesignTokens.Borders.hairline)
      }
      .shadow(color: Color.black.opacity(0.44), radius: 10, y: 8)
      .offset(y: side * 0.43)
      .accessibilityHidden(true)
  }

  private func objectShadow(side: CGFloat) -> some View {
    Ellipse()
      .fill(Color.black.opacity(0.44))
      .frame(width: side * 0.78, height: side * 0.09)
      .blur(radius: max(4, side * 0.035))
      .offset(y: side * 0.44)
      .accessibilityHidden(true)
  }

  @ViewBuilder
  private func mountSurface(side: CGFloat) -> some View {
    switch profile.mount {
    case .framedSquare:
      RoundedRectangle(cornerRadius: max(12, side * 0.10), style: .continuous)
        .fill(Color.Mystic.obsidianElevated.opacity(0.92))
        .overlay {
          RoundedRectangle(cornerRadius: max(12, side * 0.10), style: .continuous)
            .stroke(mountAccent.opacity(0.46), lineWidth: DesignTokens.Borders.hairline)
        }
        .shadow(color: Color.black.opacity(0.34), radius: 14, y: 10)

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
            .stroke(mountAccent.opacity(0.50), lineWidth: DesignTokens.Borders.hairline)
        }
        .shadow(color: Color.black.opacity(0.38), radius: 16, y: 12)

    case .bookCradle:
      RoundedRectangle(cornerRadius: max(10, side * 0.08), style: .continuous)
        .fill(Color.Mystic.parchmentCard.opacity(0.18))
        .overlay {
          RoundedRectangle(cornerRadius: max(10, side * 0.08), style: .continuous)
            .stroke(mountAccent.opacity(0.48), lineWidth: DesignTokens.Borders.hairline)
        }
        .overlay(alignment: .bottom) {
          Rectangle()
            .fill(mountAccent.opacity(0.56))
            .frame(height: 6)
            .padding(.horizontal, side * 0.14)
            .padding(.bottom, side * 0.06)
        }
        .shadow(color: Color.black.opacity(0.34), radius: 14, y: 10)

    case .suspendedSquare:
      RoundedRectangle(cornerRadius: max(12, side * 0.10), style: .continuous)
        .fill(Color.Mystic.deepVoid.opacity(0.78))
        .overlay {
            RoundedRectangle(cornerRadius: max(12, side * 0.10), style: .continuous)
            .stroke(mountAccent.opacity(0.46), style: StrokeStyle(lineWidth: 1, dash: [5, 6]))
        }
        .shadow(color: mountAccent.opacity(0.14), radius: 20, y: 8)

    case .ritualTray:
      RoundedRectangle(cornerRadius: max(16, side * 0.14), style: .continuous)
        .fill(Color.Mystic.obsidianElevated.opacity(0.92))
        .overlay {
          RoundedRectangle(cornerRadius: max(16, side * 0.14), style: .continuous)
            .stroke(mountAccent.opacity(0.46), lineWidth: DesignTokens.Borders.hairline)
        }
        .overlay {
          Circle()
            .stroke(mountAccent.opacity(0.24), lineWidth: 1)
            .padding(side * 0.17)
        }
        .shadow(color: Color.black.opacity(0.36), radius: 16, y: 12)
    }
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

  private var mountAccent: Color {
    Color.Mystic.brassGoldPrimary
  }
}
