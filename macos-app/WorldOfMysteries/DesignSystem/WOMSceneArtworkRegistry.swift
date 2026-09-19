import SwiftUI

/// 生产场景的语义身份。
///
/// 这里登记的是**表现层场景**，不是导航项：一个导航页可以同时承载多个场景语义
/// （命运页既承载 `fateIntervention`，也在底部承载 `artifactLibrary`）。
public nonisolated enum WOMSceneIdentity: String, CaseIterable, Sendable {
    /// 世界观察首页：世界独立演化的入口。
    case worldObservation
    /// 命运干预：既定事实与开放未来之间的干预态。
    case fateIntervention
    /// 人物档案：长期存在的人与其卷宗。
    case characterCodex
    /// 私人历史：已提交的 Episode 沉淀。
    case narrativeArchive
    /// 世界线：1349 正典主轴与显式登记的分叉。
    case worldlineAtlas
    /// 调查笔记与占卜器材。
    case investigationNotes
    /// 特殊物品档案库：封存证物与受控研究。
    case artifactLibrary

    /// 该场景归属的已批准 W1–W6 场景族。
    public var asset: WOMWorldArtworkAsset {
        switch self {
        case .worldObservation: .worldHero
        case .fateIntervention: .grayFog
        case .characterCodex: .codexArchive
        case .narrativeArchive: .codexArchive
        case .worldlineAtlas: .fateWorldline
        case .investigationNotes: .ritualAltar
        case .artifactLibrary: .artifactVault
        }
    }

    /// 场景派生图变体。
    ///
    /// 页头场景带使用 `wideHeader`（2400×900，正是为横向页头裁切生产）；
    /// `sceneRuntime`（2560×1600）留给内容面纹理。两者都不会解析到生产 master。
    public var variant: WOMArtworkVariant {
        switch self {
        case .worldObservation, .fateIntervention, .characterCodex,
            .narrativeArchive, .worldlineAtlas, .investigationNotes, .artifactLibrary:
            .wideHeader
        }
    }

    /// 图片不可用时的语义回退图标（与场景语义一致，而不是通用占位符）。
    public var fallbackIcon: WOMIconSource {
        switch self {
        case .worldObservation: .asset(.world)
        case .fateIntervention: .navigation(.fate)
        case .characterCodex: .navigation(.character)
        case .narrativeArchive: .asset(.codex)
        case .worldlineAtlas: .navigation(.worldline)
        case .investigationNotes: .navigation(.notes)
        case .artifactLibrary: .asset(.artifact)
        }
    }

    /// 场景身份说明：描述这个场景在游戏里承载什么，而不是美术自述。
    public var caption: String {
        switch self {
        case .worldObservation:
            "工业时代的城市与煤气灯先成立，异常只作为第二阅读层。"
        case .fateIntervention:
            "灰雾之上的尺度不可度量；干预只发生在既定事实与开放未来之间。"
        case .characterCodex:
            "档案柜、旧纸与黄铜仪器：人物是长期存在的人，不是一张属性面板。"
        case .narrativeArchive:
            "已提交的 Episode 沉淀为私人历史，可以回看，不会被重新编造。"
        case .worldlineAtlas:
            "1349 正典主轴与显式登记的世界线分叉；分叉必须被隔离，而不是被抹平。"
        case .investigationNotes:
            "钢笔、纸张与占卜器材互相印证；线索在案头被整理，而不在特效里。"
        case .artifactLibrary:
            "封存证物与受控研究：危险物品被隔离观察，而不是拿出来炫耀。"
        }
    }
}

/// 一个场景与其运行时美术载荷的绑定结果。
public nonisolated struct WOMSceneArtworkDeclaration: Sendable {
    public let scene: WOMSceneIdentity
    public let asset: WOMWorldArtworkAsset
    public let variant: WOMArtworkVariant
    public let fallbackIcon: WOMIconSource
    public let caption: String

    /// 可直接交给 `WOMArtworkView` 的 Asset Catalog 名称。
    ///
    /// 变体不匹配时回退到未裁切的场景派生图，而不是抛错或落到生产 master。
    public var assetName: String {
        asset.assetName(for: variant) ?? asset.runtimeAssetName
    }
}

/// 场景美术登记表：回答「哪个真实场景用哪张已批准的图」。
///
/// 这张表不承载任何领域事实：世界状态、人物状态与叙事提交仍来自 Local Engine IPC 与
/// `DemoWorldSnapshot`。它也不允许出现生产 master —— 只能登记运行时可加载的派生图。
public nonisolated enum WOMSceneArtworkRegistry: Sendable {
    public static var all: [WOMSceneArtworkDeclaration] {
        WOMSceneIdentity.allCases.map(declaration(for:))
    }

    public static func declaration(for scene: WOMSceneIdentity) -> WOMSceneArtworkDeclaration {
        WOMSceneArtworkDeclaration(
            scene: scene,
            asset: scene.asset,
            variant: scene.variant,
            fallbackIcon: scene.fallbackIcon,
            caption: scene.caption
        )
    }

    /// 导航页 → 场景页头的映射。
    ///
    /// `.cards` 与 `.settings` 没有对应的已批准场景资产，因此不挂场景页头：
    /// 宁可保持现状，也不给它们套一张语义不符的图。
    public static func scene(for item: NavigationItem) -> WOMSceneIdentity? {
        switch item {
        case .world: .worldObservation
        case .character: .characterCodex
        case .storyBook: .narrativeArchive
        case .worldline: .worldlineAtlas
        case .notes: .investigationNotes
        case .fate, .cards, .gallery, .settings: nil
        }
    }

    /// 已批准 W1–W6 六个场景族的覆盖情况，供契约测试核对「没有孤立的场景资产」。
    public static var coveredAssets: Set<WOMWorldArtworkAsset> {
        Set(all.map(\.asset))
    }
}
