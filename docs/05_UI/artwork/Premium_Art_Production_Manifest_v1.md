# World of Mysteries — Premium Art Production Manifest v1

> Status: ACTIVE  
> Program: Premium Art A1–A3  
> Repository: `hrygo/WorldofMysteries`  
> Delivery model: one long-lived PR + atomic commits + milestone CI only.

## 1. Production objective

Convert the completed Visual System engineering foundation into a premium, image-led product experience. This phase does **not** reopen Button/Surface/Window primitives unless artwork integration proves a real gap.

Primary outcomes:

1. 6/6 premium world / scene artworks.
2. 15/15 premium Artifact artworks aligned to the existing `ArtifactRegistry`.
3. Asset Catalog + typed artwork registries.
4. Runtime integration into existing World / Ritual / Codex / Fate / Artifact surfaces.
5. Visual QA for crop safety, readability, contrast, long-text layout and minimum-window behavior.

## 2. Art direction

Canonical visual thesis:

> industrial-age reality first; the supernatural intrudes into it.

The app must not collapse into a generic all-black / purple / tentacle occult UI. Gray Fog, ritual geometry, corruption, celestial fracture and impossible space are **semantic domains**, not a universal filter.

Shared art language:

- late Victorian / early industrial realism;
- restrained cosmic horror;
- archival mysticism;
- aged brass, blackened metal, old silver, dark timber, parchment, glass, worn leather;
- volumetric fog and practical light;
- supernatural light as local evidence, not global neon;
- readable silhouette before decorative detail.

Avoid:

- high-saturation magic purple;
- generic mobile-game gold;
- excessive bloom;
- large baked-in UI text;
- copied official animation / game / comic art;
- meaningless occult-symbol wallpaper.

## 3. Current product implementation to preserve

The current repository already has:

- `ArtifactRegistry` with 15 canonical/special objects;
- 15 Artifact gameplay components;
- typed artifact action / result / risk / state models;
- progressive disclosure in `ArtifactShowcaseView`;
- responsive `ArtifactComponentShell`;
- RealityKit interaction for Probability Die;
- Visual QA, contrast, typography and source guards.

Therefore premium art is **identity and atmosphere**, not a gameplay rewrite.

## 4. A1 — World / Scene Art (6/6)

| ID | Scene | Product use | Composition constraint |
|---|---|---|---|
| W1 | World Hero | main world / shell hero | city reality dominant; supernatural intrusion secondary; left or lower quiet zone for text |
| W2 | Gray Fog / Sefirah | Fate / liminal state | abstract impossible scale; no generic castle-in-cloud fantasy |
| W3 | Ritual Altar | Ritual components / header | practical candle/metal/stone materials; ritual geometry precise but restrained |
| W4 | Codex / Archive | Codex / Archive | dense historical archive, dossiers, lamps, brass instruments; readable quiet region |
| W5 | Fate / Worldline | Fate / intervention | branching causal structure / astronomical machinery; avoid sci-fi hologram look |
| W6 | Artifact Vault / Evidence Room | Artifact library | museum/evidence-room logic; sealed dangerous objects treated as controlled evidence |

Master target: `4096×2560`  
Runtime target: `2560×1600`  
Optional header crop: `2400×900`

Every asset must define:

- Focus Zone;
- Quiet Zone;
- Crop Reserve;
- minimum safe crop;
- contrast/scrim requirement;
- provenance record.

## 5. A2/A3 — Artifact premium art (15/15)

### P0 signature 7

1. Arrodes Mirror
2. Alzuhod Quill / 0-08
3. Trunsoest Brass Book / 0-02
4. Magic Wishing Lamp / 0-05
5. Creeping Hunger
6. Sea God Scepter
7. Probability Die

### P1 remaining 8

8. Leymano's Travels
9. Groselle's Travels
10. Azik Copper Whistle
11. Cards of Blasphemy
12. Staff of Stars
13. Box of the Great Old Ones
14. Death Knell
15. Unshadowed Crucifix

Artifact master: `2048×2048`  
Detail runtime: `1024×1024`  
Thumbnail: `512×512`

Acceptance:

- recognizable silhouette at 96px;
- no baked-in labels/stats/buttons;
- object material and wear communicate history;
- supernatural effect communicates capability **and cost/risk**;
- transparent/quiet surround sufficient for card/detail composition;
- artwork does not replace typed status/risk UI.

Probability Die keeps existing RealityKit as the interactive primary state. Premium 2D artwork serves library / dossier / static presentation.

## 6. First generated art-direction board

A first visual-direction candidate has been produced in the execution environment to validate overall mood before committing runtime art.

Candidate filename: `PremiumArt_ArtDirectionBoard_v1_q82.jpg`  
SHA-256: `d89dc4c1a5b39e07fb9395484052cb9066fc922dff3d6a43d121a941b0d888ca`

Purpose: **art-direction reference only**, not runtime asset.

QA observation from this candidate:

- the blue-gray / aged-brass / practical-light balance is directionally useful;
- Archive / Ritual / Vault material language is strong;
- the board overuses gothic architecture and baked typography for production use;
- W1/W2 production pieces must be cleaner, more product-composable, and contain explicit quiet zones;
- Artifact production must use the real 15 registry objects rather than invented generic relics.

This board therefore acts as a **direction checkpoint**, not an approved shipping image.

## 7. Runtime integration architecture

Planned typed APIs:

```text
WOMWorldArtworkAsset
WOMArtifactArtworkAsset
WOMArtworkVariant
WOMArtworkView
WOMArtworkScrim
```

Integration principle:

```text
premium artwork = primary visual identity
existing typed icon = semantic/accessibility/fallback identity
existing component state = authoritative interaction/state
```

`ArtifactComponentShell.identityPanel` will evolve from:

```text
SF Symbol primary identity
```

to:

```text
premium object artwork primary identity
+ typed SF Symbol fallback
+ existing metadata / risk / state / action UI
```

## 8. Visual QA hard gates

All previous contracts remain active:

- readable text >= 4.5:1;
- important/long-text approved combinations target >= 7:1;
- key non-text affordance >= 3:1;
- body >= 13pt;
- metadata >= 11pt;
- 960×640 no structural overlap;
- 1180×760 preferred default;
- Inspector 280 / 320 / 420;
- no `minimumScaleFactor` layout escape;
- no negative-padding content layout hacks;
- Increased Contrast / Reduce Transparency / Reduce Motion / Differentiate Without Color / Focus remain valid.

Artwork-specific QA:

- no text on uncontrolled image detail without quiet zone/scrim/surface;
- crop must preserve semantic focal subject;
- runtime selectors never load master-resolution images;
- texture/detail must survive Retina but not create illegible micro-noise behind text;
- high-contrast mode must remain usable even if decorative art is reduced.

## 9. Commit strategy

This program intentionally uses one large production PR. Planned atomic commit families:

1. `docs(art): start premium art production manifest`
2. `art(world): add W1 and W2 candidates`
3. `art(world): complete W3–W6 scene set`
4. `feat(macos): integrate world artwork registry and scrim`
5. `art(artifact): add P0 signature artifact set`
6. `feat(macos): integrate artifact artwork into component shell`
7. `art(artifact): complete remaining 8 artifact artworks`
8. `test(macos): enforce artwork catalog and QA contracts`
9. `docs(art): finalize provenance and approval record`

Routine work does **not** wait on Actions. CI is reviewed only at meaningful milestone closure and final merge readiness.

## 10. Milestone definition

Do not request final CI/merge until at least one meaningful milestone is complete.

Preferred milestone for this PR:

- 6/6 World scene artworks;
- 15/15 Artifact premium artworks;
- typed registries and runtime integration;
- visual QA/provenance complete;
- no placeholder artwork in shipping Artifact identity surfaces.
