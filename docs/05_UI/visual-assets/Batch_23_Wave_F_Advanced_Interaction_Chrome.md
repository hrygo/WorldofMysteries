# Batch 23 — Wave F Advanced Interaction & World-State Chrome

> Branch: `feat/wom-visual-system-wave-f`  
> PR: #32  
> Stacked base: `feat/wom-visual-qa-backfill-v2@8b9ab58428d05762184884c9e60b03f6e8075d71`  
> Status: IMPLEMENTATION COMPLETE / RETARGET + FINAL CI PENDING

## 1. Goal

Wave F fills the remaining advanced visual primitives without replacing native macOS behavior:

1. adaptive segmented mode selection;
2. relationship-state chrome;
3. achievement / discovery seal;
4. cooldown / availability indicator;
5. Component Gallery specimens and semantic regression contracts.

The implementation inherits `Visual_QA_Contract_v1.0.md` as a hard gate.

## 2. Native macOS boundary

### Adaptive segmented selection

Implemented with native SwiftUI `Picker` semantics:
- wide presentation: `.segmented`;
- segmented branch preserves intrinsic horizontal width with `fixedSize(horizontal: true)` so long labels do not silently compress below readable width;
- narrow-width fallback: `.menu` through `ViewThatFits`;
- keyboard / focus / VoiceOver / selection semantics remain native;
- no Button row and no AppKit `NSSegmentedControl` bridge.

### Tabs

Wave F does not create an app-level tab framework. App/scene navigation remains existing SwiftUI/macOS navigation. The segmented primitive is only for local peer mode switching inside a component or inspector.

## 3. Implemented primitives

### `WOMAdaptiveSegmentedPicker`

- typed `WOMSegmentedOption<Value>`;
- title + optional SF Symbol;
- native segmented primary form;
- intrinsic-width measurement before fallback;
- menu fallback under horizontal pressure;
- system accessibility semantics preserved.

### `WOMRelationBadge`

Presentation-only roles:
- trusted;
- aligned;
- neutral;
- wary;
- hostile.

Implementation:
- icon + readable text + border geometry;
- `Differentiate Without Color` adds role-specific dash patterns;
- Increased Contrast strengthens border;
- long names/details wrap;
- no relationship score or persistence.

### `WOMAchievementSeal`

States:
- locked;
- discovered;
- completed.

Implementation:
- 11pt metadata baseline;
- locked state remains readable;
- icon + text + geometry in every state;
- completed may use subtle gold texture but text remains stable foreground;
- long achievement names/details wrap.

### `WOMCooldownIndicator`

Externally supplied states:
- ready;
- cooling(progress, remainingLabel);
- locked(reason).

Implementation:
- clamped externally supplied progress;
- native `ProgressView` for determinate progress;
- no `Timer`, `Task.sleep`, wall-clock truth, or `repeatForever`;
- domain/runtime owns actual availability;
- icon + status text ensure non-color-only semantics.

## 4. Gallery regression surface

`ComponentGalleryVisualSystemSection.swift` now includes:
- normal-width adaptive segmented specimen;
- 220pt narrow Inspector specimen to force segmented → menu fallback;
- all 5 relationship roles;
- long hostile Chinese/English label stress;
- locked / discovered / completed achievement states;
- long achievement title stress;
- ready / cooling / locked cooldown states;
- explicit statement that these primitives do not create domain facts.

## 5. Automated contracts

`VisualAdvancedInteractionContractTests.swift` locks:
- native Picker implementation;
- segmented + menu fallback;
- intrinsic-width preservation;
- no Button imitation / NSViewRepresentable bridge;
- relationship / achievement state coverage;
- icon + text + geometry and Differentiate Without Color support;
- metadata not falling below 11pt;
- cooldown owning no timer/task/animation loop;
- Gallery narrow/long-label specimens;
- no SQLite / EngineIPCClient / world.db / URLSession coupling.

## 6. Static diff audit

Relative to predecessor #31 head:
- ahead 8 / behind 0 at first implementation audit;
- only Wave F Capsule/docs, two DesignSystem source files, Gallery and one test file are changed;
- no Engine / DB / IPC / schema / `.github` / `.hacf` changes;
- no production-domain bindings are fabricated.

Current head has additional atomic audit/test/doc commits but remains in the same authorized file set.

## 7. Visual QA acceptance

Implementation is designed to satisfy:
- readable text >= 4.5:1 final contrast;
- important non-text affordances >= 3:1;
- body >=13pt, metadata >=11pt;
- no 9pt semantic text;
- long Chinese / English labels wrap or fall back;
- no color-only state;
- no overlap at the 960x640 app baseline;
- no new infinite animation loops.

## 8. Remaining steps

1. Keep #32 Draft while #31 remains unmerged.
2. After #31 merges, retarget #32 to `main`.
3. Reissue/reconcile Capsule base against the new `main` SHA.
4. Re-read stacked diff to ensure only Wave F changes remain.
5. Mark Ready and run one final `MACOS_APP_P0`.
6. If CI fails, only atomic log-driven fixes are allowed.
7. Do not merge without explicit authorization.
