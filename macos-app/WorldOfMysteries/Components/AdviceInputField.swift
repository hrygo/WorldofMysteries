import SwiftUI

/// 命运干预 Advice 建议输入栏（严格践行 Advice ≠ Command 不变量）
public struct AdviceInputField: View {
    @Binding public var text: String
    public let targetCharacter: String
    public var onVoiceTapped: (@MainActor () -> Void)?
    public var onSubmitAdvice: (@MainActor (String) -> Void)?
    
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
                Image(systemName: "feather.pointed.fill")
                    .font(.system(size: 11))
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
                    .onSubmit {
                        submit()
                    }
                
                // 语音麦克风直发
                Button {
                    onVoiceTapped?()
                } label: {
                    Image(systemName: "mic.fill")
                        .font(.system(size: 14))
                        .foregroundStyle(Color.Mystic.brassGoldPrimary)
                        .padding(DesignTokens.Spacing.xs)
                }
                .buttonStyle(.plain)
                
                // 提交建议按钮
                Button {
                    submit()
                } label: {
                    Text("提交建议")
                        .font(Font.Mystic.caption)
                        .fontWeight(.semibold)
                        .foregroundStyle(Color.Mystic.obsidianBase)
                        .padding(.horizontal, DesignTokens.Spacing.md)
                        .padding(.vertical, DesignTokens.Spacing.xs)
                        .background(
                            text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                            ? Color.Mystic.brassGoldMuted
                            : Color.Mystic.brassGoldPrimary
                        )
                        .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.xs))
                }
                .buttonStyle(.plain)
                .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding(.horizontal, DesignTokens.Spacing.md)
            .padding(.vertical, DesignTokens.Spacing.sm)
            .background(Color.Mystic.obsidianCard)
            .clipShape(RoundedRectangle(cornerRadius: DesignTokens.Radii.sm))
            .overlay(
                RoundedRectangle(cornerRadius: DesignTokens.Radii.sm)
                    .stroke(Color.Mystic.brassGoldBorder, lineWidth: DesignTokens.Borders.standard)
            )
        }
    }
    
    private func submit() {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        onSubmitAdvice?(trimmed)
        text = ""
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
