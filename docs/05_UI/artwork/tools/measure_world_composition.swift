#!/usr/bin/env xcrun swift

import Foundation
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers
import Darwin

private struct ToolError: Error, CustomStringConvertible {
    let description: String
}

private struct RegionMetrics: Codable {
    let meanLuminance: Double
    let meanGradient: Double
}

private struct Point2D: Codable {
    let x: Double
    let y: Double
}

private struct MetricsReport: Codable {
    let width: Int
    let height: Int
    let left35: RegionMetrics
    let focus: RegionMetrics
    let leftToFocusGradientRatio: Double
    let leftToFocusLuminanceRatio: Double
    let brightestHalfPercentCentroid: Point2D
}

private struct Plane {
    let width: Int
    let height: Int
    let values: [Double]

    subscript(x: Int, y: Int) -> Double {
        values[y * width + x]
    }
}

private func loadRGBA(_ url: URL) throws -> (CGImage, [UInt8]) {
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
    else {
        throw ToolError(description: "Unable to decode image: \(url.path)")
    }

    let width = image.width
    let height = image.height
    let bytesPerRow = width * 4
    var bytes = [UInt8](repeating: 0, count: height * bytesPerRow)

    guard let colorSpace = CGColorSpace(name: CGColorSpace.sRGB),
          let context = CGContext(
            data: &bytes,
            width: width,
            height: height,
            bitsPerComponent: 8,
            bytesPerRow: bytesPerRow,
            space: colorSpace,
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
          )
    else {
        throw ToolError(description: "Unable to create RGBA context")
    }

    context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
    return (image, bytes)
}

private func luminancePlane(width: Int, height: Int, rgba: [UInt8]) -> Plane {
    var values = [Double](repeating: 0, count: width * height)
    for y in 0..<height {
        for x in 0..<width {
            let i = (y * width + x) * 4
            let r = Double(rgba[i]) / 255.0
            let g = Double(rgba[i + 1]) / 255.0
            let b = Double(rgba[i + 2]) / 255.0
            values[y * width + x] = 0.2126 * r + 0.7152 * g + 0.0722 * b
        }
    }
    return Plane(width: width, height: height, values: values)
}

private func gradientPlane(_ luminance: Plane) -> Plane {
    var values = [Double](repeating: 0, count: luminance.width * luminance.height)
    for y in 0..<luminance.height {
        for x in 0..<luminance.width {
            let here = luminance[x, y]
            let left = luminance[max(0, x - 1), y]
            let up = luminance[x, max(0, y - 1)]
            let gx = abs(here - left)
            let gy = abs(here - up)
            values[y * luminance.width + x] = (gx * gx + gy * gy).squareRoot()
        }
    }
    return Plane(width: luminance.width, height: luminance.height, values: values)
}

private func metrics(
    luminance: Plane,
    gradient: Plane,
    xRange: Range<Int>,
    yRange: Range<Int>
) -> RegionMetrics {
    var lum = 0.0
    var grad = 0.0
    var count = 0

    for y in yRange {
        for x in xRange {
            lum += luminance[x, y]
            grad += gradient[x, y]
            count += 1
        }
    }

    let divisor = Double(max(1, count))
    return RegionMetrics(
        meanLuminance: lum / divisor,
        meanGradient: grad / divisor
    )
}

private func brightCentroid(_ luminance: Plane) -> Point2D {
    let sorted = luminance.values.sorted()
    let thresholdIndex = max(0, Int(Double(sorted.count) * 0.995) - 1)
    let threshold = sorted[thresholdIndex]

    var sumX = 0.0
    var sumY = 0.0
    var count = 0.0

    for y in 0..<luminance.height {
        for x in 0..<luminance.width where luminance[x, y] >= threshold {
            sumX += Double(x) / Double(luminance.width)
            sumY += Double(y) / Double(luminance.height)
            count += 1
        }
    }

    guard count > 0 else { return Point2D(x: 0.5, y: 0.5) }
    return Point2D(x: sumX / count, y: sumY / count)
}

private func analyze(_ url: URL) throws -> MetricsReport {
    let (image, rgba) = try loadRGBA(url)
    let luminance = luminancePlane(width: image.width, height: image.height, rgba: rgba)
    let gradient = gradientPlane(luminance)

    let leftX = 0..<max(1, Int(Double(image.width) * 0.35))
    let allY = 0..<image.height

    let focusX = Int(Double(image.width) * 0.55)..<max(
        Int(Double(image.width) * 0.55) + 1,
        Int(Double(image.width) * 0.78)
    )
    let focusY = Int(Double(image.height) * 0.28)..<max(
        Int(Double(image.height) * 0.28) + 1,
        Int(Double(image.height) * 0.72)
    )

    let left = metrics(luminance: luminance, gradient: gradient, xRange: leftX, yRange: allY)
    let focus = metrics(luminance: luminance, gradient: gradient, xRange: focusX, yRange: focusY)

    return MetricsReport(
        width: image.width,
        height: image.height,
        left35: left,
        focus: focus,
        leftToFocusGradientRatio: left.meanGradient / max(focus.meanGradient, 0.000001),
        leftToFocusLuminanceRatio: left.meanLuminance / max(focus.meanLuminance, 0.000001),
        brightestHalfPercentCentroid: brightCentroid(luminance)
    )
}

private func selfTest() throws {
    let width = 100
    let height = 100
    var values = [Double](repeating: 0.1, count: width * height)

    for y in 28..<72 {
        for x in 55..<78 {
            values[y * width + x] = ((x + y) % 2 == 0) ? 0.8 : 0.25
        }
    }

    let luminance = Plane(width: width, height: height, values: values)
    let gradient = gradientPlane(luminance)
    let left = metrics(luminance: luminance, gradient: gradient, xRange: 0..<35, yRange: 0..<100)
    let focus = metrics(luminance: luminance, gradient: gradient, xRange: 55..<78, yRange: 28..<72)

    guard left.meanGradient < focus.meanGradient,
          left.meanLuminance < focus.meanLuminance
    else {
        throw ToolError(description: "Synthetic quiet/focus metric regression")
    }

    print("measure_world_composition.swift self-test: PASS")
}

private func main() throws {
    let args = CommandLine.arguments
    if args.contains("--self-test") {
        try selfTest()
        return
    }

    guard let inputIndex = args.firstIndex(of: "--input"), inputIndex + 1 < args.count else {
        throw ToolError(description: "Usage: measure_world_composition.swift --input <image>")
    }

    let report = try analyze(URL(fileURLWithPath: args[inputIndex + 1]))
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    print(String(decoding: try encoder.encode(report), as: UTF8.self))
}

do {
    try main()
} catch {
    fputs("measure_world_composition.swift: \(error)\n", stderr)
    exit(1)
}
