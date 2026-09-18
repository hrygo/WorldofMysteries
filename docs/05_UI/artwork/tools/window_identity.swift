import CoreGraphics
import Foundation

// 用法: window_identity.swift <属主进程名>
//
// 按属主列出屏幕上的可见窗口，每行一个 JSON 对象：
//   {"window_number": 437, "pid": 67096, "width": 1280, "height": 800, "layer": 0}
//
// 尺寸单位是点（与 `System Events` 的窗口 size 一致），供 `screencapture -l <window_number>`
// 精确定位到采集窗口，而不必依赖窗口标题（标题读取需要额外的屏幕录制授权）。
guard CommandLine.arguments.count > 1 else {
    FileHandle.standardError.write(Data("usage: window_identity.swift <owner process name>\n".utf8))
    exit(2)
}

let owner = CommandLine.arguments[1]
guard let windows = CGWindowListCopyWindowInfo(
    [.optionOnScreenOnly, .excludeDesktopElements],
    kCGNullWindowID
) as? [[String: Any]] else {
    exit(1)
}

for window in windows {
    guard let name = window[kCGWindowOwnerName as String] as? String, name == owner else { continue }

    let number = window[kCGWindowNumber as String] as? Int ?? -1
    let pid = window[kCGWindowOwnerPID as String] as? Int ?? -1
    let layer = window[kCGWindowLayer as String] as? Int ?? -1
    let bounds = window[kCGWindowBounds as String] as? [String: Any] ?? [:]
    let width = Int((bounds["Width"] as? Double ?? 0).rounded())
    let height = Int((bounds["Height"] as? Double ?? 0).rounded())

    print(
        "{\"window_number\": \(number), \"pid\": \(pid), \"width\": \(width), "
            + "\"height\": \(height), \"layer\": \(layer)}"
    )
}
