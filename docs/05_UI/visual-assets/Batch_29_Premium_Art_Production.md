# Batch 29 — Premium Art Production A1–A3

> Status: ACTIVE  
> Branch: `feat/premium-art-production`  
> Delivery mode: one long-lived PR + atomic commits  
> CI policy: milestone/final only; no per-commit polling.

## Scope

This batch converts the approved A0 plan into actual premium image assets and runtime integration.

### In scope

- W1–W6 premium world/scene artworks;
- 15/15 premium Artifact artworks matching the existing `ArtifactRegistry`;
- artwork provenance and QA records;
- typed artwork registries;
- `WOMArtworkView` / scrim/crop/fallback support;
- integration into existing Ritual / Codex / Fate / Artifact visual surfaces;
- Asset Catalog and artwork-contract tests.

### Out of scope

- Engine/domain gameplay redesign;
- DB / IPC / schema changes;
- replacing Probability Die RealityKit interaction;
- reopening finished Button/Surface/Window primitives without a concrete integration need;
- using static premium art to make unfinished placeholder product routes appear complete.

## First checkpoint

A first generated art-direction board exists as a non-shipping reference candidate. Its purpose is to validate overall mood before production assets are approved.

The next atomic work is not more planning: it is actual W1/W2 scene production and UI-safe composition review.

## Quality bar

Every image must pass both art-direction and product-use tests:

1. canon/semantic fidelity;
2. distinctive silhouette / focal hierarchy;
3. material credibility;
4. controlled supernatural effect;
5. explicit quiet zone / crop reserve;
6. readability with existing Visual QA contracts;
7. no baked UI chrome/text;
8. provenance recorded;
9. runtime-size derivative exists;
10. minimum-window composition remains viable.

## W1 macOS finishing deferment

The selected W1 source may advance through server-side engineering preparation, but final image restoration is intentionally deferred to the Apple Silicon macOS workstation when the server lacks the preferred high-quality SR / local-repair stack.

Authoritative backlog: `docs/05_UI/artwork/W1_macOS_Finishing_Backlog.md`.

Until that backlog completes F1–F7, W1 is **art direction approved / selected source locked / macOS finishing pending**, not shipping-art complete. This keeps engineering throughput high without lowering G3–G5 image-quality requirements.

## Milestone before CI review

Routine commits continue without waiting on Actions. Review CI only after a meaningful milestone, preferably:

- 6/6 world scenes complete;
- 15/15 Artifact object art complete;
- typed runtime integration complete;
- artwork QA/provenance complete.
