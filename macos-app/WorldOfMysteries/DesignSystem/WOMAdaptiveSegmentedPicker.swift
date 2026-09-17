import SwiftUI

/// Typed option used by `WOMAdaptiveSegmentedPicker`.
///
/// The option is presentation metadata only. The bound `value` remains the caller's source of
/// truth and is never persisted by the visual-system component.
public struct WOMSegmentedOption<Value: Hashable>: Identifiable {
    public let value: Value
    public let title: String
    public let systemImage: String?

    public init(
        value: Value,
        title: String,
        systemImage: String? = nil
    ) {
        self.value = value
        self.title = title
        self.systemImage = systemImage
    }

    public var id: Value { value }
}

/// Native macOS peer-mode selection that keeps system Picker semantics.
///
/// - Wide layout: SwiftUI `.segmented` picker.
/// - Narrow layout: SwiftUI `.menu` picker selected through `ViewThatFits`.
///
/// This component intentionally does not recreate `NSSegmentedControl` with a row of Buttons.
/// Keyboard, focus, VoiceOver and selection semantics remain owned by the native `Picker`.
public struct WOMAdaptiveSegmentedPicker<Value: Hashable>: View {
    public let label: String
    @Binding public var selection: Value
    public let options: [WOMSegmentedOption<Value>]

    public init(
        _ label: String,
        selection: Binding<Value>,
        options: [WOMSegmentedOption<Value>]
    ) {
        self.label = label
        self._selection = selection
        self.options = options
    }

    public var body: some View {
        ViewThatFits(in: .horizontal) {
            picker
                .pickerStyle(.segmented)
                .labelsHidden()

            picker
                .pickerStyle(.menu)
                .labelsHidden()
        }
        .accessibilityLabel(label)
    }

    private var picker: some View {
        Picker(label, selection: $selection) {
            ForEach(options) { option in
                optionLabel(option)
                    .tag(option.value)
            }
        }
    }

    @ViewBuilder
    private func optionLabel(_ option: WOMSegmentedOption<Value>) -> some View {
        if let systemImage = option.systemImage {
            Label(option.title, systemImage: systemImage)
        } else {
            Text(option.title)
        }
    }
}
