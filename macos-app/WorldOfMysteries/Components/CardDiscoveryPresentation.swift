import Foundation

/// 依据 `docs/05_UI/UI_交互基线_v1.0.md` 第 7 节“Card Collection”
public nonisolated enum CardDiscoveryStage: String, Sendable {
    case unknown = "unknown"                       // 完全未知，迷雾笼罩
    case silhouette = "silhouette"                 // 剪影碎片
    case identified = "identified"                 // 确认序列名称
    case partiallyRevealed = "partially_revealed"   // 部分魔药配方揭示
    case established = "established"               // 完整生平传记建立
}

/// A projection of the discovery stage already supplied by the caller, not a source of Canon.
/// Visible copy and assistive copy share one boundary so hidden identity cannot leak through either.
nonisolated struct CardDiscoveryPresentation: Equatable, Sendable {
    let revealsIdentity: Bool
    let pathwayLabel: String
    let sequenceLabel: String
    let title: String
    let stageText: String
    let accessibilityLabel: String

    init(stage: CardDiscoveryStage, pathwayName: String, sequenceNumber: Int, sequenceTitle: String) {
        switch stage {
        case .unknown:
            revealsIdentity = false
            pathwayLabel = "途径未知"
            sequenceLabel = "Seq.?"
            title = "未知卡牌"
            stageText = "未探索"
            accessibilityLabel = "未知卡牌，途径与序列尚未发现"
        case .silhouette:
            revealsIdentity = false
            pathwayLabel = "途径待辨"
            sequenceLabel = "Seq.?"
            title = "卡牌残片"
            stageText = "残片感知"
            accessibilityLabel = "卡牌残片，身份尚待辨认"
        case .identified, .partiallyRevealed, .established:
            revealsIdentity = true
            pathwayLabel = pathwayName
            sequenceLabel = "Seq.\(sequenceNumber)"
            title = sequenceTitle
            accessibilityLabel = "\(pathwayName)，序列 \(sequenceNumber) \(sequenceTitle)"
            switch stage {
            case .identified: stageText = "已知序列"
            case .partiallyRevealed: stageText = "配方解析中"
            case .established: stageText = "生平已建立"
            case .unknown, .silhouette: stageText = "未探索"
            }
        }
    }
}
