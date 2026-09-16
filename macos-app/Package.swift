// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "WorldOfMysteriesApp",
    platforms: [
        .macOS("26.0")
    ],
    products: [
        .library(name: "WorldOfMysteriesCore", targets: ["WorldOfMysteriesCore"]),
    ],
    dependencies: [],
    targets: [
        .target(
            name: "WorldOfMysteriesCore",
            path: "WorldOfMysteries",
            exclude: ["MyApp.swift"], // Exclude App entry point for library/testing target
            swiftSettings: [
                .enableUpcomingFeature("ExistentialAny"),
                .enableExperimentalFeature("StrictConcurrency")
            ]
        ),
        .testTarget(
            name: "WorldOfMysteriesTests",
            dependencies: ["WorldOfMysteriesCore"],
            path: "WorldOfMysteriesTests",
            swiftSettings: [
                .enableUpcomingFeature("ExistentialAny"),
                .enableExperimentalFeature("StrictConcurrency")
            ]
        )
    ]
)
