import Foundation
import Testing
@testable import WorldOfMysteriesCore

/// G5 运行时证据采集面的契约测试。
///
/// 抓取脚本（`docs/05_UI/artwork/tools/capture_scene_runtime_evidence.py`）依赖这里的
/// 窗口标识、偏好键与砖块几何，把截图换算成对比度测量区；这些值一旦静默变化，
/// 已提交的运行时证据就会失真，所以必须在测试里被拦住。
@Suite("Scene Artwork Runtime Verification Surface")
struct SceneArtworkRuntimeVerificationTests {
    @Test("verification window identity and preferences stay addressable by the capture harness")
    func windowIdentityIsStable() {
        #expect(SceneArtworkRuntimeVerificationView.windowID == "scene-artwork-verification")
        #expect(SceneArtworkRuntimeVerificationView.windowTitle == "场景美术运行时校验")
        #expect(SceneArtworkRuntimeVerificationView.scenePreferenceKey == "wom.artwork.verification.scene")
        #expect(SceneArtworkRuntimeVerificationView.modePreferenceKey == "wom.artwork.verification.mode")
        #expect(
            SceneArtworkRuntimeVerificationView.variantPreferenceKey
                == "wom.artwork.verification.variant"
        )
        #expect(
            SceneArtworkRuntimeVerificationView.contrastPreferenceKey
                == "wom.artwork.verification.contrast"
        )
        #expect(
            SceneArtworkRuntimeVerificationView.transparencyPreferenceKey
                == "wom.artwork.verification.transparency"
        )
        #expect(SceneArtworkVerificationMode.allCases.count == 3)
        #expect(SceneArtworkVerificationVariant.allCases.count == 2)
    }

    @Test("verification window is reachable from the app scene and the menu")
    func verificationWindowIsWired() throws {
        let app = try source("MyApp.swift")
        let commands = try source("Components/AppMenuBarCommands.swift")

        #expect(app.contains("id: SceneArtworkRuntimeVerificationView.windowID"))
        #expect(app.contains(SceneArtworkRuntimeVerificationView.windowTitle))
        #expect(commands.contains("openWindow(id: SceneArtworkRuntimeVerificationView.windowID)"))
    }

    @Test("grid tiles render every scene runtime asset uncropped and unmasked")
    func gridTilesStayRaw() throws {
        let source = try source("Components/SceneArtworkRuntimeVerificationView.swift")
        let tile = try declarationBody(of: "private struct SceneArtworkVerificationTile:", in: source)

        #expect(source.contains("WOMWorldArtworkAsset.allCases"))
        #expect(tile.contains("asset.runtimeAssetName"))
        #expect(tile.contains("contentMode: .fit"))
        #expect(!tile.contains("WOMArtworkScrim"), "裁切与遮罩会削弱模板匹配，探针必须留在独立砖块")
        #expect(!tile.contains(".opacity("))
        #expect(!tile.contains("contentMode: .fill"))
    }

    @Test("probe tiles anchor the composed overlay under an uncropped wide image")
    func probeTilesAnchorUnderWideImage() throws {
        let source = try source("Components/SceneArtworkRuntimeVerificationView.swift")
        let tile = try declarationBody(of: "private struct SceneArtworkVerificationProbeTile:", in: source)
        let probe = try declarationBody(of: "private struct SceneArtworkVerificationProbe:", in: source)

        let imageFirst = try #require(tile.range(of: "asset.wideHeaderAssetName"))
        let probeSecond = try #require(tile.range(of: "SceneArtworkVerificationProbe("))
        #expect(
            imageFirst.lowerBound < probeSecond.lowerBound,
            "抓取脚本按「原图在上、探针在下」反推对比度测量区"
        )
        #expect(tile.contains("contentMode: .fit"))

        #expect(
            probe.contains("WOMArtworkScrim(edge: .leading, strength: scrimStrength)"),
            "标准态沿用产品 header 的 0.92，辅助功能态走各自的不透明度规则"
        )
        #expect(probe.contains("variant.assetName(for: asset)"))
    }

    @Test("accessibility states are modelled explicitly instead of claiming a system switch")
    func accessibilityStatesAreModelled() throws {
        let source = try source("Components/SceneArtworkRuntimeVerificationView.swift")
        // 反斜杠用码点构造：补丁与 shell 层会重复转义，写死在字面量里不可靠。
        let backslash = String(UnicodeScalar(92))

        #expect(source.contains("private struct SceneArtworkReduceTransparencyKey: EnvironmentKey"))
        #expect(source.contains("private struct SceneArtworkIncreasedContrastKey: EnvironmentKey"))
        #expect(source.contains("var sceneArtworkReduceTransparency: Bool"))
        #expect(source.contains("var sceneArtworkIncreasedContrast: Bool"))
        #expect(
            source.contains(
                ".environment(\(backslash).sceneArtworkReduceTransparency, reduceTransparency)"
            )
        )
        #expect(
            source.contains(
                ".environment(\(backslash).sceneArtworkIncreasedContrast, increasedContrast)"
            )
        )
        #expect(
            source.contains("@Environment(\(backslash).accessibilityReduceTransparency)")
        )
        #expect(source.contains("@Environment(\(backslash).colorSchemeContrast)"))
        #expect(
            source.contains("systemReduceTransparency || transparencyRawValue == \"reduced\""),
            "系统开关打开时必须按打开渲染，采集注入值只作补充"
        )
        #expect(
            source.contains("systemContrast == .increased || contrastRawValue == \"increased\"")
        )
        #expect(
            source.contains("guard injectedContrast, systemContrast != .increased else { return base }"),
            "系统已经收紧时不能重复叠加 0.12"
        )
        #expect(
            !source.contains(".environment(\(backslash).colorSchemeContrast"),
            "colorSchemeContrast 是只读键，不能注入"
        )
        #expect(
            !source.contains(".environment(\(backslash).accessibilityReduceTransparency"),
            "accessibilityReduceTransparency 是只读键，不能注入"
        )
        #expect(
            SceneArtworkRuntimeVerificationView.transparencyPreferenceKey
                == "wom.artwork.verification.transparency"
        )
    }

    @Test("focus mode keeps native point sizes aligned with derivative pixels at 2x")
    func focusModeUsesNativePointSizes() {
        #expect(SceneArtworkVerificationVariant.runtime.nativePointSize == CGSize(width: 1280, height: 800))
        #expect(SceneArtworkVerificationVariant.wide.nativePointSize == CGSize(width: 1200, height: 450))
        #expect(SceneArtworkVerificationVariant.runtime.pixelSizeDescription == "2560×1600")
        #expect(SceneArtworkVerificationVariant.wide.pixelSizeDescription == "2400×900")

        #expect(
            SceneArtworkVerificationMetrics.focusWindowSize(for: .runtime)
                == CGSize(width: 1304, height: 852)
        )
        #expect(
            SceneArtworkVerificationMetrics.focusWindowSize(for: .wide)
                == CGSize(width: 1224, height: 502)
        )

        for asset in WOMWorldArtworkAsset.allCases {
            #expect(
                SceneArtworkVerificationVariant.runtime.assetName(for: asset) == asset.runtimeAssetName
            )
            #expect(
                SceneArtworkVerificationVariant.wide.assetName(for: asset) == asset.wideHeaderAssetName
            )
        }
    }

    @Test("tile geometry constants remain the capture contract")
    func tileGeometryConstants() {
        #expect(SceneArtworkVerificationMetrics.probeHeight == 72)
        #expect(SceneArtworkVerificationMetrics.captionHeight == 18)
        #expect(SceneArtworkVerificationMetrics.tileSpacing == 12)
        #expect(SceneArtworkVerificationMetrics.headerHeight == 44)
        #expect(SceneArtworkVerificationMetrics.probeInset == 12)
        #expect(SceneArtworkVerificationMetrics.probeLineHeight == 14)
        #expect(SceneArtworkVerificationMetrics.probeLineSpacing == 2)
        #expect(SceneArtworkVerificationMetrics.templateMatchMinimumTileWidth == 154)
        #expect(SceneArtworkVerificationMetrics.tileAspectRatio == 1.6)
        #expect(abs(SceneArtworkVerificationMetrics.wideAspectRatio - 2400.0 / 900.0) < 1e-9)
        #expect(SceneArtworkVerificationMetrics.probeOffsetBelowImage == 0)
    }

    @Test("probe text regions land on the title line and the two important-copy lines")
    func probeTextRegions() {
        let regions = SceneArtworkVerificationMetrics.probeTextRegions(probeWidth: 300)

        #expect(regions.primary == CGRect(x: 12, y: 16, width: 276, height: 14))
        #expect(regions.importantCopy == CGRect(x: 12, y: 32, width: 276, height: 28))
    }

    @Test("grid layout fits the locked window geometries with matchable tiles")
    func gridFitsLockedWindowGeometries() {
        // 窗口点数扣掉标题栏与采集面内边距后的可用内容区。
        let lockedContentSizes = [
            CGSize(width: 936, height: 588),   // 960×640 最小运行时窗口
            CGSize(width: 1156, height: 708),  // 1180×760 默认运行时布局
            CGSize(width: 1256, height: 748),  // 1280×800 → 2× 背屏 2560×1600 px 抓取
            CGSize(width: 1176, height: 398),  // 1200×450 → 2× 背屏 2400×900 px 抓取
        ]

        for size in lockedContentSizes {
            let metrics = SceneArtworkVerificationMetrics.resolveGrid(
                available: size,
                count: WOMWorldArtworkAsset.allCases.count
            )

            #expect(
                metrics.tileWidth >= SceneArtworkVerificationMetrics.templateMatchMinimumTileWidth,
                "\(Int(size.width))×\(Int(size.height)) 里砖块只有 \(metrics.tileWidth) 点，模板匹配会失效"
            )
            #expect(
                metrics.requiredHeight(count: WOMWorldArtworkAsset.allCases.count) <= size.height,
                "\(Int(size.width))×\(Int(size.height)) 放不下六个场景砖块"
            )
        }
    }

    @Test("probe layout fits the windows used for contrast and accessibility captures")
    func probeLayoutFitsProbeCaptureWindows() {
        let probeContentSizes = [
            CGSize(width: 1156, height: 708),  // 1180×760：对比度与辅助功能抓取窗口
            CGSize(width: 1256, height: 748),  // 1280×800
        ]

        for size in probeContentSizes {
            let metrics = SceneArtworkVerificationMetrics.resolveProbeGrid(
                available: size,
                count: WOMWorldArtworkAsset.allCases.count
            )

            #expect(metrics.showsProbe)
            #expect(!metrics.showsCaption)
            #expect(
                metrics.tileWidth >= SceneArtworkVerificationMetrics.templateMatchMinimumTileWidth
            )
            #expect(
                metrics.requiredHeight(count: WOMWorldArtworkAsset.allCases.count) <= size.height
            )
        }
    }

    // MARK: - Source helpers

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

    /// 截取一段声明主体，用于断言「这个砖块里没有 scrim」这类结构性事实。
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
