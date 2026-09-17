# Batch 23 — Wave F Advanced Interaction & World-State Chrome

> Branch: `feat/wom-visual-system-wave-f`  
> Stacked base: `feat/wom-visual-qa-backfill-v2@8b9ab58428d05762184884c9e60b03f6e8075d71`  
> Status: IN PROGRESS

## 1. Goal

Wave F fills the remaining advanced visual primitives without replacing native macOS behavior:

1. adaptive segmented mode selection;
2. relationship-state chrome;
3. achievement / discovery seal;
4. cooldown / availability indicator;
5. Component Gallery specimens and semantic regression contracts.

The implementation inherits `Visual_QA_Contract_v1.0.md` as a hard gate. No component is accepted merely because it matches the occult/Victorian visual language.

## 2. Native macOS boundary

### Adaptive segmented selection

Use native SwiftUI `Picker` semantics:
- primary presentation: `.segmented` for a small fixed set of peer choices;
- narrow-width fallback: `.menu` through `ViewThatFits`;
- keyboard / accessibility / selection semantics remain native;
- no hand-built row of Buttons that imitates `NSSegmentedControl`.

### Tabs

Wave F does not create a fake app-level tab framework. App/scene navigation continues to use existing macOS/SwiftUI navigation. The segmented primitive is only for local peer mode switching inside a component or inspector.

## 3. New primitives

### `WOMAdaptiveSegmentedPicker`
- typed option model;
- compact title + optional SF Symbol;
- native segmented primary form;
- menu fallback under horizontal pressure;
- label and help/accessibility support;
- long-label stress specimen.

### `WOMRelationBadge`
Semantic roles only; no domain persistence:
- trusted;
- aligned;
- neutral;
- wary;
- hostile.

Rules:
- relation color is secondary semantics, never the only signal;
- each role has icon + readable label + border/chrome difference;
- supports optional short detail, but not a hidden relationship engine.

### `WOMAchievementSeal`
Presentation states:
- locked;
- discovered;
- completed.

Rules:
- 11pt minimum metadata;
- locked state remains readable, not low-opacity illegible;
- completion uses icon/geometry in addition to color;
- long achievement names wrap instead of shrinking.

### `WOMCooldownIndicator`
Static presentation of externally supplied availability state:
- ready;
- cooling(progress 0...1);
- locked.

Rules:
- no internal wall-clock/game timer;
- no infinite animation;
- domain/runtime owns the actual cooldown fact;
- UI renders provided progress/time label only;
- readable percentage / remaining text uses stable foreground token.

## 4. Visual QA acceptance

All new primitives must satisfy:
- normal readable text >= 4.5:1 final contrast;
- important non-text affordances >= 3:1;
- body >=13pt, metadata >=11pt;
- no 9pt semantic text;
- long Chinese / English labels wrap or fall back;
- no overlap at the 960x640 app baseline;
- `Differentiate Without Color`, `Increase Contrast`, `Reduce Motion`, `Reduce Transparency` have stable behavior where relevant;
- no color-only status.

## 5. Delivery sequence

1. Persist Wave F plan + Capsule + Living Plan update.
2. Implement adaptive segmented picker.
3. Implement relation badge.
4. Implement achievement seal.
5. Implement cooldown indicator.
6. Add Visual System Gallery specimens including long-label/narrow-layout stress.
7. Add semantic contract tests.
8. Static diff/capsule audit.
9. After predecessor #31 merges, retarget to `main`, reissue Capsule base if required, then run one final `MACOS_APP_P0`.

## 6. Non-goals

- no Engine/DB/IPC/schema changes;
- no fake relationship or achievement domain data;
- no custom replacement for system tabs/windows;
- no large bitmap UI assets;
- no new animation loops;
- no weakening of Visual QA rules to preserve decorative styling.
