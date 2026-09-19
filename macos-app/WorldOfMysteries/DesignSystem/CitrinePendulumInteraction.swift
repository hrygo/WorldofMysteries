import CoreGraphics
import Foundation

/// 黄水晶手动灵摆交互的纯数学边界。
///
/// 只负责把指针几何与释放速度投影为小角度摆动参数；不拥有 SwiftUI 状态、
/// 不触发占卜、也不改变任何 Domain / StoryState。
public nonisolated enum CitrinePendulumInteraction {
    private static let minimumRadius: Double = 8
    private static let maximumAngularVelocityDegreesPerSecond: Double = 360

    /// 指针位置 → 摆角。使用 tanh 软限位而不是硬截断，让接近原画安全边界时逐渐产生阻力感。
    public static func dragAngle(
        pointer: CGPoint,
        pivot: CGPoint,
        maxAngleDegrees: Double = DesignTokens.Motion.pendulumSwingMaxDegrees
    ) -> Double {
        let dx = Double(pointer.x - pivot.x)
        let dy = Double(pointer.y - pivot.y)
        let radiusSquared = dx * dx + dy * dy
        guard radiusSquared >= minimumRadius * minimumRadius else { return 0 }

        let limit = max(abs(maxAngleDegrees), 0.001)
        let rawDegrees = atan2(dx, dy) * 180 / Double.pi
        return limit * tanh(rawDegrees / limit)
    }

    /// 笛卡尔释放速度 → 绕摆轴角速度（度/秒）。
    ///
    /// 对 theta = atan2(dx, dy) 求导：
    /// dtheta/dt = (dy*vx - dx*vy) / (dx^2 + dy^2)。
    public static func angularVelocityDegreesPerSecond(
        pointer: CGPoint,
        velocity: CGSize,
        pivot: CGPoint
    ) -> Double {
        let dx = Double(pointer.x - pivot.x)
        let dy = Double(pointer.y - pivot.y)
        let vx = Double(velocity.width)
        let vy = Double(velocity.height)
        let radiusSquared = dx * dx + dy * dy

        guard radiusSquared >= minimumRadius * minimumRadius,
              dx.isFinite, dy.isFinite, vx.isFinite, vy.isFinite
        else { return 0 }

        let radiansPerSecond = (dy * vx - dx * vy) / radiusSquared
        let degreesPerSecond = radiansPerSecond * 180 / Double.pi
        return min(
            max(degreesPerSecond, -maximumAngularVelocityDegreesPerSecond),
            maximumAngularVelocityDegreesPerSecond
        )
    }

    /// 把真实角速度投影到 SwiftUI spring 的归一化进度速度。
    ///
    /// 动画属性从当前角度走向 0，因此 target - current = -angle；
    /// 向中心运动得到正进度速度，继续向外甩得到负进度速度。
    public static func springInitialVelocity(
        angleDegrees: Double,
        angularVelocityDegreesPerSecond: Double
    ) -> Double {
        let remainingDistance = -angleDegrees
        guard remainingDistance.isFinite,
              angularVelocityDegreesPerSecond.isFinite,
              abs(remainingDistance) > 0.25
        else { return 0 }

        let normalized = angularVelocityDegreesPerSecond / remainingDistance
        return min(max(normalized, -1), 1)
    }
}
