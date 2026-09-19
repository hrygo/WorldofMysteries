import CoreGraphics
import Foundation

// 用法: window_identity_by_pid.swift <pid>
// 只列出指定 pid 的屏幕可见窗口；每行一个 JSON 对象。
guard CommandLine.arguments.count > 1, let wantedPID = Int(CommandLine.arguments[1]) else {
    FileHandle.standardError.write(Data("usage: window_identity_by_pid.swift <pid>\n".utf8))
    exit(2)
}

guard let windows = CGWindowListCopyWindowInfo(
    [.optionOnScreenOnly, .excludeDesktopElements],
    kCGNullWindowID
) as? [[String: Any]] else {
    exit(1)
}

for window in windows {
    let pid = window[kCGWindowOwnerPID as String] as? Int ?? -1
    guard pid == wantedPID else { continue }

    let number = window[kCGWindowNumber as String] as? Int ?? -1
    let layer = window[kCGWindowLayer as String] as? Int ?? -1
    let bounds = window[kCGWindowBounds as String] as? [String: Any] ?? [:]
    let width = Int((bounds["Width"] as? Double ?? 0).rounded())
    let height = Int((bounds["Height"] as? Double ?? 0).rounded())

    print(
        "{\"window_number\": \(number), \"pid\": \(pid), \"width\": \(width), "
            + "\"height\": \(height), \"layer\": \(layer)}"
    )
}
