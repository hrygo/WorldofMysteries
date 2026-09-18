import SwiftUI

private struct AdviceFocusRequestIDKey: EnvironmentKey {
    static let defaultValue: Int = 0
}

extension EnvironmentValues {
    var adviceFocusRequestID: Int {
        get { self[AdviceFocusRequestIDKey.self] }
        set { self[AdviceFocusRequestIDKey.self] = newValue }
    }
}

/// 命运干预 Advice 建议输入栏（严格践行 Advice ≠ Command 不变量）
public struct AdviceInputField: View {
    @Binding public var text: String
    public let targetCharacter: String
    public var onVoiceTapped: (@MainActor () -> Void)?
    public var onSubmitAdvice: (@MainActor (String) -> Void)?

    @Environment(\.adviceFocusRequestID) private var adviceFocusRequestID
    @Environment(\.colorSchemeContrast) private var colorSchemeContrast
    @Environment(\.isEnabled) private var isEnabled
    @FocusState private var isTextFieldFocused: Bool
    
    public init(
        text: Binding<String>,
        targetCharacter: String = "克莱恩·莫雷蒂",
        onVoiceTapped: (@MainActor () -> Void)? = nil,
        onSubmitAdvice: (@MainActor (String) -> Void)? = nil
    ) {
        self._text = text
        self.targetCharacter = targetCharacter
        self.onVoiceTapped = onVoiceTapped
        self.onSubmitAdvice = onSubmitAdvice
    }
    
    public var body: some View {
        VStack(alignment: .leading, spacing: DesignTokens.Spacing.xs) {
            // 语义提示：Advice ≠ Command
            HStack(spacing: DesignTokens.Spacing.xs) {
                WOMIcon(system: .advice, size: .compact)
                    .foregroundStyle(Color.Mystic.brassGoldPrimary)
                
                Text("建议干预（Advice to \(targetCharacter) · 决策权归人物所有）")
                    .font(Font.Mystic.caption)
                    .foregroundStyle(Color.Mystic.textSecondary)
                
                Spacer()
            }
            
            // 输入容器
            HStack(spacing: DesignTokens.Spacing.sm) {
                TextField("轻声提供你的建议，例如：“不要回头看镜子...”", text: $text)
                    .textFieldStyle(.plain)
                    .font(Font.Mystic.bodyMedium)
                    .foregroundStyle(Color.Mystic.textPrimary)
                    .focused($isTextFieldFocused)
                    .accessibilityLabel("给\(targetCharacter)的建议")
                    .onSubmit {
                        submit()
                    }
                
                // 语音建议：统一 icon-only button geometry / focus / disabled / Reduce Motion。
                Button {
                    onVoiceTapped?()
                } label: {
                    WOMIcon(system: .voiceAdvice, size: .compact)
                        .foregroundStyle(Color.Mystic.brassGoldPrimary)
                }
                .buttonStyle(WOMIconButtonStyle(.secondary))
                .disabled(onVoiceTapped == nil)
                .accessibilityLabel("语音输入建议")
                .help("语音输入建议")
                
                // 提交建议：统一主行动按钮，不再局部复制按钮色彩与按压规则。
                Button("提交建议") {
                    submit()
                }
                .buttonStyle(WOMButtonStyle(.primary))
                .disabled(isSubmitDisabled)
                .accessibilityHint("将建议提交给\(targetCharacter)，人物仍保留最终决策权")
            }
            .padding(.horizontal, DesignTokens.Spacing.md)
            .padding(.vertical, DesignTokens.Spacing.sm)
            .background(Color.Mystic.obsidianCard)
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
            .overlay(
                RoundedRectangle(cornerRadius: DesignTokens.Radii.sm, style: .continuous)
                    .stroke(inputBorderColor, lineWidth: inputBorderWidth)
            )
            .shadow(
                color: isTextFieldFocused
                    ? Color.Mystic.brassGoldGlow.opacity(0.22)
                    : Color.clear,
                radius: isTextFieldFocused ? 4 : 0
            )
        }
        .onChange(of: adviceFocusRequestID) { _, _ in
            isTextFieldFocused = true
        }
    }
    
    private var isSubmitDisabled: Bool {
        AdviceDraftSubmission.payload(
            from: text,
            isEnabled: isEnabled,
            hasHandler: onSubmitAdvice != nil
        ) == nil
    }

    private var inputBorderColor: Color {
        if colorSchemeContrast == .increased {
            return isTextFieldFocused ? Color.Mystic.textPrimary : Color.Mystic.textGoldAccent
        }
        return isTextFieldFocused ? Color.Mystic.brassGoldPrimary : Color.Mystic.brassGoldBorder
    }

    private var inputBorderWidth: CGFloat {
        isTextFieldFocused || colorSchemeContrast == .increased
            ? DesignTokens.Borders.heavy
            : DesignTokens.Borders.standard
    }

    private func submit() {
        AdviceDraftSubmission.submit(
            readDraft: { text },
            writeDraft: { text = $0 },
            isEnabled: isEnabled,
            handler: onSubmitAdvice
        )
    }
}

#Preview("Advice Input Field") {
    ZStack {
        Color.Mystic.obsidianBase.ignoresSafeArea()
        AdviceInputField(text: .constant("小心身后的红月，屏住呼吸离开房间。"))
            .padding(DesignTokens.Spacing.xl)
            .frame(width: 540)
    }
}
