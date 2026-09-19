# Scene finishing delivery — W1–W6 (2026-09-19)

## What this record covers

The six approved scene sources reached the macOS finishing checkpoint and their runtime derivatives
are published in the app Asset Catalog. This record describes the delivered bytes and the evidence
that supports them. It is **not** a shipping approval, and it does not assert literal Canon
architecture: the metaphor framing recorded in
[the scene approval update](World_Scene_Approval_Update_2026-09-18.md) still stands.

## Delivered runtime bytes

Every payload below was re-hashed on disk after publication and matches both the Asset Catalog and
its QA record. Masters are the intermediate 4096×2560 production images; their digests are recorded
in the QA / provenance records but the masters themselves are not committed.

| Task | Runtime asset | Output | SHA256 (first 16) | Wide asset | Output | SHA256 (first 16) |
| --- | --- | --- | --- | --- | --- | --- |
| W1 | `wom.art.world.hero` | 2560×1600 | `7cc7e998df8edce4` | `wom.art.world.hero.wide` | 2400×900 | `c7537eb89428c82a` |
| W2 | `wom.art.world.gray-fog` | 2560×1600 | `14518e8ea435b374` | `wom.art.world.gray-fog.wide` | 2400×900 | `2671bfc20655d48a` |
| W3 | `wom.art.scene.ritual-altar` | 2560×1600 | `2b851c67f7d1b662` | `wom.art.scene.ritual-altar.wide` | 2400×900 | `bf184396701b6ed0` |
| W4 | `wom.art.scene.codex-archive` | 2560×1600 | `678289b34f66eb7a` | `wom.art.scene.codex-archive.wide` | 2400×900 | `721e190c4769faef` |
| W5 | `wom.art.scene.fate-worldline` | 2560×1600 | `df077bd493509a35` | `wom.art.scene.fate-worldline.wide` | 2400×900 | `59444ef0d9ade9b2` |
| W6 | `wom.art.scene.artifact-vault` | 2560×1600 | `e4261b35fae20bcb` | `wom.art.scene.artifact-vault.wide` | 2400×900 | `96b52da25f212270` |

The full digests, the pixel digests and the photometry of each master are in
[`../qa/`](../qa/) and [`../provenance/`](../provenance/). The nine scene originals are committed
under [`../sources/approved-2026-09-18-r2/`](../sources/approved-2026-09-18-r2/), so an earlier
transport step is no longer outstanding.

## Why the records can be trusted

`record` is fail-closed: it refuses to write a QA / provenance record unless the approved source
crop, one super-resolution pass, the grade, the master and both derivatives are present and
byte-identical to their stage reports, and unless both derivatives came from that same master with
the anchor the scene review recorded. The Asset Catalog payload must also be byte-identical to the
derivative.

Re-running that command against the delivered bytes reproduces every record **without a single
changed byte**, which is what makes the chain auditable rather than asserted:

```sh
python3 docs/05_UI/artwork/tools/finish_world_artwork.py record \
  --task W1 --work-dir <stage-output-dir> \
  --source docs/05_UI/artwork/sources/approved-2026-09-18-r2/sources/S01_WORLD_HERO/source.png \
  --catalog-root macos-app/WorldOfMysteries/Assets.xcassets \
  --inspection docs/05_UI/artwork/qa/G3_structural_inspection_2026-09-18.json \
  --qa docs/05_UI/artwork/qa/W1_WORLD_HERO.qa.json \
  --provenance docs/05_UI/artwork/provenance/W1_WORLD_HERO.provenance.json
```

## Fidelity against the approved source

| Task | MAE (0–255) | Luminance correlation | Edge-structure correlation | Verdict |
| --- | --- | --- | --- | --- |
| W1 | 7.255 | 0.9933 | 0.9792 | passed |
| W2 | 8.258 | 0.9961 | 0.9784 | passed |
| W3 | 6.581 | 0.9931 | 0.9803 | passed |
| W4 | 5.512 | 0.9930 | 0.9809 | passed |
| W5 | 7.251 | 0.9933 | 0.9798 | passed |
| W6 | 5.790 | 0.9925 | 0.9816 | passed |

## Gate position per scene

| Gate | Status | Basis |
| --- | --- | --- |
| G0 semantic | PASSED | Locked source, explicit art-direction approval |
| G1 Canon atmosphere | PASSED | Art-direction basis; the images assert no Canon architecture, ownership or cosmology |
| G2 composition | PENDING_RUNTIME_QA | Source-frame and wide-crop identity checks pass (wide/master identity ratio 0.87–1.22 against the 0.6 floor); real runtime framing is not yet captured |
| G3 structure | PASSED | 25 / 100 / 200 % inspection record, no defects found |
| G4 production | PASSED | 4096×2560 master, 2560×1600 and 2400×900 derivatives, catalog payloads byte-identical |
| G5 runtime | PENDING_RUNTIME_QA | No window or accessibility captures yet |

## What this delivery does not claim

- **No shipping approval.** `shipping_approved` stays `false` for all six world targets, and the
  manifest status reads `MACOS_FINISHING_COMPLETE_RUNTIME_QA_PENDING`.
- **No runtime verification.** G2's runtime framing and G5's window / accessibility captures are
  still open; the derived assets are published, not approved for release.
- **No Canon claim.** The scenes remain art-direction metaphors, not assertions about canonical
  architecture.

## Verification commands

```sh
python3 -m unittest discover -s docs/05_UI/artwork/delivery/tests
python3 -m unittest discover -s docs/05_UI/artwork/tools/tests -p 'test_finish_world_artwork.py'
```
