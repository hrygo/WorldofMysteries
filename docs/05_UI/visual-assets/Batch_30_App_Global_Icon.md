# Batch 30 · App Icon & Global Brand Identity

> Task: `MAC-APP-GLOBAL-ICON`  
> Base: `main@c0c18ae31d76dac54b981e7855de87024f8d9e09`  
> Status: implementation candidate

## Decision

The user selected the first generated icon concept as the product-wide identity for **World of Mysteries / 诡秘世界**.

The identity is centered on a high-contrast antique-gold **W** and celestial ring over a dark blue mysterious-world scene. It remains aligned with the existing obsidian / brass / occult visual system while being recognizable at Dock and Finder scale.

## Integration

- Add a real macOS `AppIcon.appiconset` derived from the selected master artwork.
- Bind the Xcode target through `ASSETCATALOG_COMPILER_APPICON_NAME = AppIcon`.
- Add `wom.brand.primary` as the semantic in-app brand asset.
- Add typed `WOMBrandAsset` / `WOMBrandMark`.
- Replace the generic seal in the Sidebar product header with the shared brand mark.
- The brand image remains presentation-only and carries no domain meaning.

## Accessibility / behavior

When the Sidebar is expanded, the brand image is decorative because the adjacent text already names the product. In collapsed mode, the mark receives the accessibility label “诡秘世界”.

## Validation boundary

This batch does not claim a successful Xcode or `MACOS_APP_P0` gate until the final branch head is validated by the repository CI / macOS build environment.
