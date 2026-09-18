# Artifact object finishing pipeline v1.0

> The executable checkpoint for the 15 Artifact objects: approved source → one super-resolution
> pass → 2048×2048 Master → same-Master runtime derivatives → Asset Catalog → QA / provenance.
> It does not approve shipping, Canon or runtime behaviour.

## Why Artifacts have their own pipeline

An Artifact object is a square, single-object image with a `detail` / `thumbnail` runtime
contract. World and Scene images are 16:10 landscapes with a `runtime` / `wide` contract, and
their pipeline lives in `tools/finish_world_artwork.py`. Sharing one tool would mean two
different crop rules, two different master sizes and two different derivative sets behind one
command name, so the object path is a separate, explicit order.

Both paths share the same grade profile (`subtle-illustration-v1`) and the same evidence
discipline, so the Premium Art set keeps one reproducible look without pretending the two asset
classes are the same asset class.

## Order

`tools/finish_artifact_artwork.py`:

| Step | Operation | Generative |
| --- | --- | --- |
| `square-crop` | Deterministic centred 1:1 safety crop of the approved source | no |
| `sr` | One Real-ESRGAN RRDBNet ×4 pass on Apple Silicon MPS (tile 512, overlap 32) | one learned pass |
| `grade` | Material restoration and colour / luminance grade in float space | no |
| `master` | Controlled Lanczos downsample to the 2048×2048 Artifact Master; refuses to upscale | no |
| `derive` | 1024×1024 `.detail` and 512×512 `.thumbnail` from that same master | no |
| `fidelity` | MAE / luminance correlation / edge-structure correlation against the approved source crop | no |
| `publish-catalog` | Publishes only the two runtime derivatives as imagesets; never the Master | no |
| `record` | Fail-closed QA and provenance assembly from byte-verified stage reports | no |
| `contact-sheet` | Small preview sheet for the human 96×96 legibility read | no |

Contract sizes come from `delivery/approved_sources.json` → `production_contract`:
`artifact_master_baseline` 2048×2048, `artifact_detail` 1024×1024, `artifact_thumbnail` 512×512,
with `one_source_per_image`, `baked_text_allowed: false`,
`independent_derivative_generation_allowed: false` and `macos_finishing_required: true`.

## The Master is a finished Master, not a native generation

The widest approved object source is 1371px on its short edge and most are 1254×1254, so the
2048×2048 Master is a finished / super-resolved Master. The provenance record states
`master_is_native_generation: false` and carries that note explicitly. Non-square sources
(A02 1222×1287; A11/A12/A14 1370-1371×1148) are cropped to the largest centred square; nothing is
stretched and no canvas is invented. The crop rectangle is a pure function of the decoded size and
is recorded per object.

## Determinism

The pipeline is byte-reproducible: the same source, weights and parameters produce the same PNG
bytes.

One defect had to be fixed to get there. The embedded sRGB profile is generated through
LittleCMS, which stamps the ICC profile `date/time` tag with the wall clock, so two identical runs
differed in the profile's seconds field — and therefore in every output's SHA256. The tool now
normalises that tag to a fixed instant (`FIXED_PROFILE_DATE`) before writing any output. Without
that normalisation a recorded derivative hash could not be reproduced, and the
Catalog-versus-derivative check in `record` would fail on a re-run.

The learned pass is the only non-deterministic-looking step in principle; measured on this host it
is deterministic once the profile tag is normalised (identical IDAT bytes and identical
`pixel_sha256` for repeated runs, verified in
`tools/tests/test_finish_artifact_artwork.py`).

## Colour management

Every finishing output is PNG with an explicit sRGB ICC profile. All 15 approved sources arrive as
RGB PNGs with no embedded profile, so the tagging is part of the fix rather than a cosmetic
detail, and the intake bundle keeps the originals untouched.

## Evidence, and what stays open

`record` refuses to write a record unless the whole chain is present and byte-identical to its
stage reports, the fidelity verdict passed, the derivatives came from that same Master at the
contract sizes, and the Asset Catalog payloads match the derivatives. A gate can only become
`PASSED` with its own evidence:

- **G0** needs a finished-master semantic read and no baked typography;
- **G1** needs a verified primary form claim *and* a recorded consistency note, otherwise it stays
  open — visual approval is not Canon verification;
- **G2** needs the recorded crop and a subject-safety read;
- **G3** needs a 25/100/200% structural inspection with no defects;
- **G4** needs the Master, the same-Master derivatives and byte-identical catalog payloads;
- **G5** needs captured runtime and accessibility evidence. No Artifact capture exists yet, so G5
  is open for all 15.

A missing evidence file is an open gate — never a pass and never a crash.

Open items after this checkpoint are tracked in `delivery/approved_sources.json` (`pending`) and
recorded per object in each `.qa.json`: the A02/A03 baked-lettering decision, Canon review for the
twelve objects without primary form evidence, and the Artifact runtime captures.

## Running it

The workbench driver is local and git-ignored; the commands it runs are the committed ones:

```sh
python3 docs/05_UI/artwork/tools/finish_artifact_artwork.py square-crop \
  --input <approved-source>/source.png --output work/A01_01_square.png

python3 docs/05_UI/artwork/tools/finish_artifact_artwork.py sr \
  --input work/A01_01_square.png --output work/A01_02_sr.png \
  --weights RealESRGAN_x4plus.pth --downstream 4096x4096

python3 docs/05_UI/artwork/tools/finish_artifact_artwork.py record \
  --task A01 --work-dir work \
  --inspection docs/05_UI/artwork/qa/G3_artifact_structural_inspection_2026-09-19.json \
  --catalog-root macos-app/WorldOfMysteries/Assets.xcassets \
  --qa docs/05_UI/artwork/qa/A01_ARRODES_MIRROR.qa.json \
  --provenance docs/05_UI/artwork/provenance/A01_ARRODES_MIRROR.provenance.json
```

`--require-complete` turns an incomplete record into a non-zero exit code for scripts and gates.
The Real-ESRGAN weights are not committed; the SHA256 actually used is recorded in the provenance
record. Run the tool with an interpreter that has `numpy`, `Pillow` and `torch`.

```sh
python3 -m unittest discover -s docs/05_UI/artwork/tools/tests -v
```

## Boundaries

Use it only on an approved, locked source. It must not be used to rescue a rejected composition, to
add a second super-resolution pass, to upscale a master from a smaller working image, or to
generate a derivative independently of the Master. Masters are never published into the Asset
Catalog and never loaded by runtime selectors. `record` describes the bytes that exist; it never
substitutes for the human art-direction decision that approved the source.
