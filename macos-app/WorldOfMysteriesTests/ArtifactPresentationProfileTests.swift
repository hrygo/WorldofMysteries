import Foundation
import Testing
@testable import WorldOfMysteriesCore

@Suite("Artifact Presentation Profiles")
struct ArtifactPresentationProfileTests {
    @Test("every canonical artifact has one presentation profile")
    func profileCompleteness() {
        let profiles = ArtifactPresentationProfiles.all
        #expect(profiles.count == ArtifactRegistry.all.count)
        #expect(Set(profiles.map(\.artifactID)).count == ArtifactRegistry.all.count)

        for descriptor in ArtifactRegistry.all {
            let profile = ArtifactPresentationProfiles.profile(for: descriptor.id)
            #expect(profile.artifactID == descriptor.id)
            #expect(
                profile.relatedIDs.allSatisfy { relatedID in
                    ArtifactRegistry.all.contains { descriptor in descriptor.id == relatedID }
                }
            )
        }
    }

    @Test("profile relationships stay inside the registry")
    func relatedIDsAreCanonical() {
        let canonicalIDs = Set(ArtifactRegistry.all.map(\.id))
        for profile in ArtifactPresentationProfiles.all {
            #expect(profile.relatedIDs.allSatisfy(canonicalIDs.contains))
        }
    }

    @Test("stage geometry keeps the square mount inside the rectangular stage")
    func stageGeometry() {
        let profile = ArtifactPresentationProfiles.profile(for: .probabilityDie)
        let stageSize = CGSize(width: 960, height: 600)
        let side = ArtifactObjectStageMetrics.mountSide(for: stageSize, profile: profile)
        let anchor = ArtifactObjectStageMetrics.anchorOffset(for: stageSize, anchor: profile.stageAnchor)

        #expect(side > 0)
        #expect(side <= stageSize.width * 0.48)
        #expect(side <= stageSize.height * 0.68)
        #expect(abs(anchor.width) < stageSize.width * 0.05)
        #expect(abs(anchor.height) < stageSize.height * 0.05)
    }

    @Test("pointer parallax is bounded and can be disabled")
    func parallaxBudget() {
        let stageSize = CGSize(width: 800, height: 500)
        let offset = ArtifactObjectStageMetrics.parallaxOffset(
            for: CGPoint(x: 0, y: 500),
            in: stageSize,
            enabled: true
        )

        #expect(abs(offset.width) <= ArtifactObjectStageMetrics.maximumParallax)
        #expect(abs(offset.height) <= ArtifactObjectStageMetrics.maximumParallax)
        #expect(
            ArtifactObjectStageMetrics.parallaxOffset(
                for: CGPoint(x: 400, y: 250), in: stageSize, enabled: false
            ) == .zero
        )
    }

    @Test("stage source declares native 2.5D and accessibility fallbacks")
    func stageAccessibilityContract() throws {
        let source = try file(
            "macos-app/WorldOfMysteries/Artifacts/ArtifactObjectStage.swift"
        )

        #expect(source.contains(".aspectRatio(ArtifactObjectStageMetrics.aspectRatio"))
        #expect(source.contains("contentMode: .fit"))
        #expect(source.contains("onContinuousHover"))
        #expect(source.contains("accessibilityReduceMotion"))
        #expect(source.contains("accessibilityHidden(true)"))
        #expect(source.contains("maximumParallax"))
    }

    private func file(_ relativePath: String) throws -> String {
        try String(
            contentsOf: repositoryRoot.appendingPathComponent(relativePath),
            encoding: .utf8
        )
    }

    private var repositoryRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }
}
