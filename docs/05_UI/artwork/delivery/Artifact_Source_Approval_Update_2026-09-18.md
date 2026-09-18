# Artifact object source approval — intake revision 3

> Source-level art approval for the 15 Artifact objects. macOS finishing is recorded separately;
> Canon verification, runtime QA and shipping approval remain open.

## Approval and scope

The user generated and accepted 15 standalone Artifact object illustrations and handed over the
selected originals as `WorldofMysteries_Artifact_Selected_Source_Pack`. Each accepted image is one
object per file: no montage, no grid of objects, no shared "rarity skin", and no reuse of the
World / Scene crimson-moon or gold-ring motif.

This update moves the 15 `artifact_targets` in [approved_sources.json](approved_sources.json) from
`CANON_BRIEF_AND_GENERATION_PENDING` with no source, to `SOURCE_LOCKED_FINISHING_PENDING` with an
explicitly bound original. Intake revision 3 therefore declares **24 approved sources**: nine
World / Scene originals from revision 2 (six target sources and three supplemental environments)
plus the 15 Artifact objects.

| Order | Phase | `artifact_id` | Source | Native size |
|:--:|:--:|---|---|---|
| 1 | P0 | `arrodesMirror` | A01_ARRODES_MIRROR | 1254×1254 |
| 2 | P0 | `alzuhodQuill` | A02_ALZUHOD_QUILL | 1222×1287 |
| 3 | P0 | `trunsoestBrassBook` | A03_TRUNSOEST_BRASS_BOOK | 1254×1254 |
| 4 | P0 | `magicWishingLamp` | A04_MAGIC_WISHING_LAMP | 1254×1254 |
| 5 | P0 | `creepingHunger` | A05_CREEPING_HUNGER | 1254×1254 |
| 6 | P0 | `seaGodScepter` | A06_SEA_GOD_SCEPTER | 1254×1254 |
| 7 | P0 | `probabilityDie` | A07_PROBABILITY_DIE | 1254×1254 |
| 8 | P1 | `leymanoTravels` | A08_LEYMANO_TRAVELS | 1254×1254 |
| 9 | P1 | `groselleTravels` | A09_GROSELLE_TRAVELS | 1254×1254 |
| 10 | P1 | `azikCopperWhistle` | A10_AZIK_COPPER_WHISTLE | 1254×1254 |
| 11 | P1 | `cardsOfBlasphemy` | A11_CARDS_OF_BLASPHEMY | 1370×1148 |
| 12 | P1 | `staffOfStars` | A12_STAFF_OF_STARS | 1371×1148 |
| 13 | P1 | `boxOfGreatOldOnes` | A13_BOX_OF_GREAT_OLD_ONES | 1254×1254 |
| 14 | P1 | `deathKnell` | A14_DEATH_KNELL | 1370×1148 |
| 15 | P1 | `unshadowedCrucifix` | A15_UNSHADOWED_CRUCIFIX | 1254×1254 |

Exact original-byte hashes, byte sizes, dimensions and generation IDs are recorded per source in
[approved_sources.json](approved_sources.json). The original PNGs are preserved and never
overwritten; the finishing chain only ever reads them.

## What this approval does not mean

- It is **not Canon verification**. `canon_evidence.json` still records verified primary form
  claims for only three of the 15 objects, and every Artifact source carries
  `canon_approval: false`.
- It is **not runtime approval**. No Artifact collection, detail-sheet or accessibility capture
  exists yet, so G5 stays open for all 15.
- It is **not shipping approval**. Every source and every target keeps `shipping_approved: false`.
- It does **not** claim a native 2048×2048 generation. The widest approved object source is
  1371px on its short edge, so the 2048×2048 Master is recorded as a finished / super-resolved
  Master.

## Known visual deviations recorded at intake

- **A02 阿勒苏霍德之笔**: the approved source contains baked readable Latin/English lettering on
  the background book spines ("THE FOOL", "HISTORY MYSTERIES"). Product policy is text-free art.
  This is recorded as a defect rather than hidden, so G0 and G3 stay open for A02 until the user
  either accepts the lettering as background prop or re-generates the source.
- **A03 特伦索斯特黄铜书**: the approved source contains baked readable Latin lettering engraved
  on the brass cover ("FIAT IUSTITIA ET PEREAT ET MUNDUS"). Recorded the same way as A02.
- Every other object passed the 25/100/200% text scan with no legible word, numeral or
  pseudo-writing.

## Artifacts that need a user or Canon decision before shipping

Three objects have verified primary form evidence (`alzuhodQuill`, `probabilityDie`,
`arrodesMirror`). The remaining twelve have no recorded primary form claim, and
`trunsoestBrassBook` / `creepingHunger` are explicitly listed as public-preview coverage limits in
`canon_evidence.json`. G1 therefore stays open for them; this document does not convert a visual
approval into a Canon conclusion.

## Remaining work

The finishing checkpoint covers source intake, one principal super-resolution pass, the
2048×2048 Master, same-Master `detail` / `thumbnail` derivatives and Asset Catalog ingestion.
Still open: the A02/A03 baked-lettering decision, Canon review for twelve objects, Artifact
collection / detail-sheet / accessibility captures (G5), final-head Work Receipt and the
protected macOS gate. See `#51` for the handoff and `#41` for the remaining Premium Art
delivery.
