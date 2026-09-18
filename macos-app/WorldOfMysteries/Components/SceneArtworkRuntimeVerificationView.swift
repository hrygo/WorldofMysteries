import SwiftUI

/// 场景运行时美术校验的呈现模式。
///
/// 三种模式各自承担一类 G5 运行时证据，互不替代：
/// - `grid`：六个场景族的 runtime 派生图未裁切同屏，证明出厂资产确实被渲染；
/// - `probe`：runtime 原图 + 发布态叠加探针（wide 派生图 + 前导 scrim + 文本），复算文本对比度；
/// - `focus`：单场景派生图按原生点尺寸呈现，2× 背屏抓取下与派生图像素 1:1。
public nonisolated enum SceneArtworkVerificationMode: String, CaseIterable, Sendable {
    case grid
    case probe
    case focus
}

/// `focus` 模式下呈现的派生图变体。
public nonisolated enum SceneArtworkVerificationVariant: String, CaseIterable, Sendable {
    case runtime
    case wide

    /// 原生点尺寸：2× 背屏抓取下与派生图像素一一对应。
    public var nativePointSize: CGSize {
        switch self {
        case .runtime: CGSize(width: 1280, height: 800)
        case .wide: CGSize(width: 1200, height: 450)
        }
    }

    /// 派生图像素尺寸描述，用于采集面自证标签。
    public var pixelSizeDescription: String {
        switch self {
        case .runtime: "2560×1600"
        case .wide: "2400×900"
        }
    }

    public func assetName(for asset: WOMWorldArtworkAsset) -> String {
        switch self {
        case .runtime: asset.runtimeAssetName
        case .wide: asset.wideHeaderAssetName
        }
    }
}

/// 采集面的砖块几何。
///
/// 这里暴露的常量同时是**采集契约**：抓取脚本依赖它们把模板匹配结果换算成对比度测量区域，
/// 因此静默改动会让已提交的运行时证据失真（`SceneArtworkRuntimeVerificationTests` 会拦住改动）。
public nonisolated struct SceneArtworkVerificationMetrics: Sendable {
    /// 发布态叠加探针高度（点）。
    public static let probeHeight: CGFloat = 72
    /// 身份标签高度（点）。
    public static let captionHeight: CGFloat = 18
    /// 砖块间距（点）。
    public static let tileSpacing: CGFloat = 12
    /// 页头预算高度（点）。
    public static let headerHeight: CGFloat = 44
    /// 探针内边距（点）。
    public static let probeInset: CGFloat = 12
    /// 探针文本行高（点）。
    public static let probeLineHeight: CGFloat = 14
    /// 探针文本行距（点）。
    public static let probeLineSpacing: CGFloat = 2
    /// 砖块最小可用宽度（点）：低于该宽度时标签与正文不再可信。
    public static let minimumTileWidth: CGFloat = 96
    /// 模板匹配下限（点）：`finish_world_artwork.py surface` 的 `--min-scale` 是 0.12，
    /// 2560 px 宽的 runtime 派生图至少要占 2560×0.12 = 307 设备像素，2× 背屏即 154 点。
    /// 低于该宽度的砖块无法承担「资产确实被渲染」的证明。
    public static let templateMatchMinimumTileWidth: CGFloat = 154
    /// 场景派生图为 16:10。
    public static let tileAspectRatio: CGFloat = 16.0 / 10.0
    /// wide 派生图为 2400×900（8:3），探针砖块用它的原图验证 wide 资产确实被渲染。
    public static let wideAspectRatio: CGFloat = 2400.0 / 900.0
    /// 采集面内容内边距（点）。
    public static let contentPadding: CGFloat = 12
    /// 窗口标题栏预算（点）：`focus` 窗口要按原生尺寸留出这段高度。
    public static let titleBarAllowance: CGFloat = 28

    public let columns: Int
    public let tileWidth: CGFloat
    public let imageHeight: CGFloat
    /// 砖块是否包含发布态叠加探针。
    public let showsProbe: Bool
    /// 砖块是否包含身份标签。
    public let showsCaption: Bool

    public init(
        columns: Int,
        tileWidth: CGFloat,
        imageHeight: CGFloat,
        showsProbe: Bool,
        showsCaption: Bool
    ) {
        self.columns = columns
        self.tileWidth = tileWidth
        self.imageHeight = imageHeight
        self.showsProbe = showsProbe
        self.showsCaption = showsCaption
    }

    public func rows(count: Int) -> Int {
        guard columns > 0 else { return count }
        return Int((Double(count) / Double(columns)).rounded(.up))
    }

    public var tileHeight: CGFloat {
        imageHeight
            + (showsProbe ? Self.probeHeight : 0)
            + (showsCaption ? Self.captionHeight : 0)
    }

    public func requiredHeight(count: Int) -> CGFloat {
        let rowCount = CGFloat(rows(count: count))
        return Self.headerHeight
            + rowCount * tileHeight
            + max(rowCount - 1, 0) * Self.tileSpacing
            + Self.tileSpacing
    }

    /// grid 模式：砖块是未裁切的 16:10 runtime 原图 + 身份标签。
    public static func resolveGrid(
        available: CGSize,
        count: Int,
        preferredColumns: [Int] = [3, 2, 6, 1]
    ) -> SceneArtworkVerificationMetrics {
        resolve(
            available: available,
            count: count,
            preferredColumns: preferredColumns,
            showsProbe: false,
            showsCaption: true,
            minimumWidth: templateMatchMinimumTileWidth
        ) { width in
            (width / tileAspectRatio).rounded()
        }
    }

    /// probe 模式：砖块是未裁切的 wide 原图 + 发布态叠加探针（探针自带文字，不再重复标签）。
    ///
    /// 这样两处都服务于同一件事：grid 抓取证明 runtime 派生图被渲染，probe 抓取证明 wide 派生图
    /// 被渲染，同时给出发布态叠加文本的对比度测量区。
    public static func resolveProbeGrid(
        available: CGSize,
        count: Int,
        preferredColumns: [Int] = [3, 2, 6, 1]
    ) -> SceneArtworkVerificationMetrics {
        resolve(
            available: available,
            count: count,
            preferredColumns: preferredColumns,
            showsProbe: true,
            showsCaption: false,
            minimumWidth: templateMatchMinimumTileWidth
        ) { width in
            (width / wideAspectRatio).rounded()
        }
    }

    /// 在给定可用空间里挑列数：优先少列大砖，都放不下时退回所需高度最小的候选。
    private static func resolve(
        available: CGSize,
        count: Int,
        preferredColumns: [Int],
        showsProbe: Bool,
        showsCaption: Bool,
        minimumWidth: CGFloat,
        imageHeightFor: (CGFloat) -> CGFloat
    ) -> SceneArtworkVerificationMetrics {
        let candidates = preferredColumns.compactMap { columns -> SceneArtworkVerificationMetrics? in
            guard columns > 0 else { return nil }
            let width = (available.width - tileSpacing * CGFloat(columns - 1)) / CGFloat(columns)
            guard width >= minimumWidth else { return nil }
            return SceneArtworkVerificationMetrics(
                columns: columns,
                tileWidth: width,
                imageHeight: imageHeightFor(width),
                showsProbe: showsProbe,
                showsCaption: showsCaption
            )
        }

        if let fitting = candidates.first(where: { $0.requiredHeight(count: count) <= available.height }) {
            return fitting
        }

        return candidates.min { $0.requiredHeight(count: count) < $1.requiredHeight(count: count) }
            ?? SceneArtworkVerificationMetrics(
                columns: 1,
                tileWidth: max(available.width, minimumWidth),
                imageHeight: max((available.width / tileAspectRatio).rounded(), 1),
                showsProbe: showsProbe,
                showsCaption: showsCaption
            )
    }

    /// `focus` 模式窗口尺寸：原生点尺寸加上内边距与标题栏，保证派生图 1:1 完整可见。
    public static func focusWindowSize(
        for variant: SceneArtworkVerificationVariant
    ) -> CGSize {
        CGSize(
            width: variant.nativePointSize.width + contentPadding * 2,
            height: variant.nativePointSize.height + contentPadding * 2 + titleBarAllowance
        )
    }

    /// 探针内两个文本测量区（相对探针左上角，单位点）。
    ///
    /// 抓取脚本用它们把归一化互相关给出的原图框换算成 WCAG 对比度测量区：主标题单独一行，
    /// 重要长文本占其下两行，二者的墨迹占比都足以让 p95 落在文字上。
    public static func probeTextRegions(probeWidth: CGFloat) -> (primary: CGRect, importantCopy: CGRect) {
        let blockHeight = probeLineHeight + probeLineSpacing + probeLineHeight * 2
        let blockTop = probeHeight - probeInset - blockHeight
        let width = max(probeWidth - probeInset * 2, 1)
        return (
            primary: CGRect(x: probeInset, y: blockTop, width: width, height: probeLineHeight),
            importantCopy: CGRect(
                x: probeInset,
                y: blockTop + probeLineHeight + probeLineSpacing,
                width: width,
                height: probeLineHeight * 2
            )
        )
    }

    /// 探针相对原图下沿的垂直偏移（点）：VStack 里探针紧贴原图。
    public static let probeOffsetBelowImage: CGFloat = 0
}

/// 场景美术运行时证据的采集面（G5）。
///
/// 为什么单独开窗口：产品表面（卡片 header 等）用 `.fill` 裁切并叠加 scrim 与透明度，
/// 无法用模板匹配证明「出厂的派生图确实被渲染出来」。这里以未裁切、无遮罩的方式渲染，
/// 让 `docs/05_UI/artwork/tools/finish_world_artwork.py surface` 的归一化互相关与
/// `record` 的对比度复算都有可复算的像素依据；发布态观感仍由产品表面承担。
/// 单实例：采集脚本按 App 包内可执行路径断点启动前后都断言只有一个进程，见
/// `docs/05_UI/artwork/tools/capture_scene_runtime_evidence.py`。
private struct SceneArtworkReduceTransparencyKey: EnvironmentKey {
    /// 采集面本地的「降低透明度」渲染开关。
    ///
    /// 本机 `defaults write com.apple.universalaccess` 被系统拒绝，系统开关无法被自动化切换；
    /// 而产品遮罩 `WOMArtworkScrim` 是显式 `Color.opacity` 渐变、不是系统 `Material`，
    /// 系统开关对它本来就不产生渲染差异。这里显式建模该状态：当系统开关打开或采集脚本
    /// 注入同名偏好时，发布态探针改用更高的不透明度下限，采集据此证明「更少透明」这条
    /// 渲染路径下文本区仍然达标——而不是声称等于改动了系统开关。
    static let defaultValue = false
}

private struct SceneArtworkIncreasedContrastKey: EnvironmentKey {
    /// 采集面本地的「增强对比度」渲染开关。
    ///
    /// 与降低透明度同理：`\.colorSchemeContrast` 在 macOS 27 SDK 里是只读环境值，
    /// 采集脚本无法注入、系统开关又是受保护域写不进去。这里显式建模该状态，并按
    /// `WOMArtworkScrim.effectiveStrength` 的同一条规则（增强对比度把遮罩收紧 0.12）
    /// 收紧探针遮罩；系统开关真实打开时以系统值为准，不重复叠加。
    static let defaultValue = false
}

extension EnvironmentValues {
    var sceneArtworkReduceTransparency: Bool {
        get { self[SceneArtworkReduceTransparencyKey.self] }
        set { self[SceneArtworkReduceTransparencyKey.self] = newValue }
    }

    var sceneArtworkIncreasedContrast: Bool {
        get { self[SceneArtworkIncreasedContrastKey.self] }
        set { self[SceneArtworkIncreasedContrastKey.self] = newValue }
    }
}

public struct SceneArtworkRuntimeVerificationView: View {
    public static let windowID = "scene-artwork-verification"
    public static let windowTitle = "场景美术运行时校验"
    public static let scenePreferenceKey = "wom.artwork.verification.scene"
    public static let modePreferenceKey = "wom.artwork.verification.mode"
    public static let variantPreferenceKey = "wom.artwork.verification.variant"
    /// 辅助功能状态：本机 `defaults write com.apple.universalaccess` 被系统拒绝，
    /// 采集脚本改为注入这两个偏好键，并在证据里标注所用机制。
    public static let contrastPreferenceKey = "wom.artwork.verification.contrast"
    public static let transparencyPreferenceKey = "wom.artwork.verification.transparency"

    /// 系统里真实生效的辅助功能设置：注入值只做补充，系统开关打开时以系统值为准。
    @Environment(\.accessibilityReduceTransparency) private var systemReduceTransparency
    @Environment(\.colorSchemeContrast) private var systemContrast

    /// 采集脚本用 `defaults write` 注入，避免依赖界面自动化点选。
    @AppStorage(SceneArtworkRuntimeVerificationView.scenePreferenceKey)
    private var sceneRawValue = WOMWorldArtworkAsset.worldHero.rawValue
    @AppStorage(SceneArtworkRuntimeVerificationView.modePreferenceKey)
    private var modeRawValue = SceneArtworkVerificationMode.grid.rawValue
    @AppStorage(SceneArtworkRuntimeVerificationView.variantPreferenceKey)
    private var variantRawValue = SceneArtworkVerificationVariant.runtime.rawValue
    @AppStorage(SceneArtworkRuntimeVerificationView.contrastPreferenceKey)
    private var contrastRawValue = "standard"
    @AppStorage(SceneArtworkRuntimeVerificationView.transparencyPreferenceKey)
    private var transparencyRawValue = "standard"

    public init() {}

    public var body: some View {
        VStack(alignment: .leading, spacing: SceneArtworkVerificationMetrics.tileSpacing) {
            header

            switch mode {
            case .grid:
                gridSurface
            case .probe:
                probeSurface
            case .focus:
                focusSurface
            }
        }
        .padding(SceneArtworkVerificationMetrics.contentPadding)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(WOMWindowCanvas())
        .environment(\.sceneArtworkIncreasedContrast, increasedContrast)
        .environment(\.sceneArtworkReduceTransparency, reduceTransparency)
        .preferredColorScheme(.dark)
    }

    private var reduceTransparency: Bool {
        systemReduceTransparency || transparencyRawValue == "reduced"
    }

    private var increasedContrast: Bool {
        systemContrast == .increased || contrastRawValue == "increased"
    }

    private var mode: SceneArtworkVerificationMode {
        SceneArtworkVerificationMode(rawValue: modeRawValue) ?? .grid
    }

    private var variant: SceneArtworkVerificationVariant {
        SceneArtworkVerificationVariant(rawValue: variantRawValue) ?? .runtime
    }

    private var focusedScene: WOMWorldArtworkAsset {
        WOMWorldArtworkAsset(rawValue: sceneRawValue) ?? .worldHero
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xxs) {
            Text("场景美术运行时校验 · G5 采集面")
                .font(Font.Mystic.titleSmall)
                .foregroundStyle(Color.Mystic.brassGoldPrimary)

            Text(
                "未裁切 · 无遮罩渲染，模板匹配与对比度都从这些像素复算；"
                    + "辅助功能状态：增强对比度\(stateWord(increasedContrast, injected: contrastRawValue == "increased", system: systemContrast == .increased))"
                    + " · 降低透明度\(stateWord(reduceTransparency, injected: transparencyRawValue == "reduced", system: systemReduceTransparency))"
            )
                .font(Font.Mystic.caption)
                .foregroundStyle(Color.Mystic.textSecondary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// 抓取图上必须能读到「这个状态是系统给的还是采集注入的」。
    private func stateWord(_ active: Bool, injected: Bool, system: Bool) -> String {
        guard active else { return "关" }
        return "开（系统\(system ? "开" : "关")·注入\(injected ? "开" : "关")）"
    }

    private var gridSurface: some View {
        GeometryReader { proxy in
            let metrics = SceneArtworkVerificationMetrics.resolveGrid(
                available: proxy.size,
                count: WOMWorldArtworkAsset.allCases.count
            )

            LazyVGrid(
                columns: columns(for: metrics),
                alignment: .leading,
                spacing: SceneArtworkVerificationMetrics.tileSpacing
            ) {
                ForEach(WOMWorldArtworkAsset.allCases, id: \.rawValue) { asset in
                    SceneArtworkVerificationTile(asset: asset, metrics: metrics)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }

    private var probeSurface: some View {
        GeometryReader { proxy in
            let metrics = SceneArtworkVerificationMetrics.resolveProbeGrid(
                available: proxy.size,
                count: WOMWorldArtworkAsset.allCases.count
            )

            LazyVGrid(
                columns: columns(for: metrics),
                alignment: .leading,
                spacing: SceneArtworkVerificationMetrics.tileSpacing
            ) {
                ForEach(WOMWorldArtworkAsset.allCases, id: \.rawValue) { asset in
                    SceneArtworkVerificationProbeTile(asset: asset, metrics: metrics)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        }
    }

    /// 原生尺度呈现：抓取窗口与派生图 1:1 时用来做设备像素级比对。
    private var focusSurface: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.sm) {
            Text("\(focusedScene.rawValue) · \(variant.pixelSizeDescription) · 原生 1:1")
                .font(Font.Mystic.monoBadge)
                .foregroundStyle(Color.Mystic.textSecondary)

            WOMArtworkView(
                assetName: variant.assetName(for: focusedScene),
                fallback: .systemImage("photo"),
                contentMode: .fit
            )
            .frame(width: variant.nativePointSize.width, height: variant.nativePointSize.height)
            .accessibilityIdentifier(
                "wom.artwork.verification.focus.\(focusedScene.rawValue).\(variant.rawValue)"
            )

            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func columns(for metrics: SceneArtworkVerificationMetrics) -> [GridItem] {
        Array(
            repeating: GridItem(
                .fixed(metrics.tileWidth),
                spacing: SceneArtworkVerificationMetrics.tileSpacing
            ),
            count: metrics.columns
        )
    }
}

/// 未裁切的 runtime 原图砖块：模板匹配的比对基准，任何遮罩或透明度都会削弱它。
private struct SceneArtworkVerificationTile: View {
    let asset: WOMWorldArtworkAsset
    let metrics: SceneArtworkVerificationMetrics

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            WOMArtworkView(
                assetName: asset.runtimeAssetName,
                fallback: .systemImage("photo"),
                contentMode: .fit
            )
            .frame(width: metrics.tileWidth, height: metrics.imageHeight)
            .accessibilityIdentifier("wom.artwork.verification.runtime.\(asset.rawValue)")

            SceneArtworkVerificationCaption(asset: asset, suffix: "runtime 2560×1600")
                .frame(width: metrics.tileWidth)
        }
        .frame(width: metrics.tileWidth, alignment: .leading)
    }
}

/// 探针砖块：未裁切 wide 原图在上、发布态叠加探针在下，抓取脚本按这个顺序反推测量区。
private struct SceneArtworkVerificationProbeTile: View {
    let asset: WOMWorldArtworkAsset
    let metrics: SceneArtworkVerificationMetrics

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            WOMArtworkView(
                assetName: asset.wideHeaderAssetName,
                fallback: .systemImage("photo"),
                contentMode: .fit
            )
            .frame(width: metrics.tileWidth, height: metrics.imageHeight)
            .accessibilityIdentifier("wom.artwork.verification.probeWide.\(asset.rawValue)")

            SceneArtworkVerificationProbe(
                asset: asset,
                variant: .wide,
                width: metrics.tileWidth
            )
        }
        .frame(width: metrics.tileWidth, alignment: .leading)
    }
}

/// 发布态叠加探针：与卡片 header 相同的 wide 派生图 + 前导 scrim + 文本语义。
private struct SceneArtworkVerificationProbe: View {
    let asset: WOMWorldArtworkAsset
    let variant: SceneArtworkVerificationVariant
    let width: CGFloat

    /// 采集面注入的辅助功能状态；标准态沿用产品 header 的 0.92。
    @Environment(\.sceneArtworkReduceTransparency) private var reduceTransparency
    @Environment(\.sceneArtworkIncreasedContrast) private var injectedContrast
    @Environment(\.colorSchemeContrast) private var systemContrast

    /// 与 `WOMArtworkScrim.effectiveStrength` 同一条规则：增强对比度把遮罩收紧 0.12；
    /// 系统开关真实打开时由 `WOMArtworkScrim` 自己收紧，这里不重复叠加。
    private var scrimStrength: Double {
        let base = reduceTransparency ? 1 : 0.92
        guard injectedContrast, systemContrast != .increased else { return base }
        return min(1, base + 0.12)
    }

    var body: some View {
        ZStack(alignment: .bottomLeading) {
            WOMArtworkView(
                assetName: variant.assetName(for: asset),
                fallback: .systemImage("photo"),
                contentMode: .fill
            )
            .frame(width: width, height: SceneArtworkVerificationMetrics.probeHeight)
            .clipped()

            WOMArtworkScrim(edge: .leading, strength: scrimStrength)

            VStack(alignment: .leading, spacing: SceneArtworkVerificationMetrics.probeLineSpacing) {
                Text("贝克兰德 · 全景态势视窗")
                    .mysticTitleStyle(font: Font.Mystic.caption)
                    .lineLimit(1)
                    .frame(height: SceneArtworkVerificationMetrics.probeLineHeight, alignment: .leading)

                Text("雾气、灯火与雨幕之间的发布态文本")
                    .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                    .lineLimit(1)

                Text("可读性探针：与卡片 header 同语义的叠加层")
                    .mysticCaptionStyle(color: Color.Mystic.textSecondary)
                    .lineLimit(1)
            }
            .padding(SceneArtworkVerificationMetrics.probeInset)
        }
        .frame(width: width, height: SceneArtworkVerificationMetrics.probeHeight)
        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
        .accessibilityIdentifier("wom.artwork.verification.probe.\(asset.rawValue)")
    }
}

/// 砖块标签：同时承担语义身份自证（抓取图上可读到资产名与尺寸）。
private struct SceneArtworkVerificationCaption: View {
    let asset: WOMWorldArtworkAsset
    let suffix: String

    var body: some View {
        Text("\(asset.rawValue) · \(suffix)")
            .font(Font.Mystic.monoBadge)
            .foregroundStyle(Color.Mystic.textSecondary)
            .lineLimit(1)
            .frame(height: SceneArtworkVerificationMetrics.captionHeight, alignment: .leading)
    }
}

#Preview("Scene Artwork Runtime Verification") {
    SceneArtworkRuntimeVerificationView()
        .frame(width: 1180, height: 760)
}
