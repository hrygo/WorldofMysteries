# Component Review — Selector Recovery and Feedback Content

Status: implementation increment; native rendering/VoiceOver review has separate evidence.
Baseline: `f07a924a82f869a8b810c1efe3128d6d2cf3a3e4`, PR #39.
Scope: small-control presentation only. Approved scene sources and Artifact work are untouched.

## Reproduced gaps

- Adaptive Picker passed caller options directly to `ForEach`; duplicate values produced duplicate identities, and removed/empty options left the current selection without a matching tag.
- Empty-state/banner accepted a non-nil but whitespace-only action title, allowing a button without a usable name.
- Loading feedback replaced the combined accessibility label with a title-only label, omitting its message from the explicit description.
- Banner's horizontal candidate could compress long content rather than select its intended vertical fallback.

## Changes

- `WOMControlContent.swift` holds pure presentation policies. The public `WOMSegmentedOption` initializer/value/title API is preserved, now independently testable without SwiftUI.
- Options are resolved in stable caller order: the first usable label for each value wins; blank-label choices are excluded. Same label/different values remain separate choices.
- Missing selection appears as a disabled native-menu entry with its original tag. An empty usable list disables the control. Restoring options restores the original selection display, without writing the binding or picking a replacement.
- Valid selection still uses native segmented/menu Picker adaptation; full labels remain available as help text. No custom button-based selection engine is introduced.
- Feedback actions require both a nonblank title and a handler. Empty messages do not create blank text rows. Loading descriptions retain their message; descriptive content and native action buttons remain separate accessibility elements.
- Banner checks its horizontal intrinsic width before falling back to vertical layout.
- Gallery adds an interactive 220-point recovery specimen: remove/restore a selected option, empty the list, duplicate identities, long feedback, retry counter and a deliberately blank action label.

## Verification

- Linux Swift 6.2.1: actual production `WOMControlContent.swift` and `ControlContentReviewTests.swift` compiled unmodified in an isolated validation package. **11 tests passed**, including five whitespace cases.
- Swift parser accepted all seven changed/new Swift source/test files. Parsing is not SwiftUI type checking.
- Native tests added: binding is not written during view construction; production wiring guards; banner render bounds at 220/280/420 points. These require macOS CI; local Linux results do not certify them.
- Existing native Picker, overlay, icon, motion and contrast guards are retained, not weakened.

Before declaring visual acceptance, use the Gallery on macOS to verify keyboard selection, the unavailable entry, option restoration and VoiceOver reading order. Native render bounds do not prove VoiceOver behavior or complete accessibility compliance.

No final Work Receipt, artwork approval, or merge authorization is issued by this increment.

## Sources

- [Apple Picker semantics and typed selection tags](https://developer.apple.com/documentation/swiftui/picker)
- [Apple accessibility child behavior](https://developer.apple.com/documentation/swiftui/accessibilitychildbehavior)
- [Repository Visual QA contract](Visual_QA_Contract_v1.0.md)
