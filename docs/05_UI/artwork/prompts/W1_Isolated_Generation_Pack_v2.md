# W1 — Isolated Generation Pack v2

> Artwork contract: `contracts/W1_WORLD_HERO.contract.json`  
> Purpose: generate composition candidates only.  
> This file intentionally excludes product naming, UI implementation terms, Asset Catalog names and runtime dimensions from the actual model-facing prompts.

## 1. Generation isolation rule

The image model must not receive these product/engineering tokens in the scene prompt:

- World of Mysteries
- W1
- hero asset
- macOS
- SwiftUI
- Asset Catalog
- runtime / imageset
- Fate / Codex / Gallery

The production operator may know those terms; the scene generator should receive only visual facts.

The target is **occult historical realism**:

> A materially believable late-19th-century industrial city in which ordinary urban life visibly coexists with an implied hidden order of churches, secret societies, divination, ritual knowledge and unseen observation. Supernatural evidence is local and restrained.

## 2. Shared model-facing core

Use this shared core for every candidate:

```text
A historically grounded European industrial city in the late 1890s shortly after rain. Dense four-to-six-storey masonry and soot-aged brick blocks, slate roofs, narrow chimneys, black wrought iron railings and balconies, dark timber details, oxidized brass, wet stone streets, horse-carriage scale, restrained small pedestrians, practical gas lamps and muted warm window light under a heavy blue-gray overcast sky.

The city must feel inhabited, physically believable and governed by ordinary material reality. Beneath that ordinary life there is a quiet sense of hidden churches, private societies, divination, sealed knowledge and old ritual traditions. This hidden order is suggested through atmosphere, institutional architecture, old metalwork, dim interiors and subtle observation motifs rather than explicit magic.

Reserve the left approximately one third of the frame as darker, low-frequency urban atmosphere: shadowed masonry, soft haze and simple architectural masses, with no face, no bright lamp cluster and no important signage. Place the strongest environmental depth and practical-light cluster right of center. The composition should remain readable as a real industrial city first.

Allow only one restrained physical anomaly: a faint cold silver-blue reflection on wet stone with no visible light source, or one small patch of mist moving subtly against the wind. The anomaly must be easy to miss at first glance.

Natural historical materials, restrained low-key lighting, blue-gray slate and charcoal dominant, aged brass and muted amber secondary, cold silver-blue only as a tiny abnormal accent.
```

Minimal negative classes:

```text
No typography or readable signage.
No fantasy architecture or impossible landscape.
No dominant hero character.
No overt magical spectacle.
```

Do not append long lists of forbidden objects unless a repeated failure proves one category needs a targeted guard.

## 3. Candidate A — Street-depth observation

Intent: strongest default W1 candidate.

Append:

```text
Camera viewpoint: slightly elevated from a second-storey or raised street position, looking diagonally down a long urban street. The right half contains layered street depth, roofs, chimneys, a restrained clocktower or church silhouette and several believable gaslight/window-light clusters. The left third is occupied by a close shadowed masonry facade and thin rain haze, creating a calm low-detail area. No landmark dominates the skyline. Human figures remain small and incidental.
```

Expected strengths:

- strong right-of-center focal depth;
- natural left quiet zone;
- lived-in city scale;
- easiest wide-header derivative.

## 4. Candidate B — Rooftop and avenue oblique

Intent: denser metropolitan identity without becoming a skyline poster.

Append:

```text
Camera viewpoint: oblique view across rain-darkened rooftops toward a broad avenue below, not a bird's-eye panorama. Repeating chimneys, slate roofs and masonry blocks create believable industrial density. The avenue and warm practical-light cluster sit right of center. The left third remains darker and simpler through a nearby roof mass, smoke haze and unlit wall surfaces. Keep the horizon modest; avoid monumental fantasy silhouettes.
```

Expected strengths:

- metropolitan density;
- smoke / fog layering;
- useful city horizon for wide crop.

Risk:

- reject if it becomes an epic skyline or landmark poster.

## 5. Candidate C — River-industrial district

Intent: introduce infrastructure and fog without turning the image into landscape art.

Append:

```text
Camera viewpoint: urban river or canal edge inside the dense city. Wet stone embankments, iron bridge structures, warehouses, brick blocks, chimneys and distant institutional roofs establish industrial reality. Water occupies only a controlled lower portion of the frame. The primary city depth and warm practical-light cluster remain right of center. The left third is a darker stone embankment / warehouse shadow and soft haze. The only abnormality may be a faint silver-blue reflection on water that has no matching source.
```

Expected strengths:

- believable industrial infrastructure;
- strong material variety;
- naturally supports anomalous reflection.

Risk:

- reject if river, cliffs, waterfalls or landscape become the primary subject.

## 6. Candidate D — Institutional street / hidden-order pressure

Intent: strongest occult-pressure candidate while remaining realistic.

Append:

```text
Camera viewpoint: a narrow but active late-19th-century urban street opening toward an austere institutional building or church-like civic silhouette in the middle-right distance. The building must remain plausible historical architecture, not a fantasy cathedral. Warm windows and gas lamps are sparse. Black iron gates, old brass details, damp stone and guarded entrances subtly suggest institutions, churches, archives or private societies. The left third is shadowed ordinary urban fabric. The scene should feel watched without showing a watcher.
```

Expected strengths:

- strongest hidden-order atmosphere;
- church / secret-society implication;
- restrained occult identity.

Risk:

- reject if architecture becomes gothic fantasy spectacle.

## 7. Candidate production policy

Generate 4–6 total candidates:

- A: at least 2 variations;
- B: 1 variation;
- C: 1 variation;
- D: 1 variation;
- optional sixth candidate: variation of the strongest direction only.

Do not iteratively edit a candidate that fails the **primary semantic read**.

Regenerate when:

- image reads as high fantasy;
- architecture is not historically believable;
- dominant character appears;
- city is replaced by natural landscape;
- typography / promotional composition appears;
- left quiet zone is structurally absent.

Use local editing only after G0 semantic pass.

## 8. Blind semantic QA script

The reviewer must inspect the image without reading its prompt or candidate label.

Record answers:

1. In one sentence, what place is shown?
2. What historical era does it suggest?
3. Does it read as a real city before supernatural imagery?
4. What makes the scene feel secretive / occult?
5. Is there an overt magical effect?
6. Is there a dominant protagonist?
7. Is there visible typography or fake readable signage?
8. Where is the strongest focal region?
9. Is the left third materially quieter than the focal region?
10. Does the image look like generic fantasy game key art?

Automatic rejection if answers indicate:

- fantasy kingdom / magical ruins / floating island / fantasy castle as primary read;
- overt spell effects;
- promotional title card / asset sheet;
- dominant protagonist;
- no usable left quiet zone.

## 9. Selection rule

Only candidates passing G0 proceed.

From G0-passing candidates, select at most two for:

```text
16:10 recomposition / outpaint
→ G2 composition
→ local structural repair
→ G3 structure
→ SR / material restoration
```

A visually attractive image that fails the contract is not a W1 candidate.

## 10. Relationship to product identity

The generator is intentionally isolated from product naming, but the final visual result must still satisfy the human art-direction brief:

- late-Victorian / early-industrial material reality;
- hidden church / ritual / divination / secret-knowledge pressure;
- restrained cosmic/occult abnormality;
- blue-gray + charcoal environment;
- aged brass + gaslight amber practical accents;
- tiny cold-silver abnormal accent;
- city reality first, occult order second, anomaly third.

This isolation prevents generic high-fantasy prompt priors without removing the intended 《诡秘之主》-style occult atmosphere.
