import CoreGraphics
import Testing
@testable import WorldOfMysteriesCore

@Suite("Citrine Pendulum Direct Interaction")
struct CitrinePendulumInteractionTests {
    @Test("vertical pointer stays centered and horizontal displacement preserves direction")
    func dragAngleDirection() {
        let pivot = CGPoint(x: 100, y: 20)

        let centered = CitrinePendulumInteraction.dragAngle(
            pointer: CGPoint(x: 100, y: 150),
            pivot: pivot
        )
        let right = CitrinePendulumInteraction.dragAngle(
            pointer: CGPoint(x: 130, y: 150),
            pivot: pivot
        )
        let left = CitrinePendulumInteraction.dragAngle(
            pointer: CGPoint(x: 70, y: 150),
            pivot: pivot
        )

        #expect(abs(centered) < 0.0001)
        #expect(right > 0)
        #expect(left < 0)
    }

    @Test("soft limit never leaves the high-fidelity artwork safety envelope")
    func dragAngleSoftLimit() {
        let pivot = CGPoint(x: 100, y: 20)
        let limit = DesignTokens.Motion.pendulumSwingMaxDegrees

        let farRight = CitrinePendulumInteraction.dragAngle(
            pointer: CGPoint(x: 500, y: 80),
            pivot: pivot
        )
        let farLeft = CitrinePendulumInteraction.dragAngle(
            pointer: CGPoint(x: -300, y: 80),
            pivot: pivot
        )

        #expect(abs(farRight) <= limit)
        #expect(abs(farLeft) <= limit)
        #expect(farRight > limit * 0.95)
        #expect(farLeft < -limit * 0.95)
    }

    @Test("release velocity becomes signed angular velocity around the grip point")
    func angularVelocityDirection() {
        let pivot = CGPoint(x: 100, y: 20)
        let pointer = CGPoint(x: 100, y: 150)

        let rightward = CitrinePendulumInteraction.angularVelocityDegreesPerSecond(
            pointer: pointer,
            velocity: CGSize(width: 120, height: 0),
            pivot: pivot
        )
        let leftward = CitrinePendulumInteraction.angularVelocityDegreesPerSecond(
            pointer: pointer,
            velocity: CGSize(width: -120, height: 0),
            pivot: pivot
        )

        #expect(rightward > 0)
        #expect(leftward < 0)
    }

    @Test("spring velocity distinguishes motion toward center from an outward fling")
    func springVelocityDirection() {
        let towardCenter = CitrinePendulumInteraction.springInitialVelocity(
            angleDegrees: 6,
            angularVelocityDegreesPerSecond: -30
        )
        let outward = CitrinePendulumInteraction.springInitialVelocity(
            angleDegrees: 6,
            angularVelocityDegreesPerSecond: 30
        )

        #expect(towardCenter > 0)
        #expect(outward < 0)
        #expect(abs(towardCenter) <= 1)
        #expect(abs(outward) <= 1)
    }

    @Test("near-pivot or non-finite inputs cannot create unstable motion")
    func degenerateInputSafety() {
        let pivot = CGPoint(x: 100, y: 20)

        let angle = CitrinePendulumInteraction.dragAngle(
            pointer: CGPoint(x: 102, y: 22),
            pivot: pivot
        )
        let velocity = CitrinePendulumInteraction.angularVelocityDegreesPerSecond(
            pointer: CGPoint(x: 102, y: 22),
            velocity: CGSize(width: 10_000, height: 10_000),
            pivot: pivot
        )

        #expect(angle == 0)
        #expect(velocity == 0)
        #expect(
            CitrinePendulumInteraction.springInitialVelocity(
                angleDegrees: .nan,
                angularVelocityDegreesPerSecond: 1
            ) == 0
        )
    }
}
