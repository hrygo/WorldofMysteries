# W1 macOS Finishing Backlog

> Status: **DEFERRED TO macOS FINISHING**  
> Artwork: `W1_WORLD_HERO`  
> Branch / PR: `feat/premium-art-production` / PR #39  
> Purpose: keep production moving when the current server environment cannot provide the preferred high-quality local image-restoration stack.

## Decision

The selected W1 composition and art direction may continue through engineering preparation on the server, but the image must **not** be declared final shipping artwork solely from server-side resize or low-quality generic upscaling.

The approved direction is intentionally more game-oriented and more overtly mysterious than the original realism-heavy W1 exploration. The final image is expected to preserve:

- late-Victorian / industrial city readability;
- strong occult game atmosphere;
- the crimson moon associated with the Evernight Goddess as a major sky motif;
- rain, fog, gaslight, wet-stone reflections and dense urban depth;
- stylized premium-game illustration rather than photographic realism.

## What may be completed on the server

The server may complete and version:

1. source-image intake and immutable source SHA256;
2. exact 16:10 composition framing / crop planning;
3. semantic and art-direction review records;
4. candidate-to-master naming and provenance scaffolding;
5. deterministic runtime derivative tooling and expected dimensions;
6. Asset Catalog target-path preparation;
7. QA checklist preparation;
8. engineering integration that does not falsely mark unfinished image quality as final.

## Deferred macOS finishing work

Perform the following on the Apple Silicon macOS workstation before final G3–G5 approval:

### F1 — Local structural repair

Inspect at 100–200% and repair only local defects:

- malformed windows, chimneys and roof geometry;
- carriage / wheel / horse anatomy errors;
- repeated or melted pedestrians;
- broken railings and balcony patterns;
- accidental pseudo-text / signage;
- malformed banners, occult marks or architectural seams;
- moon-edge, cloud-edge and smoke compositing artifacts.

Do not redesign the whole composition during this stage.

### F2 — Primary super resolution

Use one high-quality Apple-Silicon-capable super-resolution pass to create an approximately 6K working image.

Requirements:

- one principal SR pass only;
- preserve composition and moon geometry;
- avoid invented micro-text and repetitive masonry;
- avoid excessive oversharpening / haloing;
- retain atmospheric depth rather than flattening fog and smoke.

A native Apple Silicon / Metal / MPS capable tool is preferred. The exact tool is not part of the shipping contract; output quality is.

### F3 — Material restoration

At the oversampled working resolution, restore selective material detail:

- wet stone and rain sheen;
- slate roofs;
- soot-aged brick / masonry;
- black iron and oxidized brass;
- cloth, carriage and street-surface separation;
- cloud, smoke and fog transitions;
- controlled lunar glow without clipping the crimson moon.

Do not introduce new semantic objects.

### F4 — Color / luminance grade

Target a readable dark-fantasy game image rather than a crushed-black night scene.

- preserve warm gaslight separation;
- maintain readable midtones in buildings and street depth;
- keep the crimson moon visually dominant without flooding the entire frame red;
- retain cool blue-gray / charcoal environmental balance;
- avoid photographic HDR appearance;
- verify that the image remains readable under the runtime leading scrim.

### F5 — Production Master

Create the canonical:

```text
W1_WORLD_HERO_MASTER_4096x2560.png
```

The Master must be produced by controlled downsample from the finished oversampled working image, not by independently regenerating another image.

### F6 — Deterministic runtime derivatives

From the approved Master only, run:

```bash
xcrun swift docs/05_UI/artwork/tools/derive_world_artwork.swift \
  --input W1_WORLD_HERO_MASTER_4096x2560.png \
  --runtime-output wom.art.world.hero.png \
  --wide-output wom.art.world.hero.wide.png \
  --wide-anchor top
```

W1 v3 requires `--wide-anchor top`. Omitting it selects the tool's centered default and can remove the identity-bearing crimson moon. Verify `wideAnchor: top` in the derivative report; do not treat a successful export with the wrong crop as approval.

Expected outputs:

```text
wom.art.world.hero       2560×1600
wom.art.world.hero.wide  2400×900
```

### F7 — Final QA / provenance

Only after the macOS finishing stages are complete:

- finalize `W1_WORLD_HERO.qa.json`;
- finalize `W1_WORLD_HERO.provenance.json`;
- record Master + derivative SHA256 values;
- perform G3 structural QA;
- perform G4 production QA;
- perform G5 runtime / accessibility QA;
- then ingest the approved runtime assets into `Assets.xcassets`.

## Completion rule

Until F1–F7 are complete, W1 may be described as:

> **art direction approved / selected source locked / macOS finishing pending**

It must not be described as:

> **shipping artwork complete**

This deferment is a production-environment constraint, not a relaxation of the final quality bar.
