import Foundation

/// 示例世界快照（Presentation-only · 单一事实源）。
///
/// 接入 Local Engine 之前，界面上出现的叙事数值（人物身份、序列、灵性储备、世界时间）
/// 全部来自这一份声明。它存在的唯一目的是：**同一事实只声明一次**，
/// 避免侧边栏与工作区对同一个人物给出互相矛盾的数值（历史缺陷：侧边栏「占卜家 Seq 9 · 灵性 85%」
/// 与命运页「未服食魔药 (凡人) · 灵性 78%」同屏冲突）。
///
/// 约束：
/// - 它不写入任何领域数据库，也不代表 Domain Truth（遵守「AI/UI 不造事实」不变量）；
/// - 每个消费它的界面都必须能向用户表明这是示例数据（`isDemoData`）；
/// - Engine 接入后由 `AppState` 提供的真实快照替换，本类型随之删除。
public struct DemoWorldSnapshot: Sendable, Equatable {
    public let characterName: String
    public let characterShortName: String
    /// 当前序列的人类可读描述，例如「未服食魔药 (凡人)」。
    public let sequenceDescription: String
    /// 侧边栏等紧凑位置使用的短标签。
    public let sequenceBadge: String
    /// 灵性储备，取值 0...1。
    public let spirituality: Double
    public let worldTimeLabel: String
    public let locationLabel: String

    public init(
        characterName: String,
        characterShortName: String,
        sequenceDescription: String,
        sequenceBadge: String,
        spirituality: Double,
        worldTimeLabel: String,
        locationLabel: String
    ) {
        self.characterName = characterName
        self.characterShortName = characterShortName
        self.sequenceDescription = sequenceDescription
        self.sequenceBadge = sequenceBadge
        self.spirituality = min(max(spirituality, 0), 1)
        self.worldTimeLabel = worldTimeLabel
        self.locationLabel = locationLabel
    }

    /// 界面是否仍在使用示例数据。接入真实 Domain 快照前恒为 `true`。
    public var isDemoData: Bool { true }

    public var spiritualityPercentText: String {
        "\(Int((spirituality * 100).rounded()))%"
    }

    /// 命运页序幕场景：韦尔奇卧室的红月案发，此时克莱恩尚未服食魔药。
    public static let current = DemoWorldSnapshot(
        characterName: "克莱恩·莫雷蒂",
        characterShortName: "克莱恩",
        sequenceDescription: "未服食魔药 (凡人)",
        sequenceBadge: "凡人",
        spirituality: 0.78,
        worldTimeLabel: "第五纪 · 1349 年 · 廷根市",
        locationLabel: "廷根市 · 明斯克街 15 号"
    )
}
