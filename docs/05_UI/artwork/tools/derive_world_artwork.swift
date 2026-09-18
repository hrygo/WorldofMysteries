#!/usr/bin/env xcrun swift

import Foundation
import CoreGraphics
import ImageIO
import CryptoKit
import UniformTypeIdentifiers
import Darwin

private struct DerivativeError: Error, CustomStringConvertible {
    let description: String
}

private enum VerticalAnchor: String {
    case top
    case center
    case bottom
}

private struct Options {
    var input: URL?
    var runtimeOutput: URL?
    var wideOutput: URL?
    var wideAnchor: VerticalAnchor = .center
    var selfTest = false
}

private struct PixelSize: Codable {
    let width: Int
    let height: Int
}

private struct OutputRecord: Codable {
    let path: String
    let size: PixelSize
    let sha256: String
}

private struct Report: Codable {
    let input: OutputRecord
    let runtime: OutputRecord
    let wide: OutputRecord
    let wideAnchor: String
    let colorSpace: String
    let interpolation: String
}

private func parseArguments() throws -> Options {
    var options = Options()
    var index = 1
    let args = CommandLine.arguments

    while index < args.count {
        switch args[index] {
        case "--self-test":
            options.selfTest = true
            index += 1
        case "--input", "--runtime-output", "--wide-output":
            guard index + 1 < args.count else {
                throw DerivativeError(description: "Missing value for \(args[index])")
            }
            let value = URL(fileURLWithPath: args[index + 1])
            switch args[index] {
            case "--input": options.input = value
            case "--runtime-output": options.runtimeOutput = value
            case "--wide-output": options.wideOutput = value
            default: break
            }
            index += 2
        case "--wide-anchor":
            guard index + 1 < args.count,
                  let anchor = VerticalAnchor(rawValue: args[index + 1])
            else {
                throw DerivativeError(description: "--wide-anchor must be top, center or bottom")
            }
            options.wideAnchor = anchor
            index += 2
        case "--help", "-h":
            printUsage()
            exit(0)
        default:
            throw DerivativeError(description: "Unknown argument: \(args[index])")
        }
    }

    return options
}

private func printUsage() {
    print("""
    Usage:
      xcrun swift derive_world_artwork.swift \
        --input <4096x2560-master.png> \
        --runtime-output <runtime-2560x1600.png> \
        --wide-output <wide-2400x900.png> \
        [--wide-anchor top|center|bottom]

      xcrun swift derive_world_artwork.swift --self-test

    Contract:
      - input must be exactly 4096x2560
      - runtime is a full-frame 2560x1600 sRGB PNG
      - wide uses the full horizontal field and a 4096x1536 crop, then downsamples
        to 2400x900; vertical anchor defaults to center and may be top/bottom when the
        Image Contract requires preserving an upper/lower identity-bearing subject
      - no generative operation occurs in this tool
    """)
}

private func cropRect(
    sourceWidth: Int,
    sourceHeight: Int,
    targetWidth: Int,
    targetHeight: Int,
    verticalAnchor: VerticalAnchor = .center
) -> CGRect {
    let sourceAspect = Double(sourceWidth) / Double(sourceHeight)
    let targetAspect = Double(targetWidth) / Double(targetHeight)

    if sourceAspect < targetAspect {
        let cropHeight = Double(sourceWidth) / targetAspect
        let remaining = Double(sourceHeight) - cropHeight
        let y: Double
        switch verticalAnchor {
        case .top: y = 0
        case .center: y = remaining / 2
        case .bottom: y = remaining
        }
        return CGRect(x: 0, y: y, width: Double(sourceWidth), height: cropHeight).integral
    }

    if sourceAspect > targetAspect {
        let cropWidth = Double(sourceHeight) * targetAspect
        let x = (Double(sourceWidth) - cropWidth) / 2
        return CGRect(x: x, y: 0, width: cropWidth, height: Double(sourceHeight)).integral
    }

    return CGRect(x: 0, y: 0, width: sourceWidth, height: sourceHeight)
}

private func selfTest() throws {
    let wide = cropRect(
        sourceWidth: 4096,
        sourceHeight: 2560,
        targetWidth: 2400,
        targetHeight: 900
    )

    guard Int(wide.origin.x) == 0,
          Int(wide.origin.y) == 512,
          Int(wide.width) == 4096,
          Int(wide.height) == 1536
    else {
        throw DerivativeError(description: "16:10 -> 8:3 crop math regression: \(wide)")
    }

    let topWide = cropRect(
        sourceWidth: 4096,
        sourceHeight: 2560,
        targetWidth: 2400,
        targetHeight: 900,
        verticalAnchor: .top
    )

    guard Int(topWide.origin.x) == 0,
          Int(topWide.origin.y) == 0,
          Int(topWide.width) == 4096,
          Int(topWide.height) == 1536
    else {
        throw DerivativeError(description: "top-anchored 16:10 -> 8:3 crop regression: \(topWide)")
    }

    let bottomWide = cropRect(
        sourceWidth: 4096,
        sourceHeight: 2560,
        targetWidth: 2400,
        targetHeight: 900,
        verticalAnchor: .bottom
    )

    guard Int(bottomWide.origin.x) == 0,
          Int(bottomWide.origin.y) == 1024,
          Int(bottomWide.width) == 4096,
          Int(bottomWide.height) == 1536
    else {
        throw DerivativeError(description: "bottom-anchored 16:10 -> 8:3 crop regression: \(bottomWide)")
    }

    let sameAspect = cropRect(
        sourceWidth: 4096,
        sourceHeight: 2560,
        targetWidth: 2560,
        targetHeight: 1600
    )

    guard Int(sameAspect.origin.x) == 0,
          Int(sameAspect.origin.y) == 0,
          Int(sameAspect.width) == 4096,
          Int(sameAspect.height) == 2560
    else {
        throw DerivativeError(description: "16:10 full-frame crop regression: \(sameAspect)")
    }

    print("derive_world_artwork.swift self-test: PASS")
}

private func loadImage(_ url: URL) throws -> CGImage {
    guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else {
        throw DerivativeError(description: "Unable to open image: \(url.path)")
    }
    guard let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        throw DerivativeError(description: "Unable to decode image: \(url.path)")
    }
    return image
}

private func makeSRGBContext(width: Int, height: Int) throws -> CGContext {
    guard let colorSpace = CGColorSpace(name: CGColorSpace.sRGB) else {
        throw DerivativeError(description: "Unable to create sRGB color space")
    }

    let bitmapInfo = CGBitmapInfo.byteOrder32Big.rawValue
        | CGImageAlphaInfo.premultipliedLast.rawValue

    guard let context = CGContext(
        data: nil,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: 0,
        space: colorSpace,
        bitmapInfo: bitmapInfo
    ) else {
        throw DerivativeError(description: "Unable to allocate bitmap context")
    }

    context.interpolationQuality = .high
    return context
}

private func resized(_ image: CGImage, width: Int, height: Int) throws -> CGImage {
    let context = try makeSRGBContext(width: width, height: height)
    context.draw(
        image,
        in: CGRect(x: 0, y: 0, width: width, height: height)
    )
    guard let output = context.makeImage() else {
        throw DerivativeError(description: "Unable to create resized image")
    }
    return output
}

private func cropped(_ image: CGImage, rect: CGRect) throws -> CGImage {
    guard let output = image.cropping(to: rect) else {
        throw DerivativeError(description: "Unable to crop image using \(rect)")
    }
    return output
}

private func writePNG(_ image: CGImage, to url: URL) throws {
    try FileManager.default.createDirectory(
        at: url.deletingLastPathComponent(),
        withIntermediateDirectories: true
    )

    guard let destination = CGImageDestinationCreateWithURL(
        url as CFURL,
        UTType.png.identifier as CFString,
        1,
        nil
    ) else {
        throw DerivativeError(description: "Unable to create PNG destination: \(url.path)")
    }

    let properties: [CFString: Any] = [
        kCGImagePropertyDPIWidth: 144,
        kCGImagePropertyDPIHeight: 144,
    ]

    CGImageDestinationAddImage(destination, image, properties as CFDictionary)

    guard CGImageDestinationFinalize(destination) else {
        throw DerivativeError(description: "Unable to finalize PNG: \(url.path)")
    }
}

private func sha256(_ url: URL) throws -> String {
    let data = try Data(contentsOf: url)
    return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

private func record(_ url: URL, image: CGImage) throws -> OutputRecord {
    OutputRecord(
        path: url.path,
        size: PixelSize(width: image.width, height: image.height),
        sha256: try sha256(url)
    )
}

private func run() throws {
    let options = try parseArguments()

    if options.selfTest {
        try selfTest()
        return
    }

    guard let input = options.input,
          let runtimeOutput = options.runtimeOutput,
          let wideOutput = options.wideOutput
    else {
        printUsage()
        throw DerivativeError(description: "input, runtime-output and wide-output are required")
    }

    let master = try loadImage(input)

    guard master.width == 4096, master.height == 2560 else {
        throw DerivativeError(
            description: "Master must be exactly 4096x2560; got \(master.width)x\(master.height)"
        )
    }

    let runtime = try resized(master, width: 2560, height: 1600)
    try writePNG(runtime, to: runtimeOutput)

    let wideCrop = cropRect(
        sourceWidth: master.width,
        sourceHeight: master.height,
        targetWidth: 2400,
        targetHeight: 900,
        verticalAnchor: options.wideAnchor
    )
    let croppedWide = try cropped(master, rect: wideCrop)
    let wide = try resized(croppedWide, width: 2400, height: 900)
    try writePNG(wide, to: wideOutput)

    let report = Report(
        input: OutputRecord(
            path: input.path,
            size: PixelSize(width: master.width, height: master.height),
            sha256: try sha256(input)
        ),
        runtime: try record(runtimeOutput, image: runtime),
        wide: try record(wideOutput, image: wide),
        wideAnchor: options.wideAnchor.rawValue,
        colorSpace: "sRGB",
        interpolation: "CoreGraphics.high / sRGB destination context"
    )

    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    let reportData = try encoder.encode(report)
    print(String(decoding: reportData, as: UTF8.self))
}

do {
    try run()
} catch {
    fputs("derive_world_artwork.swift: \(error)\n", stderr)
    exit(1)
}
