# Artwork Post-Processing Tools

## finish_world_artwork.py

Deterministic macOS finishing pipeline for an approved World / Scene source. It implements the
`postprocess.order` that the image contracts already lock, so finishing is a reproducible
sequence instead of undocumented desktop edits.

| Subcommand | Operation | Generative |
| --- | --- | --- |
| `crop` | Exact contract crop of the approved source (`1,1,1585,991` → 1584×990 for the six scene sources) | no |
| `repair` | Masked local structural repair by copying a nearby region and feathering the seam | no |
| `sr` | One Real-ESRGAN RRDBNet ×4 pass on Apple Silicon MPS (tile 512, overlap 32) to the oversampled working image | one learned pass |
| `grade` | Material restoration and colour / luminance grade in float space (profile `subtle-illustration-v1`) | no |
| `master` | Controlled Lanczos downsample to the 4096×2560 Production Master; refuses to upscale | no |
| `fidelity` | MAE / luminance correlation / edge-structure correlation against the approved source crop, with a pass/fail verdict | no |
| `record` | Assemble the tracked QA and provenance records from byte-verified stage reports | no |
| `surface` | Verify that a window capture really contains the shipped asset (scale search + normalised cross-correlation) | no |

Every output is written as PNG with an explicit sRGB ICC profile. The approved sources carry no
ICC tag, so the tagging is part of the fix rather than a cosmetic detail.

### Requirements

`torch` with MPS, `numpy` and `Pillow` in some Python environment. The Real-ESRGAN weights are
**not** committed; pass `--weights` and the SHA256 actually used is recorded in the provenance
record (`4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1` for
`RealESRGAN_x4plus.pth`, the weights used for the six approved scene sources).

### Typical run for one scene

```bash
python3 docs/05_UI/artwork/tools/finish_world_artwork.py crop \
  --input <approved-source>/source.png --output W1_01_crop_1584x990.png \
  --rect 1,1,1585,991 --width 1584 --height 990

python3 docs/05_UI/artwork/tools/finish_world_artwork.py sr \
  --input W1_01_crop_1584x990.png --output W1_02_sr_6336x3960.png \
  --weights RealESRGAN_x4plus.pth --downstream 6144x3840

python3 docs/05_UI/artwork/tools/finish_world_artwork.py grade \
  --input W1_02_sr_6336x3960.png --output W1_03_grade_6336x3960.png

python3 docs/05_UI/artwork/tools/finish_world_artwork.py master \
  --input W1_03_grade_6336x3960.png --output W1_MASTER_4096x2560.png

python3 docs/05_UI/artwork/tools/finish_world_artwork.py fidelity \
  --reference W1_01_crop_1584x990.png --candidate W1_MASTER_4096x2560.png

xcrun swift docs/05_UI/artwork/tools/derive_world_artwork.swift \
  --input W1_MASTER_4096x2560.png \
  --runtime-output wom.art.world.hero.png \
  --wide-output wom.art.world.hero.wide.png --wide-anchor top
```

### Recording QA and provenance

```bash
python3 docs/05_UI/artwork/tools/finish_world_artwork.py record \
  --task W1 --work-dir <stage-output-dir> \
  --source <approved-source>/source.png \
  --catalog-root macos-app/WorldOfMysteries/Assets.xcassets \
  --inspection docs/05_UI/artwork/qa/G3_structural_inspection_2026-09-18.json \
  --runtime-evidence <stage-output-dir>/W1_runtime_evidence.json \
  --qa docs/05_UI/artwork/qa/W1_WORLD_HERO.qa.json \
  --provenance docs/05_UI/artwork/provenance/W1_WORLD_HERO.provenance.json
```

`record` is fail-closed. It refuses to write a record unless the approved source, crop, one SR
pass, grade, master and both derivatives are present and byte-identical to their stage reports,
and unless the derivatives came from that same master with the anchor the scene review recorded.
A gate can only become `PASSED` with its own evidence:

- **G3** needs a 25/100/200% inspection record with no found defects;
- **G4** needs the Asset Catalog payload to be byte-identical to the finished derivative;
- **G5** needs captured window checks at 960×640, 1180×760, 2560×1600 and 2400×900 plus captured
  Increased Contrast and Reduce Transparency states, and no measured contrast below 4.5:1 for
  primary text or 7:1 for important long copy.

A missing evidence file is an open gate — never a pass, never a crash. `--require-complete` turns
an incomplete record into a non-zero exit code for scripts and gates.

### Runtime evidence for G5

G5 is only as trustworthy as its screenshots, so the evidence file must name captures and the
tool re-verifies them instead of trusting prose. Raw claims cannot pass G5.

```json
{
  "captured_at": "2026-09-18",
  "captures": [{ "file": "W1_window_1180x760.png", "sha256": "<digest of that PNG>" }],
  "window_checks": {
    "960x640":   { "capture": "W1_window_960x640.png",   "text_legible": true, "identity_visible": true },
    "1180x760":  { "capture": "W1_window_1180x760.png",  "text_legible": true, "identity_visible": true },
    "2560x1600": { "capture": "W1_window_2560x1600.png", "text_legible": true, "identity_visible": true },
    "2400x900":  { "capture": "W1_window_2400x900.png",  "text_legible": true, "identity_visible": true }
  },
  "accessibility_checks": {
    "Increased Contrast":  { "capture": "W1_increased_contrast.png", "text_legible": true, "artwork_readable": true },
    "Reduce Transparency": { "capture": "W1_reduce_transparency.png", "text_legible": true, "artwork_readable": true }
  },
  "contrast": {
    "measurements": [
      { "kind": "text_primary",   "capture": "W1_window_1180x760.png", "region": [40, 120, 320, 90] },
      { "kind": "important_copy", "capture": "W1_window_1180x760.png", "region": [40, 240, 420, 120] }
    ]
  }
}
```

Capture file names are resolved relative to the evidence file; absolute paths are rejected.
Every capture is re-hashed against its recorded digest. Contrast ratios are **recomputed** by the
tool from the named regions (WCAG 2.2 relative luminance, p95 as ink against p05 as backing), so a
number typed into the evidence file is ignored. A missing capture, a changed capture, a missing
region or a low ratio keeps G5 pending with an explicit reason.

### Boundary

Use it only on an approved, locked source. It must not be used to rescue a rejected composition,
to add a second super-resolution pass, or to produce a master from a smaller image. `record`
describes the bytes that exist; it never substitutes for the human art-direction decision that
approved the source in the first place.

### Tests

```bash
python3 -m unittest discover -s docs/05_UI/artwork/tools/tests -v
```

The suite builds a miniature finishing chain and asserts the refusals that make the evidence
chain meaningful: a modified stage output, a wrong wide anchor, a catalog payload that no longer
matches the derivative, and runtime claims that name no verifiable capture.

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
