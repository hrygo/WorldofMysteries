import Foundation

/// 仅供 ComponentGallery / Preview 使用。
/// 产品态必须由 Local Engine IPC Adapter 实现 `ArtifactActionResolving`；
/// 此 resolver 不写数据库、不形成 Domain Truth。
public struct PreviewArtifactResolver: ArtifactActionResolving {
  public init() {}

  public func resolve(_ request: ArtifactActionRequest) async throws -> ArtifactActionResolution {
    try await Task.sleep(for: .milliseconds(260))

    switch (request.artifactID, request.action) {
    case (.arrodesMirror, .ask):
      return .init(
        requestID: request.requestID,
        title: "镜面浮现了回答",
        message: "你得到了一条有限、可追溯的真实线索。",
        detailLines: ["Reveal Level · Partial", "高位秘密仍受 Knowledge / Spoiler Gate 约束。"],
        state: "exchange_due",
        disposition: .observation,
        meters: ["exchangeDebt": 0.35],
        followUpPrompt: "按照对等原则，现在轮到我提问了。"
      )

    case (.arrodesMirror, .answerExchange):
      return .init(
        requestID: request.requestID, title: "交换完成", message: "镜面恢复平静。", state: "exchange_complete",
        disposition: .committed, meters: ["exchangeDebt": 0.05])

    case (.arrodesMirror, .refuseExchange):
      return .init(
        requestID: request.requestID, title: "交换被拒绝", message: "阿罗德斯没有忘记这次拒绝。",
        state: "exchange_refused", severity: .warning, disposition: .committed,
        meters: ["exchangeDebt": 0.72])

    case (.trunsoestBrassBook, .enactRule):
      return .init(
        requestID: request.requestID,
        committedRevision: request.expectedStoryRevision.map { $0 + 1 }, title: "新规则已经写入",
        message: request.input ?? "一条新规则浮现在黄铜页上。",
        detailLines: ["Rule Validator 已激活", "违规会产生世界内后果。"], state: "rule_active",
        severity: .warning, disposition: .committed, meters: ["rulePressure": 0.46])

    case (.magicWishingLamp, .wish):
      return .init(
        requestID: request.requestID,
        committedRevision: request.expectedStoryRevision.map { $0 + 1 }, title: "愿望被接受",
        message: "字面含义并不是唯一解释。",
        detailLines: ["Interpretation · Sealed", "Cost · Hidden", "Distortion · Unknown"],
        state: "interpretation_hidden", severity: .dangerous, disposition: .committed,
        meters: ["wishExposure": 0.31])

    case (.creepingHunger, .invokeSoul):
      let hunger = min(1, (request.numericParameters["hunger"] ?? 0.3) + 0.14)
      return .init(
        requestID: request.requestID, title: "灵魂回应", message: "所选能力进入一次调用窗口。",
        state: "soul_invoked", severity: hunger > 0.75 ? .dangerous : .warning,
        disposition: .committed, meters: ["hunger": hunger])

    case (.leymanoTravels, .recordAbility):
      return .init(
        requestID: request.requestID, title: "记录成功", message: "空白页面留下新的非凡痕迹。", state: "recorded",
        severity: .favorable, disposition: .committed)

    case (.leymanoTravels, .invokeRecordedAbility):
      return .init(
        requestID: request.requestID, title: "页面被消耗", message: "能力释放后，这一页重新归于空白。",
        state: "page_consumed", disposition: .committed)

    case (.groselleTravels, .enterBookWorld):
      return .init(
        requestID: request.requestID,
        committedRevision: request.expectedStoryRevision.map { $0 + 1 }, title: "书页成为世界",
        message: "入口已经形成；进入后的经历仍属于当前 Worldline。", state: "portal_open", severity: .warning,
        disposition: .committed)

    case (.groselleTravels, .exitBookWorld):
      return .init(
        requestID: request.requestID,
        committedRevision: request.expectedStoryRevision.map { $0 + 1 }, title: "返回主世界",
        message: "参与者带着已形成的 Memory / Knowledge 后果返回。", state: "returned", disposition: .committed)

    case (.azikCopperWhistle, .sendLetter):
      return .init(
        requestID: request.requestID, title: "白骨信使接过了信", message: "消息已经进入世界内运输流程。",
        state: "in_transit", disposition: .committed, resultingIDs: ["preview.message.001"])

    case (.cardsOfBlasphemy, .unlockLore):
      return .init(
        requestID: request.requestID, title: "知识页展开",
        message: "只揭示当前 Knowledge / Spoiler Profile 允许的内容。", state: "lore_unlocked",
        severity: .favorable, disposition: .committed, meters: ["revealBoost": 0.14])

    case (.seaGodScepter, .invokeAuthority):
      let intensity = request.numericParameters["intensity"] ?? 0.55
      return .init(
        requestID: request.requestID,
        committedRevision: request.expectedStoryRevision.map { $0 + 1 }, title: "海与雷回应",
        message: request.input ?? "环境权柄形成可验证的世界影响。", state: "authority_invoked",
        severity: intensity > 0.75 ? .dangerous : .warning, disposition: .committed,
        meters: ["authorityLoad": min(1, intensity * 0.82)])

    case (.seaGodScepter, .answerPrayer):
      return .init(
        requestID: request.requestID, title: "祈祷得到回应", message: "回应已经形成一个 WorldEvent Candidate。",
        state: "prayer_answered", disposition: .committed)

    case (.staffOfStars, .projectLocation):
      let completeness = request.numericParameters["knowledgeCompleteness"] ?? 0.65
      return .init(
        requestID: request.requestID, title: "空间投射",
        message: completeness >= 0.8 ? "地点重建稳定。" : "认知存在缺口，投射误差上升。",
        state: completeness >= 0.8 ? "projection_stable" : "projection_uncertain",
        severity: completeness >= 0.8 ? .favorable : .warning, disposition: .committed,
        meters: ["projectionConfidence": completeness])

    case (.boxOfGreatOldOnes, .openLayer):
      let layer = request.stringParameters["layer"] ?? "1"
      let forbidden = layer == "3"
      return .init(
        requestID: request.requestID, title: "旧日之盒 · 第 \(layer) 层",
        message: forbidden ? "当前世界条件不允许开启第三层。" : "空间机制已经激活。",
        state: forbidden ? "forbidden" : "active", severity: forbidden ? .dangerous : .warning,
        disposition: forbidden ? .rejected : .committed)

    case (.deathKnell, .targetWeakness):
      return .init(
        requestID: request.requestID, title: "弱点锁定", message: "只显示 Observation / Knowledge 已支持的弱点。",
        state: "target_locked", disposition: .observation)

    case (.deathKnell, .fireWeaknessShot):
      return .init(
        requestID: request.requestID,
        committedRevision: request.expectedStoryRevision.map { $0 + 1 }, title: "丧钟鸣响",
        message: "射击已交给 Combat / Outcome Resolver 结算。", state: "shot_committed",
        severity: .dangerous, disposition: .committed)

    case (.unshadowedCrucifix, .purify):
      let intensity = request.numericParameters["intensity"] ?? 0.55
      return .init(
        requestID: request.requestID, title: "处理完成", message: "污染与材料被重新分离。", state: "purified",
        severity: .favorable, disposition: .committed,
        meters: ["purification": min(1, 0.56 + intensity * 0.38)])

    default:
      return .init(
        requestID: request.requestID,
        title: ArtifactRegistry.descriptor(for: request.artifactID).displayName,
        message: "演示 resolver 已收到操作。", disposition: .observation)
    }
  }
}
