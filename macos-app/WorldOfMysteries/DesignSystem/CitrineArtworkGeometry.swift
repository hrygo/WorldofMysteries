import CoreGraphics
import Foundation

/// 黄水晶吊坠原画视窗几何（纯函数，无 SwiftUI 依赖，可独立单测）
///
/// 原画为竖幅构图：手指捏链 → 银链 → 黄水晶 → 红茶水面。直接 `scaledToFill`
/// 会让黄水晶偏出视窗中心，且摆动枢轴落到画外，摇晃时水晶会横向漂出视窗。
///
/// 本几何保证：
/// 1. 黄水晶几何中心精确锚定视窗正中，且视窗边缘无缝隙；
/// 2. 摆动枢轴落在链条与视窗可见顶边的交点（即手指捏链处），摇晃自然；
/// 3. 仅「银链 + 黄水晶」条带参与摆动：整幅原画取景不被旋转余量吃掉，
///    静态场景（手、衣料、红茶杯、桌面）保持不动，符合真实灵摆的物理直觉。
public struct CitrineArtworkGeometry: Sendable, Equatable {
    public let imageSize: CGSize
    /// 黄水晶几何中心（原画像素坐标）
    public let subjectCenter: CGPoint
    /// 手指捏链点（链条垂下之处，摆动枢轴上限）
    public let chainGrip: CGPoint
    /// 覆盖安全系数：抵消像素取整造成的边缘缝隙
    public let coverageGuard: CGFloat
    /// 摆动条带宽度（原画像素）
    public let swingStripWidth: CGFloat
    /// 摆动条带自黄水晶中心向下延伸的高度（原画像素），用于完整覆盖水晶尖端
    public let swingStripBottomOffset: CGFloat
    
    /// 当前正典原画几何（严格取自 `DesignTokens.ComponentMetrics.CitrineArtwork`）
    public static let canonical = CitrineArtworkGeometry(
        imageSize: CGSize(
            width: DesignTokens.ComponentMetrics.CitrineArtwork.imageWidth,
            height: DesignTokens.ComponentMetrics.CitrineArtwork.imageHeight
        ),
        subjectCenter: CGPoint(
            x: DesignTokens.ComponentMetrics.CitrineArtwork.subjectCenterX,
            y: DesignTokens.ComponentMetrics.CitrineArtwork.subjectCenterY
        ),
        chainGrip: CGPoint(
            x: DesignTokens.ComponentMetrics.CitrineArtwork.chainGripX,
            y: DesignTokens.ComponentMetrics.CitrineArtwork.chainGripY
        ),
        coverageGuard: DesignTokens.ComponentMetrics.CitrineArtwork.coverageGuard,
        swingStripWidth: DesignTokens.ComponentMetrics.CitrineArtwork.swingStripWidth,
        swingStripBottomOffset: DesignTokens.ComponentMetrics.CitrineArtwork.swingStripBottomOffset
    )
    
    public init(
        imageSize: CGSize,
        subjectCenter: CGPoint,
        chainGrip: CGPoint,
        coverageGuard: CGFloat = 1.0,
        swingStripWidth: CGFloat,
        swingStripBottomOffset: CGFloat
    ) {
        self.imageSize = imageSize
        self.subjectCenter = subjectCenter
        self.chainGrip = chainGrip
        self.coverageGuard = coverageGuard
        self.swingStripWidth = swingStripWidth
        self.swingStripBottomOffset = swingStripBottomOffset
    }
    
    /// 视窗完整布局解：一次性给出缩放、原画落位、摆动枢轴与摆动条带
    public struct Layout: Sendable, Equatable {
        public let scale: CGFloat
        /// 原画在视窗坐标系中的中心点
        public let imageCenter: CGPoint
        /// 原画左上角在视窗坐标系中的位置
        public let imageOrigin: CGPoint
        /// 摆动枢轴（原画像素坐标）
        public let swingPivot: CGPoint
        /// `rotationEffect` 锚点（归一化原画坐标 0...1）
        public let swingAnchorUnitPoint: CGPoint
        /// 摆动条带（视窗坐标系）
        public let swingStripFrame: CGRect
    }
    
    public func resolveLayout(in viewport: CGSize) -> Layout {
        let scale = coverScale(fitting: viewport)
        let center = imageCenter(in: viewport, scale: scale)
        let pivot = swingPivotArtwork(in: viewport, scale: scale)
        let imageWidth = imageSize.width * scale
        let imageHeight = imageSize.height * scale
        
        return Layout(
            scale: scale,
            imageCenter: center,
            imageOrigin: CGPoint(x: center.x - imageWidth / 2, y: center.y - imageHeight / 2),
            swingPivot: pivot,
            swingAnchorUnitPoint: CGPoint(
                x: imageSize.width > 0 ? pivot.x / imageSize.width : 0.5,
                y: imageSize.height > 0 ? pivot.y / imageSize.height : 0
            ),
            swingStripFrame: swingStripFrame(in: viewport, scale: scale)
        )
    }
    
    /// 保持原画构图不变的高度（配合标准视窗宽度使用）
    public func panelHeight(forWidth width: CGFloat) -> CGFloat {
        guard imageSize.width > 0 else { return 0 }
        return width * imageSize.height / imageSize.width
    }
    
    /// 最小覆盖缩放：铺满视窗，同时允许黄水晶中心落在视窗正中
    public func coverScale(fitting viewport: CGSize) -> CGFloat {
        guard viewport.width > 0, viewport.height > 0 else { return 0 }
        let halfSpanX = min(subjectCenter.x, imageSize.width - subjectCenter.x)
        let halfSpanY = min(subjectCenter.y, imageSize.height - subjectCenter.y)
        guard halfSpanX > 0, halfSpanY > 0 else { return 0 }
        return max(viewport.width / (2 * halfSpanX), viewport.height / (2 * halfSpanY)) * coverageGuard
    }
    
    /// 原画在视窗坐标系中的中心点（使黄水晶中心精确落于视窗几何中心）
    public func imageCenter(in viewport: CGSize, scale: CGFloat) -> CGPoint {
        CGPoint(
            x: viewport.width / 2 + (imageSize.width / 2 - subjectCenter.x) * scale,
            y: viewport.height / 2 + (imageSize.height / 2 - subjectCenter.y) * scale
        )
    }
    
    // MARK: - 摆动枢轴
    
    /// 摆动枢轴（原画像素坐标）：链条与视窗可见顶边的交点，收敛于捏链点与黄水晶中心之间
    public func swingPivotArtwork(in viewport: CGSize, scale: CGFloat) -> CGPoint {
        guard scale > 0 else { return chainGrip }
        
        let visibleTopY = subjectCenter.y - (viewport.height / 2) / scale
        let lower = min(chainGrip.y, subjectCenter.y)
        let upper = max(chainGrip.y, subjectCenter.y)
        let pivotY = min(max(visibleTopY, lower), upper)
        
        let span = subjectCenter.y - chainGrip.y
        let t = span == 0 ? 0 : (pivotY - chainGrip.y) / span
        return CGPoint(x: chainGrip.x + (subjectCenter.x - chainGrip.x) * t, y: pivotY)
    }
    
    /// 摆动枢轴在视窗坐标系中的位置
    public func swingPivotViewport(in viewport: CGSize, scale: CGFloat) -> CGPoint {
        let pivot = swingPivotArtwork(in: viewport, scale: scale)
        let center = imageCenter(in: viewport, scale: scale)
        return CGPoint(
            x: center.x + (pivot.x - imageSize.width / 2) * scale,
            y: center.y + (pivot.y - imageSize.height / 2) * scale
        )
    }
    
    // MARK: - 摆动条带
    
    /// 摆动条带（视窗坐标系）：自捏链点向下涵盖银链与整颗黄水晶，仅此区域参与摆动
    public func swingStripFrame(in viewport: CGSize, scale: CGFloat) -> CGRect {
        guard scale > 0 else { return .zero }
        
        let pivot = swingPivotViewport(in: viewport, scale: scale)
        let center = imageCenter(in: viewport, scale: scale)
        
        let top = pivot.y
        let bottom = center.y + swingStripBottomOffset * scale
        let width = swingStripWidth * scale
        
        return CGRect(
            x: center.x - width / 2,
            y: top,
            width: width,
            height: max(bottom - top, 0)
        )
    }
}
