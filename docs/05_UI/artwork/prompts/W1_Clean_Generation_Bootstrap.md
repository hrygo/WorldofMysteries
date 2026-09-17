# W1 Clean Generation Bootstrap

> Use the **content only** in a fresh image-generation context.
> Do not preload project chat history, rejected candidates, W2, Artifact art, card art, cosmic entities, PR discussion or UI implementation context.

## Phase 0 — Control probe

Generate exactly one image from this prompt first:

```text
A historically grounded reconstruction of an ordinary large British industrial city around 1895 shortly after rain. Four-to-six-storey brick and stone residential and commercial blocks, slate roofs, ordinary chimneys, black iron railings, wet stone streets, horse-drawn carriages, a few distant pedestrians, practical gas street lamps, warehouses and distant factory smokestacks. Slightly elevated street-level viewpoint. The right-center contains ordinary street depth; the left third is darker wall and roof mass with lower visual detail.

No monumental landmark dominates the skyline. No religious building is a primary subject. No castle, fantasy architecture, banner, emblem, poster, slogan, readable shop name, celestial spectacle, airship or magical element. The image should resemble a rigorous historical architectural environment reconstruction, not a film poster or game concept image.

Landscape composition, approximately 16:10.
```

### Control-probe PASS

Proceed only if the result:

- reads first as an ordinary late-19th-century industrial city;
- has no readable invented text;
- has no occult/faction banner;
- has no monumental fantasy cathedral/castle;
- has no celestial halo/portal/impossible moon;
- has no promotional key-art staging.

If two or more failure classes appear, **discard the entire generation context** and start another clean context. Do not tune the production prompt inside a failed context.

---

## Phase 1 — Production candidate core

After the control probe passes, start a new generation request in the **same clean context**:

```text
A historically grounded European industrial city in the late 1890s shortly after rain. Dense four-to-six-storey masonry and soot-aged brick blocks, slate roofs, ordinary narrow chimneys, black wrought-iron railings and balconies, dark timber details, oxidized brass, wet stone streets, horse-carriage scale, restrained small pedestrians, practical gas lamps and muted warm window light under a heavy blue-gray overcast sky.

The city must remain physically believable and inhabited. A subtle hidden-order atmosphere should come only from physical details: guarded entrances, curtained upper windows, restrained institutional architecture, old measuring or astronomical instruments, controlled access, worn non-textual metal geometry, unusual stillness and the sense that some rooms are not meant to be seen. Do not turn those cues into logos, banners, organizations, slogans, symbols or monumental religious architecture.

Reserve the left approximately one third as darker low-frequency urban atmosphere: shadowed masonry, soft haze and simple roof/wall masses, with no face, no bright lamp cluster and no important subject. Place the strongest street-depth and practical-light cluster right of center.

Allow exactly one almost-missable physical abnormality: a faint cold silver-blue reflection on wet stone with no visible matching light source.

All surfaces and signs are blank or unreadable. Ordinary city skyline only. No dominant protagonist. No overt magic or celestial spectacle. Blue-gray slate, charcoal and wet stone dominant; aged brass and muted gaslight amber secondary; cold silver-blue only as a tiny abnormal accent.

Landscape composition, approximately 16:10.
```

---

## Phase 2 — Candidate directions

Generate 4–6 candidates total.

### A1 / A2 — Street depth

Append:

```text
Slightly elevated diagonal view down a long urban street. Right-center: layered street depth, ordinary roofs, chimneys, one modest clocktower and believable gaslight/window clusters. Left third: near shadowed masonry facade and thin rain haze. No landmark may dominate the skyline.
```

Generate two variations.

### B — Rooftop oblique

Append:

```text
Oblique view across rain-darkened rooftops toward a broad avenue below, not a bird's-eye panorama. Repeating chimneys and masonry blocks create believable industrial density. Right-center: avenue depth and practical light. Left third: nearby dark roof mass, smoke haze and unlit wall surfaces.
```

### C — River industrial

Append:

```text
Urban canal or river edge inside the dense city. Wet stone embankment, ordinary iron bridge structures, warehouses, brick blocks, chimneys and small working boats. Water occupies only a controlled lower portion. Right-center remains dense city depth; left third is shadowed warehouse/embankment mass.
```

### D — Institutional restraint

Append:

```text
A normal urban street opening toward an austere but historically plausible civic or institutional building in the middle-right distance. It must remain comparable in scale to surrounding city blocks. Black iron gates, old brass hardware, damp stone and guarded entrances imply privacy and controlled access. No cathedral-scale silhouette.
```

---

## Phase 3 — Immediate rejection

Reject without repair if the primary read is any of:

- fantasy kingdom;
- magical ruins;
- giant cathedral/castle spectacle;
- occult faction poster;
- celestial fantasy;
- protagonist key art.

Also reject immediately for:

- readable invented text;
- banners/emblems introduced as primary motifs;
- absent left quiet zone.

Do **not** use a rejected semantic candidate as the basis for image editing.

Only G0-passing candidates may proceed to recomposition / local repair.
