import SwiftUI

/// Native macOS peer-mode selection that keeps system Picker semantics.
/// Wide layouts use segments; narrow layouts use a menu. A missing selected value is retained
/// as a disabled menu entry, never silently replaced with the first available choice.
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
        let presentation = WOMSegmentedPresentation(options: options, selection: selection)

        Group {
            if presentation.hasAvailableSelection {
                ViewThatFits(in: .horizontal) {
                    picker(presentation)
                        .pickerStyle(.segmented)
                        .labelsHidden()
                        .fixedSize(horizontal: true, vertical: false)

                    picker(presentation)
                        .pickerStyle(.menu)
                        .labelsHidden()
                }
            } else {
                picker(presentation)
                    .pickerStyle(.menu)
                    .labelsHidden()
            }
        }
        .disabled(presentation.isEmpty)
        .accessibilityLabel(label)
        .help(presentation.displayedSelectionTitle)
    }

    private func picker(_ presentation: WOMSegmentedPresentation<Value>) -> some View {
        Picker(label, selection: $selection) {
            if !presentation.hasAvailableSelection {
                Text(presentation.placeholderTitle)
                    .tag(selection)
                    .disabled(true)
            }

            ForEach(presentation.options) { option in
                optionLabel(option)
                    .tag(option.value)
                    .help(option.title)
            }
        }
    }

    @ViewBuilder
    private func optionLabel(_ option: WOMSegmentedOption<Value>) -> some View {
        if let systemImage = option.systemImage {
            Label {
                Text(option.title)
                    .lineLimit(1)
            } icon: {
                Image(systemName: systemImage)
                    .symbolRenderingMode(.monochrome)
                    .imageScale(.small)
            }
        } else {
            Text(option.title)
                .lineLimit(1)
        }
    }
}
