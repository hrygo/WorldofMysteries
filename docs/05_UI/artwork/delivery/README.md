# Approved source intake — PR #39

## Scope and authority

This is an executable source-intake checkpoint for Premium Art A1–A3, not a shipping completion record. The primary task remains [the implementation plan](../../Premium_World_Art_Artifact_Implementation_Plan_v1.0.md), [production manifest](../Premium_Art_Production_Manifest_v1.md), and the existing typed artwork registry. W1's approved v3 direction remains authoritative for W1. The subsequent explicit source-direction decision for W2/W5/W6 is recorded in [the approval update](World_Scene_Approval_Update_2026-09-18.md); it does not assert literal Canon architecture or force a crimson-moon theme onto every Artifact.

Intake revision 2 preserves **nine independently approved originals**. No montage, labels, captions, watermark, UI chrome or explanatory text may be baked into artwork. Meaning belongs in composition, material, light and spatial relationships. Source-level approval is not G3–G5 or Canon approval.

## Correct runtime mapping

| Runtime task | Approved source | Delivery status |
| --- | --- | --- |
| W1 World Hero | S01 city | Locked source; macOS finishing #40 |
| W2 Gray Fog / Sefirah | S07 high-order fog interpretation | Source locked; game-metaphor mapping/crop/runtime QA pending |
| W3 Ritual Altar | S04 temple | Source approved; ritual-component mapping and crop review pending |
| W4 Codex / Archive | S03 library | Source approved; reading-surface mapping and crop review pending |
| W5 Fate / Worldline | S08 fate observation | Source locked; mapping/crop/runtime QA pending |
| W6 Artifact Vault / Evidence Room | S09 containment vault | Source locked; mapping/crop/runtime QA pending |

S02 street, S05 harbor and S06 alley remain supplemental environments, not substitutes for Gray Fog, Fate or Vault. There are nine approved sources, six assigned scene candidates, three supplemental environments and zero finalized shipping assets in this intake. Existing `crop_review.json` records W1/W3/W4 proposals; `additional_scene_crops.json` adds W2/W5/W6. No crop record is a runtime approval.

## Ordered delivery

1. Preserve and verify all nine accepted originals; do not regenerate accepted compositions.
2. Review scene-to-component framing and overlays while macOS finishing remains deferred.
3. Produce Artifact P0 in the order in `approved_sources.json`: Arrodes, Quill, Brass Book, Wishing Lamp, Creeping Hunger, Sea God Scepter, Probability Die. Verify physical form against source evidence before treating a Canon brief as approved. Human review of P0 precedes P1.
4. Produce the remaining eight Artifacts individually. Each object needs its own visual verb, not a universal gold ring / crimson moon / rune background. The actual 15 `ArtifactID` values are unchanged; no character-portrait expansion is implied.
5. macOS finishing: repair, one principal SR pass, material/color work, approved Master, deterministic derivatives, G3–G5, provenance and Asset Catalog. W1 wide export keeps `--wide-anchor top`. Other anchors remain subject to image-specific review.
6. Run final-head Work Receipt and required gates before merge readiness. Keep #39 Draft until remaining scope is genuinely complete. #40 and #41 remain open; this intake does not authorize merge.

## Original-byte transport and macOS intake

`approved_sources.json` records exact original filenames, bytes, dimensions, SHA256 values and generation IDs. The portable `Premium-Art-Approved-Sources-v2` bundle contains all nine unmodified PNGs under `sources/`. The manifest and tooling are versioned in the PR; binary repository import is a separate pending transport step. A hash is not evidence that GitHub contains an image.

From the repository root, using a relative path to the extracted source bundle:

```sh
python3 docs/05_UI/artwork/delivery/intake.py verify \
  --source-dir scratch/Premium-Art-Approved-Sources-v2 \
  --registry macos-app/WorldOfMysteries/DesignSystem/WOMArtworkAsset.swift

python3 docs/05_UI/artwork/delivery/intake.py stage \
  --source-dir scratch/Premium-Art-Approved-Sources-v2 \
  --stage-dir docs/05_UI/artwork/sources/approved-2026-09-18-r2
```

Staging refuses an existing destination and never writes `.xcassets` or `.imageset` directories. It rechecks copied bytes before recording `INTAKE_COMPLETE.json`. Inspect the resulting source-only diff, then add it to the same production branch as one atomic source-ingestion commit. The tool does not commit, push, generate, upscale, rewrite QA flags or approve shipping.

## Targeted verification

```sh
python3 -m unittest discover -s docs/05_UI/artwork/delivery/tests -v
```

Tests cover registry consistency, P0/P1 ordering, original integrity, supplemental-scene misclassification, source-versus-shipping approval, unsafe paths, symlinks, damaged PNG containers, no-overwrite staging and Asset Catalog exclusion. PNG container validation is not pixel-level structural review. Local Python tests and source intake are not the protected macOS gate or a Work Receipt.

## Source staging isolation and scan cost

Source filenames must be canonical relative PNG paths below `sources/`. Bundle-root
`approved_sources.json` and `INTAKE_COMPLETE.json` are reserved for metadata, never
source payloads. Case-folded / Unicode-normalized duplicate paths are refused so a
bundle that is distinct on Linux cannot silently collide on a macOS filesystem.
Neither source paths nor staging destinations may contain `.xcassets` / `.imageset`
components, regardless of case. Destination checks include the absolute caller path
and its resolved location: a relative invocation inside a catalog or a directory
alias pointing into one cannot bypass the boundary. Ordinary aliases outside catalogs
remain supported. These checks assume a stable workspace, not a hostile process
concurrently replacing ancestor directories.

Metadata uses explicit UTF-8. The `stage` command verifies originals once and copied
bytes once; it no longer performs an extra full source scan in its CLI wrapper.
Copied-byte verification, atomic directory publication, failure cleanup, approval
flags and existing six-source compatibility remain intact.

Focused regression command (not the full project or macOS gate):

```sh
python3 -m unittest discover -s docs/05_UI/artwork/delivery/tests -p 'test_intake*.py' -v
```

Local recovery/staging still does not mean the original PNGs have reached GitHub.
Source-byte publication remains tracked in #41 until the remote files are verified.
