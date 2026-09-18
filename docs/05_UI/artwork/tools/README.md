# Artwork Post-Processing Tools

## derive_world_artwork.swift

Deterministic World / Scene derivative generator for an already approved `4096×2560` Production Master.

It performs **no generative operation**.

Outputs:

- full-frame `2560×1600` runtime PNG;
- semantic `4096×1536` wide crop, downsampled to `2400×900`;
- SHA256 report for input and both derivatives, including the selected wide anchor.

The default wide anchor is `center`. An Image Contract may require `top` or `bottom` when an identity-bearing subject would otherwise be cropped out. W1 Contract v3 requires `top` so the crimson moon remains visible.

Usage:

```bash
xcrun swift docs/05_UI/artwork/tools/derive_world_artwork.swift \
  --input /path/W1_MASTER_4096x2560.png \
  --runtime-output /tmp/wom.art.world.hero.png \
  --wide-output /tmp/wom.art.world.hero.wide.png \
  --wide-anchor top
```

Self-test:

```bash
xcrun swift docs/05_UI/artwork/tools/derive_world_artwork.swift --self-test
```

The JSON emitted to stdout is intended to populate the provenance record.

### Boundary

Use this tool only after G0–G3 have passed. The anchor must come from the locked Image Contract; do not choose it ad hoc during export.

It must not be used to turn a rejected candidate into a shipping asset by simple resize.


## measure_world_composition.swift

Deterministic composition metrics for World / Scene candidates.

Measures:

- mean luminance in the left 35% quiet zone;
- mean luminance-gradient density in the left 35% quiet zone;
- the same metrics in the locked focus region x=55–78%, y=28–72%;
- quiet/focus luminance and gradient ratios;
- normalized centroid of the brightest 0.5% pixels.

Usage:

```bash
xcrun swift docs/05_UI/artwork/tools/measure_world_composition.swift \
  --input /path/candidate.png
```

Self-test:

```bash
xcrun swift docs/05_UI/artwork/tools/measure_world_composition.swift --self-test
```

These metrics are **supporting evidence for G2**, not a replacement for blind semantic or human visual QA.
