# Finishing and production resume checkpoint

## Tracking and status

W1 finishing remains tracked by #40. The remaining scene/Artifact/source-transport/final-QA work is tracked by #41, all within existing PR #39. The source intake checkpoint is commit `4dc19cdd34a5413bbf03e818ef39796427ec5126`.

Six original PNGs have explicit user visual approval. This is not 6/6 required runtime coverage: W2, W5 and W6 still need matched sources. W3 and W4 have appropriate approved source candidates but require actual component-framing and runtime checks. All 15 Artifact images remain unapproved. No production Master or final shipping approval is created by these intake records.

## Exact source crops and proposed wide exports

`crop_review.json` records original and cropped SHA256 values and exclusive pixel rectangles. The 1586×992 sources yield exact 1584×990 working crops by removing one pixel from each edge. No super resolution or enlargement is involved.

| Task | Wide anchor | 4096×2560 Master crop | Reason |
| --- | --- | --- | --- |
| W1 | top, required by v3 | `[0,0,4096,1536]` | Keep its identity-bearing sky subject |
| W3 | center, proposed | `[0,512,4096,2048]` | Retain altar, ritual space and steps |
| W4 | bottom, proposed | `[0,1024,4096,2560]` | Retain reading table, books and archive materials |

The crop previews are source-framing evidence only. W3/W4 anchors are proposals, not G2/G5 passes. Validate the real component overlays and minimum-window rendering on macOS before locking those anchors. The full-frame runtime is still 2560×1600 and the wide derivative is 2400×900, both derived from the same finished Master.

## Resume source generation

Use the three separate files in `scene_prompts/` as single-scene briefs. They translate the existing W2 brief and W5/W6 roles from the main plan into composition, not explanatory labels. No new canonical architecture or artifact identity is asserted by these scene prompts. Do not send all prompts together or request a montage.

Two attempts to produce W2 in this execution context did not match the requested semantic target. Their generation IDs, hashes and unassigned status are recorded in `generation_attempts.json`; they are not approved sources or Artifact deliveries. Further blind retries through the same path are not useful. A fresh controllable generation context or an authorized alternate provider is needed. An external `fal` connection was suggested but was not installed or used; no external generation cost was incurred by this checkpoint.

For Artifacts, keep the actual P0/P1 order in `approved_sources.json`. `canon_evidence.json` distinguishes three narrow claims verified from official original-book pages from missing evidence. Public previews that do not contain a required description do not constitute verification. Do not label the entire P0 Canon review complete or copy novel passages into the repository.

## Source-binary import on macOS

The portable `Premium-Art-Approved-Sources` archive contains the six unchanged original PNGs, the manifest and intake tool. Source hashes in Git are not a substitute for committing original bytes. First verify the archive, then use the repository tool:

```sh
python3 docs/05_UI/artwork/delivery/intake.py verify \
  --source-dir .agents/scratch/Premium-Art-Approved-Sources \
  --registry macos-app/WorldOfMysteries/DesignSystem/WOMArtworkAsset.swift

python3 docs/05_UI/artwork/delivery/intake.py stage \
  --source-dir .agents/scratch/Premium-Art-Approved-Sources \
  --stage-dir docs/05_UI/artwork/sources/approved-2026-09-18
```

Review the source-only diff, commit it atomically to the existing production branch and verify remote hashes. Do not overwrite a nonempty local worktree or use a new PR for individual PNG files. Source intake must not write an Asset Catalog.

## Final macOS production boundary

Complete local repair, one principal SR pass, material/luminance finishing and final Master construction. Then invoke the existing `derive_world_artwork.swift` with the contract-approved anchor, not independent image regeneration. Finalize G3–G5 and provenance only with real output bytes and macOS runtime evidence. Keep every incomplete issue open.

The local Python source-intake tests are not `MACOS_APP_P0`, an Xcode build or a Work Receipt. The older `4e5ab9cf…` receipt does not cover current head. Final review needs the repository's protected gate and a new receipt for the final candidate head. Do not merge PR #39 on the basis of this checkpoint.
