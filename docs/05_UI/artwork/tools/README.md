# Artwork Post-Processing Tools

## derive_world_artwork.swift

Deterministic World / Scene derivative generator for an already approved `4096×2560` Production Master.

It performs **no generative operation**.

Outputs:

- full-frame `2560×1600` runtime PNG;
- centered semantic-safe `4096×1536` wide crop, downsampled to `2400×900`;
- SHA256 report for input and both derivatives.

For W1 the centered vertical wide crop is valid because the locked focal Y range is `0.28–0.72`, while the 8:3 crop preserves approximately Y `0.20–0.80`.

Usage:

```bash
xcrun swift docs/05_UI/artwork/tools/derive_world_artwork.swift \
  --input /path/W1_MASTER_4096x2560.png \
  --runtime-output /tmp/wom.art.world.hero.png \
  --wide-output /tmp/wom.art.world.hero.wide.png
```

Self-test:

```bash
xcrun swift docs/05_UI/artwork/tools/derive_world_artwork.swift --self-test
```

The JSON emitted to stdout is intended to populate the provenance record.

### Boundary

Use this tool only after G0–G3 have passed.

It must not be used to turn a rejected candidate into a shipping asset by simple resize.
