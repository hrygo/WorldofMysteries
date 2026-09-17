import Foundation
import Observation

// MARK: - Artifact Registry

public enum ArtifactID: String, CaseIterable, Identifiable, Codable, Sendable {
  case probabilityDie
  case arrodesMirror
  case alzuhodQuill
  case trunsoestBrassBook
  case magicWishingLamp
  case creepingHunger
  case leymanoTravels
  case groselleTravels
  case azikCopperWhistle
  case cardsOfBlasphemy
  case seaGodScepter
  case staffOfStars
  case boxOfGreatOldOnes
  case deathKnell
  case unshadowedCrucifix

  public var id: String { rawValue }
}

public enum ArtifactFamily: String, CaseIterable, Sendable {
  case fateAndCausality
  case knowledgeAndLore
  case spaceAndWorld
  case capabilityAndCombat
  case rulePurificationInfrastructure

  public var localizedTitle: String {
    switch self {
    case .fateAndCausality: return "命运与因果"
    case .knowledgeAndLore: return "知识与隐秘"
    case .spaceAndWorld: return "空间与世界"
    case .capabilityAndCombat: return "能力与战斗"
    case .rulePurificationInfrastructure: return "规则、净化与基础能力"
    }
  }
}

public enum ArtifactCanonClass: String, Codable, Sendable {
  case sealedArtifact
  case mysticalItem
  case uniquenessArtifact
  case specialObject

  public var localizedTitle: String {
    switch self {
    case .sealedArtifact: return "封印物"
    case .mysticalItem: return "神奇物品"
    case .uniquenessArtifact: return "高位特殊物"
    case .specialObject: return "特殊物品"
    }
  }
}

/// 只映射到项目现有 `MysticTone`，不建立第二套颜色/视觉 Token。
public struct ArtifactDescriptor: Identifiable, Sendable {
  public let id: ArtifactID
  public let displayName: String
  public let subtitle: String
  public let family: ArtifactFamily
  public let canonClass: ArtifactCanonClass
  public let systemIcon: String
  public let tone: MysticTone
  public let shortGameplay: String
}

public enum ArtifactRegistry {
  public static let all: [ArtifactDescriptor] = [
    .init(
      id: .probabilityDie, displayName: "概率之骰", subtitle: "Probability Resolver",
      family: .fateAndCausality, canonClass: .uniquenessArtifact, systemIcon: "die.face.5",
      tone: .azure, shortGameplay: "重新加权仍然合法的结果概率；结果先提交，再表现投掷。"),
    .init(
      id: .arrodesMirror, displayName: "阿罗德斯", subtitle: "Truth Exchange",
      family: .knowledgeAndLore, canonClass: .sealedArtifact, systemIcon: "eye", tone: .azure,
      shortGameplay: "提问、揭示、反问与对等交换；真相有边界，也有代价。"),
    .init(
      id: .alzuhodQuill, displayName: "0-08 阿勒苏霍德之笔", subtitle: "Causality Writer",
      family: .fateAndCausality, canonClass: .sealedArtifact, systemIcon: "pencil.and.outline",
      tone: .amber, shortGameplay: "把期望结果编译为合理因果链，并保留自主补写与反噬。"),
    .init(
      id: .trunsoestBrassBook, displayName: "0-02 特伦索斯特黄铜书", subtitle: "Rule Overlay",
      family: .rulePurificationInfrastructure, canonClass: .uniquenessArtifact,
      systemIcon: "book.closed", tone: .gold, shortGameplay: "把规则候选交给世界 Validator；违规产生世界内惩罚。"),
    .init(
      id: .magicWishingLamp, displayName: "0-05 许愿神灯", subtitle: "Wish Contract",
      family: .fateAndCausality, canonClass: .sealedArtifact, systemIcon: "lamp.desk", tone: .amber,
      shortGameplay: "愿望会被解释：字面、漏洞、扭曲与代价不会完全预告。"),
    .init(
      id: .creepingHunger, displayName: "蠕动的饥饿", subtitle: "Soul Loadout",
      family: .capabilityAndCombat, canonClass: .mysticalItem,
      systemIcon: "hand.raised.fingers.spread", tone: .crimson,
      shortGameplay: "管理具体灵魂槽位与能力调用，同时承担饥饿约束。"),
    .init(
      id: .leymanoTravels, displayName: "莱曼诺的旅行笔记", subtitle: "Ability Recorder",
      family: .knowledgeAndLore, canonClass: .mysticalItem, systemIcon: "book.pages", tone: .teal,
      shortGameplay: "观察能力、尝试记录、占用页面，并在未来一次性释放。"),
    .init(
      id: .groselleTravels, displayName: "格罗塞尔游记", subtitle: "Story World Portal",
      family: .spaceAndWorld, canonClass: .mysticalItem, systemIcon: "book.pages.fill",
      tone: .azure, shortGameplay: "进入书中 StorySpace；记忆、知识与后果可回流主世界。"),
    .init(
      id: .azikCopperWhistle, displayName: "阿兹克铜哨", subtitle: "Diegetic Messenger",
      family: .rulePurificationInfrastructure, canonClass: .mysticalItem,
      systemIcon: "envelope.badge", tone: .teal, shortGameplay: "把通信变成世界内事件：写信、召唤、运输、送达、获知。"),
    .init(
      id: .cardsOfBlasphemy, displayName: "亵渎之牌", subtitle: "Pathway Codex",
      family: .knowledgeAndLore, canonClass: .specialObject, systemIcon: "rectangle.stack.fill",
      tone: .gold, shortGameplay: "按 Knowledge / Spoiler Gate 渐进揭示途径与晋升知识。"),
    .init(
      id: .seaGodScepter, displayName: "海神权杖", subtitle: "Authority & Prayer",
      family: .capabilityAndCombat, canonClass: .sealedArtifact, systemIcon: "cloud.bolt.rain",
      tone: .azure, shortGameplay: "环境权柄与祈祷回应双模式，形成可追溯世界事件。"),
    .init(
      id: .staffOfStars, displayName: "星之杖", subtitle: "Knowledge-based Projection",
      family: .spaceAndWorld, canonClass: .sealedArtifact, systemIcon: "sparkles", tone: .azure,
      shortGameplay: "依据真实认知重建地点/目标；认知缺口直接转化为投射误差。"),
    .init(
      id: .boxOfGreatOldOnes, displayName: "旧日之盒", subtitle: "Spatial Layers",
      family: .spaceAndWorld, canonClass: .sealedArtifact, systemIcon: "shippingbox", tone: .amber,
      shortGameplay: "三层空间语法：交换/微缩、旅行，以及不应随意开启的禁忌层。"),
    .init(
      id: .deathKnell, displayName: "丧钟", subtitle: "Weakness Targeting",
      family: .capabilityAndCombat, canonClass: .mysticalItem, systemIcon: "scope", tone: .crimson,
      shortGameplay: "把 Observation / Knowledge 支持的弱点转化为锁定，再交给战斗结算。"),
    .init(
      id: .unshadowedCrucifix, displayName: "无暗十字架", subtitle: "Purification Workbench",
      family: .rulePurificationInfrastructure, canonClass: .sealedArtifact,
      systemIcon: "cross.case", tone: .gold, shortGameplay: "净化、分离、提取材料与污染，不抽象成万能清除按钮。"),
  ]

  public static func descriptor(for id: ArtifactID) -> ArtifactDescriptor {
    all.first(where: { $0.id == id })!
  }
}

// MARK: - Shared Domain Boundary

public struct ArtifactContext: Codable, Hashable, Sendable {
  public var worldID: String
  public var worldlineID: String
  public var storySessionID: String?
  public var storyRevision: Int?
  public var actorID: String?
  public var targetIDs: [String]

  public init(
    worldID: String,
    worldlineID: String,
    storySessionID: String? = nil,
    storyRevision: Int? = nil,
    actorID: String? = nil,
    targetIDs: [String] = []
  ) {
    self.worldID = worldID
    self.worldlineID = worldlineID
    self.storySessionID = storySessionID
    self.storyRevision = storyRevision
    self.actorID = actorID
    self.targetIDs = targetIDs
  }
}

public enum ArtifactRiskBand: String, CaseIterable, Codable, Sendable {
  case low
  case guarded
  case high
  case extreme

  public var localizedTitle: String {
    switch self {
    case .low: return "低"
    case .guarded: return "戒备"
    case .high: return "高"
    case .extreme: return "极端"
    }
  }
}

public enum ArtifactActionKind: String, Codable, CaseIterable, Sendable {
  case ask
  case answerExchange
  case refuseExchange
  case enactRule
  case wish
  case graze
  case invokeSoul
  case recordAbility
  case invokeRecordedAbility
  case enterBookWorld
  case exitBookWorld
  case sendLetter
  case unlockLore
  case answerPrayer
  case invokeAuthority
  case projectLocation
  case openLayer
  case targetWeakness
  case fireWeaknessShot
  case purify
}

public enum ArtifactResolutionSeverity: String, Codable, Sendable {
  case neutral
  case favorable
  case warning
  case dangerous
}

public enum ArtifactCommitDisposition: String, Codable, Sendable {
  case observation
  case proposed
  case committed
  case rejected
}

public struct ArtifactActionRequest: Codable, Hashable, Sendable {
  public var requestID: UUID
  public var idempotencyKey: String
  public var artifactID: ArtifactID
  public var action: ArtifactActionKind
  public var context: ArtifactContext
  public var expectedStoryRevision: Int?
  public var input: String?
  public var selectionIDs: [String]
  public var numericParameters: [String: Double]
  public var stringParameters: [String: String]

  public init(
    requestID: UUID = UUID(),
    idempotencyKey: String? = nil,
    artifactID: ArtifactID,
    action: ArtifactActionKind,
    context: ArtifactContext,
    expectedStoryRevision: Int? = nil,
    input: String? = nil,
    selectionIDs: [String] = [],
    numericParameters: [String: Double] = [:],
    stringParameters: [String: String] = [:]
  ) {
    self.requestID = requestID
    self.idempotencyKey = idempotencyKey ?? requestID.uuidString
    self.artifactID = artifactID
    self.action = action
    self.context = context
    self.expectedStoryRevision = expectedStoryRevision ?? context.storyRevision
    self.input = input
    self.selectionIDs = selectionIDs
    self.numericParameters = numericParameters
    self.stringParameters = stringParameters
  }
}

public struct ArtifactActionResolution: Codable, Hashable, Sendable {
  public var requestID: UUID
  public var resolutionID: UUID
  public var committedRevision: Int?
  public var title: String
  public var message: String
  public var detailLines: [String]
  public var state: String
  public var severity: ArtifactResolutionSeverity
  public var disposition: ArtifactCommitDisposition
  public var resultingIDs: [String]
  public var meters: [String: Double]
  public var followUpPrompt: String?

  public init(
    requestID: UUID,
    resolutionID: UUID = UUID(),
    committedRevision: Int? = nil,
    title: String,
    message: String,
    detailLines: [String] = [],
    state: String = "resolved",
    severity: ArtifactResolutionSeverity = .neutral,
    disposition: ArtifactCommitDisposition = .observation,
    resultingIDs: [String] = [],
    meters: [String: Double] = [:],
    followUpPrompt: String? = nil
  ) {
    self.requestID = requestID
    self.resolutionID = resolutionID
    self.committedRevision = committedRevision
    self.title = title
    self.message = message
    self.detailLines = detailLines
    self.state = state
    self.severity = severity
    self.disposition = disposition
    self.resultingIDs = resultingIDs
    self.meters = meters
    self.followUpPrompt = followUpPrompt
  }
}

public protocol ArtifactActionResolving: Sendable {
  func resolve(_ request: ArtifactActionRequest) async throws -> ArtifactActionResolution
}

public struct ArtifactActionRecord: Identifiable, Sendable {
  public let id: UUID
  public let timestamp: Date
  public let request: ArtifactActionRequest
  public let resolution: ArtifactActionResolution

  public init(
    id: UUID = UUID(),
    timestamp: Date = .now,
    request: ArtifactActionRequest,
    resolution: ArtifactActionResolution
  ) {
    self.id = id
    self.timestamp = timestamp
    self.request = request
    self.resolution = resolution
  }
}

@Observable
@MainActor
public final class ArtifactActionModel {
  public enum Phase: Equatable {
    case idle
    case resolving(ArtifactActionKind)
    case resolved
    case error(String)
  }

  public private(set) var phase: Phase = .idle
  public private(set) var lastResolution: ArtifactActionResolution?
  public private(set) var history: [ArtifactActionRecord] = []
  public var meters: [String: Double]

  private let resolver: any ArtifactActionResolving
  @ObservationIgnored private var currentTask: Task<Void, Never>?

  public init(
    resolver: any ArtifactActionResolving,
    meters: [String: Double] = [:]
  ) {
    self.resolver = resolver
    self.meters = meters
  }

  public var isBusy: Bool {
    if case .resolving = phase { return true }
    return false
  }

  public func perform(_ request: ArtifactActionRequest) async {
    currentTask?.cancel()
    currentTask = nil
    await run(request)
  }

  public func performDetached(_ request: ArtifactActionRequest) {
    currentTask?.cancel()
    currentTask = Task { @MainActor [weak self] in
      await self?.run(request)
    }
  }

  public func cancelCurrentOperation() {
    currentTask?.cancel()
    currentTask = nil
    phase = .idle
  }

  public func resetPresentation(keepHistory: Bool = true) {
    cancelCurrentOperation()
    lastResolution = nil
    if !keepHistory { history.removeAll() }
  }

  private func run(_ request: ArtifactActionRequest) async {
    phase = .resolving(request.action)
    do {
      let result = try await resolver.resolve(request)
      guard !Task.isCancelled else {
        phase = .idle
        return
      }
      lastResolution = result
      meters.merge(result.meters) { _, new in new }
      history.append(.init(request: request, resolution: result))
      if history.count > 24 {
        history.removeFirst(history.count - 24)
      }
      phase = .resolved
    } catch is CancellationError {
      phase = .idle
    } catch {
      phase = .error(error.localizedDescription)
    }
  }
}
