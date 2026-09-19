import SwiftUI

/// 神器的 G5 运行时采集面。
///
/// 为什么单独开窗口：产品表面（`ArtifactShowcaseView` 的选择行 28×28、身份面板的圆角裁切与
/// 描边）都不是「整张派生图按 1:1 呈现」，无法用模板匹配证明**出厂的派生图确实被渲染出来**。
/// 这里以未裁切、无遮罩的方式呈现 15 件神器的 thumbnail / detail 派生图，让
/// `docs/05_UI/artwork/tools/finish_world_artwork.py surface` 的归一化互相关与
/// `record` 的对比度复算都有可复算的像素依据；发布态观感仍由产品表面承担。
///
/// `showcase` 模式复刻 `ArtifactUIPrimitivesCore.identityPanel` 的发布态组合（detail 原图
/// `.fit` + 圆角裁切 + 强调色描边 + 徽记/名称/正文），用于文本对比度与辅助功能状态取证。
///
/// 单实例：采集脚本按 App 包内可执行路径在启动前后都断言只有一个进程，见
/// `docs/05_UI/artwork/tools/capture_artifact_runtime_evidence.py`。
public enum ArtifactArtworkVerificationMode: String, CaseIterable, Sendable {
    /// 15 张 thumbnail（512×512）未裁切原图。
    case collection
    /// 15 张 detail（1024×1024）未裁切原图。
    case detail
    /// 发布态身份面板组合探针（单件）。
    case showcase
}

private struct ArtifactVerificationReduceTransparencyKey: EnvironmentKey {
    /// 采集面本地的「降低透明度」渲染开关。
    ///
    /// 本机 `defaults write com.apple.universalaccess` 被系统拒绝，系统开关无法被自动化切换；
    /// 而产品遮罩 `WOMArtworkScrim` 是显式 `Color.opacity` 渐变、不是系统 `Material`，
    /// 系统开关对它本来就不产生渲染差异。这里显式建模该状态：系统开关打开或采集脚本注入
    /// 同名偏好时，发布态探针改用更高的不透明度下限，采集据此证明「更少透明」这条渲染路径
    /// 下文本区仍然达标——而不是声称等于改动了系统开关。
    static let defaultValue = false
}

private struct ArtifactVerificationIncreasedContrastKey: EnvironmentKey {
    /// 采集面本地的「增强对比度」渲染开关（同 `WOMArtworkScrim.effectiveStrength` 的 +0.12 规则）。
    static let defaultValue = false
}

extension EnvironmentValues {
    var artifactVerificationReduceTransparency: Bool {
        get { self[ArtifactVerificationReduceTransparencyKey.self] }
        set { self[ArtifactVerificationReduceTransparencyKey.self] = newValue }
    }

    var artifactVerificationIncreasedContrast: Bool {
        get { self[ArtifactVerificationIncreasedContrastKey.self] }
        set { self[ArtifactVerificationIncreasedContrastKey.self] = newValue }
    }
}

/// 采集面几何契约：采集脚本从本文件的字面量解析这些值，Swift 侧静默改动会立刻报错。
/// 采集窗口按 `windowSizePreferenceKey` 把自己钉成锁定内容尺寸（场景侧 `.windowResizability(.contentSize)`）。
public enum ArtifactArtworkVerificationMetrics {
    /// 页头预算高度（点）。
    public static let headerHeight: CGFloat = 44
    /// 砖块标签高度（点）。
    public static let captionHeight: CGFloat = 18
    /// 砖块间距（点）。
    public static let tileSpacing: CGFloat = 12
    /// 内容内边距（点）。
    public static let contentPadding: CGFloat = 12
    /// 砖块最小可用宽度（点）：低于该宽度时标签与正文不再可信。
    public static let minimumTileWidth: CGFloat = 96
    /// thumbnail 的模板匹配下限（点）：`surface --min-scale 0.12` × 512 px = 62 设备像素，
    /// 2× 背屏即 31 点，向上取整到 32。
    public static let thumbnailMatchMinimumTileWidth: CGFloat = 32
    /// detail 的模板匹配下限（点）：0.12 × 1024 = 123 设备像素，2× 背屏即 62 点。
    public static let detailMatchMinimumTileWidth: CGFloat = 62
    /// 神器派生图是 1:1 方形。
    public static let tileAspectRatio: CGFloat = 1
    /// 发布态探针里身份面板的最大高度（点），与 `ArtifactUIPrimitivesCore.identityPanel` 一致。
    public static let showcasePanelHeight: CGFloat = 220
    /// 探针文本行高（点）。
    public static let probeLineHeight: CGFloat = 14
    /// 探针正文每行的高度（点）。`Font.Mystic.caption` 是 11pt，行盒约 13.1pt，取 16 留出行距。
    public static let probeBodyLineHeight: CGFloat = 16
    /// 探针文本行距（点）。
    public static let probeLineSpacing: CGFloat = 2
    /// 探针内边距（点）。
    public static let probeInset: CGFloat = 12
    /// 探针里原图与文本块之间的间距（点）。
    public static let probeOffsetBelowImage: CGFloat = 0
    /// 窗口标题栏预算（点）。
    public static let titleBarAllowance: CGFloat = 28

    /// 解析 `"1180x760"`；非法值返回 nil，由调用方回落到基线尺寸而不是悄悄换档。
    public static func parseWindowSize(_ text: String) -> CGSize? {
        let parts = text.split(separator: "x")
        guard
            parts.count == 2,
            let width = Double(parts[0]),
            let height = Double(parts[1]),
            width >= 320,
            height >= 240
        else {
            return nil
        }
        return CGSize(width: width, height: height)
    }

    /// 采集窗口（点）→ 抓取像素：2× 背屏下后两项正好是 2560×1600。
    public static let collectionWindowSizes: [CGSize] = [
        CGSize(width: 960, height: 640),
        CGSize(width: 1180, height: 760),
        CGSize(width: 1280, height: 800),
    ]
    public static let detailWindowSize = CGSize(width: 1280, height: 800)
    public static let showcaseWindowSize = CGSize(width: 1180, height: 760)

    public struct Grid: Equatable, Sendable {
        public let columns: Int
        public let tileWidth: CGFloat
        public let imageHeight: CGFloat
    }

    /// 按网格自己的可用区域与最小匹配下限解出列数（5 → 4 → 1），宁可少列也不让砖块小到无法自证。
    ///
    /// `available` 已经是网格自身能用的区域：调用方的 `GeometryReader` 位于 `.padding` 与页头
    /// 之后，所以这里**只**再扣砖块间距与标签高度。采集脚本按同样的算式复算砖宽与渲染尺寸，
    /// 任何一侧的静默改动都会让模板匹配的期望缩放失配并在这里之外的采集步骤报错。
    public static func resolveGrid(
        available: CGSize,
        count: Int,
        minimumTileWidth: CGFloat
    ) -> Grid {
        for columns in [5, 4, 1] where columns <= max(count, 1) {
            let rows = Int(ceil(Double(count) / Double(columns)))
            let tileWidth =
                (available.width - tileSpacing * CGFloat(columns - 1)) / CGFloat(columns)
            let rowHeight =
                (available.height - tileSpacing * CGFloat(rows - 1)) / CGFloat(rows)
            let imageHeight = min(tileWidth, rowHeight - captionHeight)
            if imageHeight >= minimumTileWidth && tileWidth >= minimumTileWidth {
                return Grid(columns: columns, tileWidth: tileWidth, imageHeight: imageHeight)
            }
        }
        let fallback = max(minimumTileWidth, 1)
        return Grid(columns: 1, tileWidth: fallback, imageHeight: fallback)
    }

    /// 探针带宽（点）：抓取脚本用它把 2× 像素换算回点位。
    public static func showcaseWidth(available: CGSize) -> CGFloat {
        max(available.width, 1)
    }

    /// 探针里身份面板的边长（点）：正方形派生图，`ArtifactUIPrimitivesCore.identityPanel` 的上限是 220。
    public static func showcasePanelSide(available: CGSize) -> CGFloat {
        min(showcasePanelHeight, showcaseWidth(available: available))
    }

    /// 抓取脚本按「原图在上、文本块在下」的顺序反推对比度测量区。
    ///
    /// 返回的坐标以**身份面板左上角**为原点（点）。面板是正方形，文本块紧贴面板下沿、
    /// 左对齐、等宽，所以抓取脚本只需把归一化互相关给出的原图框左上角当作原点即可换算。
    public static func probeTextRegions(
        panelSide: CGFloat
    ) -> [String: [Int]] {
        let blockTop = panelSide + probeOffsetBelowImage

        func region(x: CGFloat, y: CGFloat, width: CGFloat, height: CGFloat) -> [Int] {
            [
                Int((x * 2).rounded()),
                Int((y * 2).rounded()),
                Int((width * 2).rounded()),
                Int((height * 2).rounded()),
            ]
        }

        return [
            "text_primary": region(
                x: 0, y: blockTop, width: panelSide, height: probeLineHeight
            ),
            "important_copy": region(
                x: 0,
                y: blockTop + probeLineHeight,
                width: panelSide,
                height: probeBodyLineHeight * 2
            ),
        ]
    }
}

public struct ArtifactArtworkRuntimeVerificationView: View {
    public static let windowID = "artifact-artwork-verification"
    public static let windowTitle = "神器美术运行时校验"
    public static let taskPreferenceKey = "wom.artwork.verification.artifact.task"
    public static let modePreferenceKey = "wom.artwork.verification.artifact.mode"
    public static let contrastPreferenceKey = "wom.artwork.verification.artifact.contrast"
    public static let transparencyPreferenceKey = "wom.artwork.verification.artifact.transparency"

    /// 采集窗口尺寸偏好（`"宽x高"`，点，窗口边框含标题栏）。
    ///
    /// 为什么由采集面自己决定几何：本机 Accessibility 的窗口属性不可用——`kAXWindowsAttribute`
    /// 返回的是 App 代理元素，`AXSize` 报 `-25205`（attribute unsupported），System Events 对
    /// 任何进程都读不到窗口，脚本摆不了窗口。采集脚本按档位写入这个键、清掉系统保存的窗口
    /// 边框记录并重启 App，窗口就在创建时落在该档位（见 `preferredWindowSize`）。实测
    /// （2026-09-19）`.defaultSize` 设定的是窗口边框尺寸，与 `screencapture -l` 的像素正好是
    /// 「档位 × 背屏倍率」；窗口仍是原生可缩放窗口，不锁定缩放。
    public static let windowSizePreferenceKey = "wom.artwork.verification.artifact.windowsize"

    /// 采集窗口的初始尺寸：偏好缺省时回落到采集窗口基线，不猜别的档位。
    public static var preferredWindowSize: CGSize {
        let stored = UserDefaults.standard.string(forKey: windowSizePreferenceKey) ?? ""
        return ArtifactArtworkVerificationMetrics.parseWindowSize(stored)
            ?? ArtifactArtworkVerificationMetrics.showcaseWindowSize
    }

    /// 系统里真实生效的辅助功能设置：注入值只做补充，系统开关打开时以系统值为准。
    @Environment(\.accessibilityReduceTransparency) private var systemReduceTransparency
    @Environment(\.colorSchemeContrast) private var systemContrast

    @AppStorage(ArtifactArtworkRuntimeVerificationView.taskPreferenceKey)
    private var taskRawValue = ArtifactRegistry.all.first?.id.rawValue ?? ""
    @AppStorage(ArtifactArtworkRuntimeVerificationView.modePreferenceKey)
    private var modeRawValue = ArtifactArtworkVerificationMode.collection.rawValue
    @AppStorage(ArtifactArtworkRuntimeVerificationView.contrastPreferenceKey)
    private var contrastRawValue = "standard"
    @AppStorage(ArtifactArtworkRuntimeVerificationView.transparencyPreferenceKey)
    private var transparencyRawValue = "standard"

    public init() {}

    public var body: some View {
        VStack(alignment: .leading, spacing: ArtifactArtworkVerificationMetrics.tileSpacing) {
            header

            switch mode {
            case .collection:
                gridSurface(asset: \.thumbnailAssetName, suffix: "thumbnail 512×512",
                            minimumTileWidth: ArtifactArtworkVerificationMetrics.thumbnailMatchMinimumTileWidth)
            case .detail:
                gridSurface(asset: \.detailAssetName, suffix: "detail 1024×1024",
                            minimumTileWidth: ArtifactArtworkVerificationMetrics.detailMatchMinimumTileWidth)
            case .showcase:
                showcaseSurface
            }
        }
        .padding(ArtifactArtworkVerificationMetrics.contentPadding)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(WOMWindowCanvas())
        .environment(\.artifactVerificationIncreasedContrast, increasedContrast)
        .environment(\.artifactVerificationReduceTransparency, reduceTransparency)
        .preferredColorScheme(.dark)
    }

    private var mode: ArtifactArtworkVerificationMode {
        ArtifactArtworkVerificationMode(rawValue: modeRawValue) ?? .collection
    }

    private var focusedDescriptor: ArtifactDescriptor {
        ArtifactRegistry.all.first { $0.id.rawValue == taskRawValue }
            ?? ArtifactRegistry.all[0]
    }

    private var reduceTransparency: Bool {
        systemReduceTransparency || transparencyRawValue == "reduced"
    }

    private var increasedContrast: Bool {
        systemContrast == .increased || contrastRawValue == "increased"
    }

    /// 抓取图上必须能读到「这个状态是系统给的还是采集注入的」。
    private func stateWord(_ active: Bool, injected: Bool, system: Bool) -> String {
        guard active else { return "关" }
        return "开（系统\(system ? "开" : "关")·注入\(injected ? "开" : "关")）"
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
            Text("神器美术运行时校验 · G5 采集面")
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.brassGoldPrimary)

            Text(
                "未裁切 · 无遮罩渲染，模板匹配与对比度都从这些像素复算；"
                    + "模式\(mode.rawValue) · 共\(ArtifactRegistry.all.count)件；"
                    + "辅助功能状态：增强对比度\(stateWord(increasedContrast, injected: contrastRawValue == "increased", system: systemContrast == .increased))"
                    + " · 降低透明度\(stateWord(reduceTransparency, injected: transparencyRawValue == "reduced", system: systemReduceTransparency))"
            )
            .font(Font.Mystic.caption)
            .foregroundStyle(Color.Mystic.textSecondary)
            .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func gridSurface(
        asset: KeyPath<WOMArtifactArtworkAsset, String>,
        suffix: String,
        minimumTileWidth: CGFloat
    ) -> some View {
        GeometryReader { proxy in
            let metrics = ArtifactArtworkVerificationMetrics.resolveGrid(
                available: proxy.size,
                count: ArtifactRegistry.all.count,
                minimumTileWidth: minimumTileWidth
            )

            LazyVGrid(
                columns: Array(
                    repeating: GridItem(
                        .fixed(metrics.tileWidth),
                        spacing: ArtifactArtworkVerificationMetrics.tileSpacing
                    ),
                    count: metrics.columns
                ),
                alignment: .leading,
                spacing: ArtifactArtworkVerificationMetrics.tileSpacing
            ) {
                ForEach(ArtifactRegistry.all) { descriptor in
                    ArtifactVerificationTile(
                        descriptor: descriptor,
                        assetName: descriptor.id.artworkAsset[keyPath: asset],
                        suffix: suffix,
                        metrics: metrics
                    )
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }

    private var showcaseSurface: some View {
        GeometryReader { proxy in
            ArtifactVerificationShowcase(
                descriptor: focusedDescriptor,
                width: ArtifactArtworkVerificationMetrics.showcaseWidth(available: proxy.size),
                panelSide: ArtifactArtworkVerificationMetrics.showcasePanelSide(
                    available: proxy.size
                )
            )
        }
    }
}

/// 未裁切的派生图砖块：模板匹配的比对基准，任何遮罩或透明度都会削弱它。
/// 未裁切的派生图砖块：模板匹配的比对基准，任何遮罩或透明度都会削弱它。
private struct ArtifactVerificationTile: View {
    let descriptor: ArtifactDescriptor
    let assetName: String
    let suffix: String
    let metrics: ArtifactArtworkVerificationMetrics.Grid

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            WOMArtworkView(
                assetName: assetName,
                fallback: .systemImage(descriptor.systemIcon),
                contentMode: .fit
            )
            .frame(width: metrics.tileWidth, height: metrics.imageHeight)
            .accessibilityIdentifier("wom.artwork.verification.artifact.\(descriptor.id.rawValue)")

            Text("\(descriptor.id.rawValue) · \(suffix)")
                .font(Font.Mystic.monoBadge)
                .foregroundStyle(Color.Mystic.textSecondary)
                .lineLimit(1)
                .frame(height: ArtifactArtworkVerificationMetrics.captionHeight, alignment: .leading)
        }
        .frame(width: metrics.tileWidth, alignment: .leading)
    }
}

/// 发布态身份面板探针：复刻 `ArtifactUIPrimitivesCore.identityPanel` 的组合语义。
private struct ArtifactVerificationShowcase: View {
    let descriptor: ArtifactDescriptor
    let width: CGFloat
    let panelSide: CGFloat

    @Environment(\.artifactVerificationReduceTransparency) private var reduceTransparency
    @Environment(\.artifactVerificationIncreasedContrast) private var injectedContrast
    @Environment(\.colorSchemeContrast) private var systemContrast

    /// 与 `WOMArtworkScrim.effectiveStrength` 同一条规则：增强对比度把叠加层收紧 0.12。
    private var scrimStrength: Double {
        let base = reduceTransparency ? 1 : 0.92
        guard injectedContrast, systemContrast != .increased else { return base }
        return min(1, base + 0.12)
    }

    var body: some View {
        // 文本块紧贴面板下沿、每行高度显式：抓取脚本按「面板边长 + 行高」换算对比度测量区，
        // 不使用字体固有行高，否则 Swift 侧的排版微调会让测量区悄悄落到别处。
        VStack(alignment: .leading, spacing: 0) {
            ZStack(alignment: .bottomLeading) {
                WOMArtworkView(
                    assetName: descriptor.id.artworkAsset.detailAssetName,
                    fallback: .systemImage(descriptor.systemIcon),
                    fallbackTint: descriptor.tone.accent,
                    contentMode: .fit,
                    accessibilityLabel: descriptor.displayName
                )
                .aspectRatio(1, contentMode: .fit)
                .frame(width: panelSide, height: panelSide)
                .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.md))
                .overlay {
                    RoundedRectangle(cornerRadius: DesignTokens.Radii.md)
                        .stroke(
                            descriptor.tone.accent.opacity(0.24),
                            lineWidth: DesignTokens.Borders.hairline
                        )
                }
                .accessibilityIdentifier(
                    "wom.artwork.verification.artifact.showcase.\(descriptor.id.rawValue)"
                )

                WOMArtworkScrim(edge: .leading, strength: scrimStrength)
                    .frame(
                        width: panelSide,
                        height: ArtifactArtworkVerificationMetrics.probeLineHeight * 3
                            + ArtifactArtworkVerificationMetrics.probeInset * 2
                    )
            }
            .frame(width: panelSide, height: panelSide, alignment: .bottomLeading)

            Text("\(descriptor.displayName) · \(descriptor.subtitle)")
                .mysticTitleStyle(font: Font.Mystic.caption)
                .lineLimit(1)
                .frame(
                    width: panelSide,
                    height: ArtifactArtworkVerificationMetrics.probeLineHeight,
                    alignment: .leading
                )

            Text(descriptor.family.localizedTitle + " · " + descriptor.canonClass.localizedTitle)
                .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                .lineLimit(1)
                .frame(
                    width: panelSide,
                    height: ArtifactArtworkVerificationMetrics.probeBodyLineHeight,
                    alignment: .leading
                )

            Text("可读性探针：与身份面板同语义的发布态组合")
                .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                .lineLimit(1)
                .frame(
                    width: panelSide,
                    height: ArtifactArtworkVerificationMetrics.probeBodyLineHeight,
                    alignment: .leading
                )
        }
        .frame(width: width, alignment: .leading)
    }
}

#Preview("Artifact Artwork Runtime Verification") {
    ArtifactArtworkRuntimeVerificationView()
        .frame(width: 1180, height: 760)
}
