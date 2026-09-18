# Approved source intake — PR #39

## Scope and authority

This is an executable source-intake checkpoint for Premium Art A1–A3, not a shipping completion record. The primary task remains [the implementation plan](../../Premium_World_Art_Artifact_Implementation_Plan_v1.0.md), [production manifest](../Premium_Art_Production_Manifest_v1.md), and the existing typed artwork registry. W1's approved v3 direction remains authoritative for W1; it does not turn every scene into a crimson-moon city.

The six user-approved originals are preserved independently. No montage, labels, captions, watermark, UI chrome or explanatory text may be baked into the artwork. Meaning belongs in composition, material, light and spatial relationships. These are source-level approvals, not assertions that G3–G5 or Canon review passed.

## Correct runtime mapping

| Runtime task | Approved source | Delivery status |
| --- | --- | --- |
| W1 World Hero | S01 city | Locked source; macOS finishing tracked by #40 |
| W2 Gray Fog / Sefirah | None | New standalone image required |
| W3 Ritual Altar | S04 temple | Source approved; ritual-component mapping and crop review pending |
| W4 Codex / Archive | S03 library | Source approved; reading-surface mapping and crop review pending |
| W5 Fate / Worldline | None | New standalone image required |
| W6 Artifact Vault / Evidence Room | None | New standalone image required |

S02 street, S05 harbor and S06 alley are approved supplemental environment sources. Preserve them; do not relabel them as Gray Fog, Fate or Vault to claim 6/6 coverage. There are six approved source images, three assigned source candidates, three missing required scene images, and zero finalized shipping assets in this intake.

## Ordered delivery

1. Preserve and verify all six accepted originals (this checkpoint).
2. Produce W2, W5 and W6 separately; verify semantic distinction, readable midtones, no baked text and viable crops. W2 uses its existing production brief; the crimson moon is not a compulsory motif for these three semantic domains.
3. Review W3/W4 source-to-component framing without reopening already accepted art direction.
4. Produce Artifact P0 in the order in `approved_sources.json`: Arrodes, Quill, Brass Book, Wishing Lamp, Creeping Hunger, Sea God Scepter, Probability Die. Verify physical form against source evidence before treating a Canon brief as approved. Human review of P0 precedes P1.
5. Produce the remaining eight Artifacts individually. Each object needs its own visual verb, not a universal gold ring / crimson moon / rune background. The actual 15 `ArtifactID` values are unchanged; no character-portrait expansion is implied.
6. macOS finishing: repair, one principal SR pass, material/color work, approved Master, deterministic derivatives, G3–G5, provenance and Asset Catalog. W1 wide export keeps `--wide-anchor top`. Other anchors remain subject to image-specific review.
7. Run final-head Work Receipt and required gates before merge readiness. Keep #39 Draft until remaining scope is genuinely complete. No automatic Issue closure or merge is authorized by this intake.

## Original-byte transport and macOS intake

`approved_sources.json` records the exact original filenames, bytes, dimensions, SHA256 values and generation IDs. The portable `Premium-Art-Approved-Sources` bundle contains those six unmodified PNGs under `sources/`. The manifest and tooling are versioned in the PR; original binary repository import remains a distinct pending transport step. A hash is not evidence that the remote repository contains the image.

From the repository root, using a relative path to the extracted source bundle:

```sh
python3 docs/05_UI/artwork/delivery/intake.py verify \
  --source-dir scratch/Premium-Art-Approved-Sources \
  --registry macos-app/WorldOfMysteries/DesignSystem/WOMArtworkAsset.swift

python3 docs/05_UI/artwork/delivery/intake.py stage \
  --source-dir scratch/Premium-Art-Approved-Sources \
  --stage-dir docs/05_UI/artwork/sources/approved-2026-09-18
```

Staging refuses an existing destination and never writes `.xcassets` or `.imageset` directories. It rechecks the copied bytes before recording `INTAKE_COMPLETE.json`. Inspect the resulting source-only diff, then add it to the same production branch as one atomic source-ingestion commit. The tool does not commit, push, generate, upscale, rewrite QA flags or approve shipping.

## Targeted verification

```sh
python3 -m unittest discover -s docs/05_UI/artwork/delivery/tests -v
```

Tests cover registry consistency, P0/P1 ordering, original integrity, supplemental-scene misclassification, source-versus-shipping approval, unsafe paths, symlinks, damaged PNG containers, no-overwrite staging and Asset Catalog exclusion. PNG container validation is not pixel-level structural review. Local Python tests and source intake are not the protected macOS gate or a Work Receipt.
