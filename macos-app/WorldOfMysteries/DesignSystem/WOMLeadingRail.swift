import SwiftUI

/// 贴边语义竖条 (Leading Semantic Rail)。
///
/// 竖条的几何**由容器自身的圆角轮廓推导**，而不是在边缘叠一个独立的圆角矩形：
///
/// 1. 外边界与容器轮廓共用同一条 `RoundedRectangle(_:style: .continuous)` 路径
///    （先按轮廓中心描边、再裁掉轮廓以外的半条），因此直边段严丝合缝、圆角段跟着轮廓一起弯，
///    贴合度 100%：既不会外溢到面板之外，也不会在圆角处留缝；
/// 2. 厚度沿轮廓法线方向恒定，圆角处不会被拉宽或压扁；
/// 3. 两端收在圆角切点上（切点长度直接量取轮廓路径，见 `WOMLeadingRailMask`），
///    端面与轮廓垂直，既不越过圆角也不留缺口。
///
/// 调用方必须传入与容器背景**完全相同**的圆角半径，否则无从拟合。
public struct WOMLeadingRail: View {
    public let color: Color
    public let cornerRadius: CGFloat
    public let thickness: CGFloat

    /// - Parameters:
    ///   - color: 语义色（由 tone 决定，组件本身不持有语义）。
    ///   - cornerRadius: 容器圆角半径，必须与容器背景所用半径一致。
    ///   - thickness: 竖条厚度，沿轮廓法线方向恒定。
    public init(
        color: Color,
        cornerRadius: CGFloat,
        thickness: CGFloat = DesignTokens.ComponentMetrics.LeadingRail.thickness
    ) {
        self.color = color
        self.cornerRadius = cornerRadius
        self.thickness = thickness
    }

    public var body: some View {
        let contour = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)

        contour
            .stroke(color, lineWidth: thickness * 2)
            .clipShape(contour)
            .clipShape(WOMLeadingRailMask(thickness: thickness, cornerRadius: cornerRadius))
            .accessibilityHidden(true)
    }
}

/// 竖条在容器内的保留区：左侧竖直带 + 左上 / 左下两个圆盘。
///
/// 圆盘半径取「圆角切点到角点」的长度，其边界恰好在切点处与轮廓相切，
/// 于是竖条的端面落在切点上且垂直于轮廓：越过圆角的悬垂与直边段的缺口同时消失。
///
/// `nonisolated`：应用目标默认 MainActor 隔离，而 `Shape` 的一致性要求是 nonisolated 的，
/// 纯几何计算也不该被 actor 隔离绑住。
nonisolated struct WOMLeadingRailMask: Shape {
    var thickness: CGFloat
    var cornerRadius: CGFloat

    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.addRect(
            CGRect(
                x: rect.minX,
                y: rect.minY,
                width: min(thickness, rect.width),
                height: rect.height
            )
        )

        let radius = Self.cornerTangentLength(in: rect, cornerRadius: cornerRadius)
        if radius > 0 {
            let diameter = radius * 2
            path.addEllipse(
                in: CGRect(
                    x: rect.minX - radius,
                    y: rect.minY - radius,
                    width: diameter,
                    height: diameter
                )
            )
            path.addEllipse(
                in: CGRect(
                    x: rect.minX - radius,
                    y: rect.maxY - radius,
                    width: diameter,
                    height: diameter
                )
            )
        }
        return path
    }

    /// 量取轮廓顶边上的圆角切点位置。
    ///
    /// 连续圆角不是半径 r 的圆弧：曲线在角点内约 `1.5287·r` 处才与直边相切，
    /// 所以既不能写死 `r`，也不该把平滑系数当成常量抄进来。这里直接遍历轮廓路径的曲线端点，
    /// 取落在顶边上最靠左的那个点——系统若调整圆角平滑曲线，竖条端点会自动跟随。
    static func cornerTangentLength(in rect: CGRect, cornerRadius: CGFloat) -> CGFloat {
        let clamped = min(cornerRadius, min(rect.width, rect.height) / 2)
        guard clamped > 0 else { return 0 }

        let contour = Path(roundedRect: rect, cornerRadius: clamped, style: .continuous)
        var leftmostOnTopEdge: CGFloat?
        contour.cgPath.applyWithBlock { element in
            let element = element.pointee
            let endpoint: CGPoint
            switch element.type {
            case .moveToPoint, .addLineToPoint:
                endpoint = element.points[0]
            case .addQuadCurveToPoint:
                endpoint = element.points[1]
            case .addCurveToPoint:
                endpoint = element.points[2]
            case .closeSubpath:
                return
            @unknown default:
                return
            }

            guard abs(endpoint.y - rect.minY) <= 0.01 else { return }
            leftmostOnTopEdge = min(leftmostOnTopEdge ?? endpoint.x, endpoint.x)
        }

        guard let leftmostOnTopEdge else { return clamped }
        return max(leftmostOnTopEdge - rect.minX, 0)
    }
}
