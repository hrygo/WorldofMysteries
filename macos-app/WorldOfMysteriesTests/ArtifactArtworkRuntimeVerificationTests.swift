import Foundation
import Testing
@testable import WorldOfMysteriesCore

/// 神器 G5 运行时证据采集面的契约测试。
///
/// 抓取脚本（`docs/05_UI/artwork/tools/capture_artifact_runtime_evidence.py`）依赖这里的
/// 窗口标识、偏好键与砖块几何，把截图换算成对比度测量区；这些值一旦静默变化，已提交的
/// 运行时证据就会失真，所以必须在测试里被拦住。
@Suite("Artifact Artwork Runtime Verification Surface")
struct ArtifactArtworkRuntimeVerificationTests {
    @Test("verification window identity and preferences stay addressable by the capture harness")
    func windowIdentityIsStable() {
        #expect(ArtifactArtworkRuntimeVerificationView.windowID == "artifact-artwork-verification")
        #expect(ArtifactArtworkRuntimeVerificationView.windowTitle == "神器美术运行时校验")
        #expect(
            ArtifactArtworkRuntimeVerificationView.taskPreferenceKey
                == "wom.artwork.verification.artifact.task"
        )
        #expect(
            ArtifactArtworkRuntimeVerificationView.modePreferenceKey
                == "wom.artwork.verification.artifact.mode"
        )
        #expect(
            ArtifactArtworkRuntimeVerificationView.contrastPreferenceKey
                == "wom.artwork.verification.artifact.contrast"
        )
        #expect(
            ArtifactArtworkRuntimeVerificationView.transparencyPreferenceKey
                == "wom.artwork.verification.artifact.transparency"
        )
        #expect(
            ArtifactArtworkRuntimeVerificationView.windowSizePreferenceKey
                == "wom.artwork.verification.artifact.windowsize"
        )
        #expect(ArtifactArtworkVerificationMode.allCases.count == 3)
        #expect(ArtifactRegistry.all.count == 15)
    }

    @Test("the capture window takes its size from the harness preference at creation")
    func windowSizeComesFromPreference() throws {
        let view = try source("Artifacts/ArtifactArtworkRuntimeVerificationView.swift")
        let app = try source("MyApp.swift")

        // 本机 Accessibility 的窗口几何不可用，所以几何由采集面自己决定：
        // 采集脚本写偏好 → App 重启 → 采集窗口以该档位创建。
        #expect(view.contains("windowSizePreferenceKey"))
        #expect(view.contains("public static var preferredWindowSize: CGSize"))
        #expect(app.contains("width: ArtifactArtworkRuntimeVerificationView.preferredWindowSize.width"))
        #expect(app.contains("height: ArtifactArtworkRuntimeVerificationView.preferredWindowSize.height"))
        #expect(
            !app.contains(".windowResizability(.contentSize)"),
            "项目守卫要求窗口保留原生缩放"
        )
        #expect(
            !view.contains("NSViewRepresentable"),
            "采集面必须留在原生 SwiftUI 里，不能引入 AppKit 桥接"
        )

        #expect(
            ArtifactArtworkVerificationMetrics.parseWindowSize("1180x760")
                == CGSize(width: 1180, height: 760)
        )
        #expect(ArtifactArtworkVerificationMetrics.parseWindowSize("1280x800") != nil)
        #expect(
            ArtifactArtworkVerificationMetrics.parseWindowSize("") == nil,
            "空偏好必须回落到基线，而不是当成 0×0"
        )
        #expect(ArtifactArtworkVerificationMetrics.parseWindowSize("1180") == nil)
        #expect(ArtifactArtworkVerificationMetrics.parseWindowSize("abcx760") == nil)
    }

    @Test("verification window is reachable from the app scene and the menu")
    func verificationWindowIsWired() throws {
        let app = try source("MyApp.swift")
        let commands = try source("Components/AppMenuBarCommands.swift")

        #expect(app.contains("id: ArtifactArtworkRuntimeVerificationView.windowID"))
        #expect(app.contains("ArtifactArtworkRuntimeVerificationView.windowTitle"))
        #expect(commands.contains("openWindow(id: ArtifactArtworkRuntimeVerificationView.windowID)"))
    }

    @Test("artifacts render every shipped derivative uncropped and unmasked")
    func tilesStayRaw() throws {
        let source = try source("Artifacts/ArtifactArtworkRuntimeVerificationView.swift")
        let tile = try declarationBody(of: "private struct ArtifactVerificationTile:", in: source)

        #expect(source.contains("ArtifactRegistry.all"))
        #expect(source.contains("thumbnailAssetName"))
        #expect(source.contains("detailAssetName"))
        #expect(tile.contains("contentMode: .fit"))
        #expect(!tile.contains("WOMArtworkScrim"), "裁切与遮罩会削弱模板匹配，探针必须留在独立组合里")
        #expect(!tile.contains(".opacity("))
        #expect(!tile.contains("contentMode: .fill"))
        #expect(!tile.contains("clipShape"))
    }

    @Test("showcase probe mirrors the published identity panel composition")
    func showcaseMirrorsIdentityPanel() throws {
        let source = try source("Artifacts/ArtifactArtworkRuntimeVerificationView.swift")
        let showcase = try declarationBody(
            of: "private struct ArtifactVerificationShowcase:",
            in: source
        )

        #expect(showcase.contains("detailAssetName"))
        #expect(showcase.contains(".aspectRatio(1, contentMode: .fit)"))
        #expect(showcase.contains("clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))"))
        #expect(showcase.contains("stroke("))
        #expect(showcase.contains("WOMArtworkScrim(edge: .leading, strength: scrimStrength)"))
    }

    @Test("accessibility states are modelled explicitly instead of claiming a system switch")
    func accessibilityStatesAreModelled() throws {
        let source = try source("Artifacts/ArtifactArtworkRuntimeVerificationView.swift")
        // 反斜杠用码点构造：补丁与 shell 层会重复转义，写死在字面量里不可靠。
        let backslash = String(UnicodeScalar(92))

        #expect(source.contains("private struct ArtifactVerificationReduceTransparencyKey: EnvironmentKey"))
        #expect(source.contains("private struct ArtifactVerificationIncreasedContrastKey: EnvironmentKey"))
        #expect(source.contains("var artifactVerificationReduceTransparency: Bool"))
        #expect(source.contains("var artifactVerificationIncreasedContrast: Bool"))
        #expect(
            source.contains(
                ".environment(\(backslash).artifactVerificationReduceTransparency, reduceTransparency)"
            )
        )
        #expect(
            source.contains(
                ".environment(\(backslash).artifactVerificationIncreasedContrast, increasedContrast)"
            )
        )
        #expect(source.contains("@Environment(\(backslash).accessibilityReduceTransparency)"))
        #expect(source.contains("@Environment(\(backslash).colorSchemeContrast)"))
        #expect(
            source.contains("systemReduceTransparency || transparencyRawValue == \"reduced\""),
            "系统开关打开时必须按打开渲染，采集注入值只作补充"
        )
        #expect(source.contains("systemContrast == .increased || contrastRawValue == \"increased\""))
        #expect(
            !source.contains(".environment(\(backslash).colorSchemeContrast"),
            "colorSchemeContrast 是只读键，不能注入"
        )
        #expect(
            !source.contains(".environment(\(backslash).accessibilityReduceTransparency"),
            "accessibilityReduceTransparency 是只读键，不能注入"
        )
    }

    @Test("tile geometry constants remain the capture contract")
    func tileGeometryConstants() {
        #expect(ArtifactArtworkVerificationMetrics.headerHeight == 44)
        #expect(ArtifactArtworkVerificationMetrics.captionHeight == 18)
        #expect(ArtifactArtworkVerificationMetrics.tileSpacing == 12)
        #expect(ArtifactArtworkVerificationMetrics.contentPadding == 12)
        #expect(ArtifactArtworkVerificationMetrics.minimumTileWidth == 96)
        // 0.12 × 512 px / 2 = 31 点 → 32；0.12 × 1024 px / 2 = 62。
        #expect(ArtifactArtworkVerificationMetrics.thumbnailMatchMinimumTileWidth == 32)
        #expect(ArtifactArtworkVerificationMetrics.detailMatchMinimumTileWidth == 62)
        #expect(ArtifactArtworkVerificationMetrics.tileAspectRatio == 1)
        #expect(ArtifactArtworkVerificationMetrics.showcasePanelHeight == 220)
        #expect(ArtifactArtworkVerificationMetrics.probeLineHeight == 14)
        #expect(ArtifactArtworkVerificationMetrics.probeBodyLineHeight == 16)
        #expect(ArtifactArtworkVerificationMetrics.probeLineSpacing == 2)
        #expect(ArtifactArtworkVerificationMetrics.probeInset == 12)
        #expect(ArtifactArtworkVerificationMetrics.probeOffsetBelowImage == 0)
        #expect(ArtifactArtworkVerificationMetrics.titleBarAllowance == 28)
    }

    /// 采集脚本按同一条算式换算期望缩放：网格可用区域 = 内容区 − 内边距 − 页头 − 间距。
    /// 档位是内容尺寸，标题栏不参与网格几何。
    private func gridArea(for contentSize: CGSize) -> CGSize {
        let metrics = ArtifactArtworkVerificationMetrics.self
        return CGSize(
            width: contentSize.width - metrics.contentPadding * 2,
            height: contentSize.height
                - metrics.contentPadding * 2
                - metrics.headerHeight
                - metrics.tileSpacing
        )
    }

    @Test("locked window sizes: the three collection windows and the detail window")
    func lockedWindowSizes() {
        #expect(
            ArtifactArtworkVerificationMetrics.collectionWindowSizes
                == [
                    CGSize(width: 960, height: 640),
                    CGSize(width: 1180, height: 760),
                    CGSize(width: 1280, height: 800),
                ]
        )
        #expect(ArtifactArtworkVerificationMetrics.detailWindowSize == CGSize(width: 1280, height: 800))
        #expect(ArtifactArtworkVerificationMetrics.showcaseWindowSize == CGSize(width: 1180, height: 760))
    }

    @Test("grid stays above the template-match floor in every locked window")
    func gridFitsLockedWindows() {
        let cases: [(CGSize, CGFloat)] = [
            (CGSize(width: 960, height: 640), ArtifactArtworkVerificationMetrics.thumbnailMatchMinimumTileWidth),
            (CGSize(width: 1180, height: 760), ArtifactArtworkVerificationMetrics.thumbnailMatchMinimumTileWidth),
            (CGSize(width: 1280, height: 800), ArtifactArtworkVerificationMetrics.thumbnailMatchMinimumTileWidth),
            (ArtifactArtworkVerificationMetrics.detailWindowSize, ArtifactArtworkVerificationMetrics.detailMatchMinimumTileWidth),
        ]
        for (size, floor) in cases {
            let available = gridArea(for: size)
            let grid = ArtifactArtworkVerificationMetrics.resolveGrid(
                available: available,
                count: ArtifactRegistry.all.count,
                minimumTileWidth: floor
            )
            let rows = Int(ceil(Double(ArtifactRegistry.all.count) / Double(grid.columns)))
            let occupiedWidth =
                CGFloat(grid.columns) * grid.tileWidth
                + CGFloat(grid.columns - 1) * ArtifactArtworkVerificationMetrics.tileSpacing
            let occupiedHeight =
                CGFloat(rows) * (grid.imageHeight + ArtifactArtworkVerificationMetrics.captionHeight)
                + CGFloat(rows - 1) * ArtifactArtworkVerificationMetrics.tileSpacing
            #expect(
                occupiedWidth <= available.width + 0.5,
                "\(size) 下 \(grid.columns) 列宽 \(occupiedWidth) 超出可用 \(available.width)"
            )
            #expect(
                occupiedHeight <= available.height + 0.5,
                "\(size) 下总高 \(occupiedHeight) 超出可用 \(available.height)"
            )
            #expect(grid.imageHeight >= floor, "\(size) 下砖块小于模板匹配下限 \(floor)")
            #expect(
                grid.imageHeight <= grid.tileWidth,
                "方形派生图按 .fit 渲染时边长取两者的较小值"
            )
        }
    }

    @Test("probe text regions land on the title line and the two important-copy lines")
    func probeTextRegions() {
        let regions = ArtifactArtworkVerificationMetrics.probeTextRegions(panelSide: 220)
        let primary = try? #require(regions["text_primary"])
        let copy = try? #require(regions["important_copy"])

        #expect(primary?.count == 4)
        #expect(copy?.count == 4)
        if let primary, let copy {
            // 坐标以身份面板左上角为原点，单位是抓取像素（2×）。
            #expect(primary[0] == 0)
            #expect(copy[0] == 0)
            #expect(primary[1] == 440, "标题行紧贴 220 点面板下沿")
            #expect(copy[1] == 468, "正文紧接标题行")
            #expect(primary[2] == 440)
            #expect(copy[2] == 440)
            #expect(primary[3] == 28)
            #expect(copy[3] == 64)
            #expect(primary[1] + primary[3] == copy[1])
        }
    }

    @Test("showcase panel side stays square and inside the probe window")
    func showcasePanelSide() {
        let metrics = ArtifactArtworkVerificationMetrics.self
        let available = gridArea(for: metrics.showcaseWindowSize)
        let width = metrics.showcaseWidth(available: available)
        let side = metrics.showcasePanelSide(available: available)

        #expect(width == available.width)
        #expect(side == metrics.showcasePanelHeight)
        #expect(side <= width)
    }

    private func source(_ relativePath: String) throws -> String {
        try String(
            contentsOf: appSourceURL.appendingPathComponent(relativePath),
            encoding: .utf8
        )
    }

    private var appSourceURL: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("WorldOfMysteries", isDirectory: true)
    }

    private func declarationBody(of declaration: String, in source: String) throws -> String {
        let start = try #require(source.range(of: declaration), "missing declaration \(declaration)")
        let remainder = source[start.upperBound...]
        let end = remainder.range(of: "\nprivate struct ") ?? remainder.range(of: "\npublic struct ")

        if let end {
            return String(remainder[..<end.lowerBound])
        }
        return String(remainder)
    }
}
