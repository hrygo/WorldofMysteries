# W1 Generation Method Validation — Context Isolation Experiment

> Date: 2026-09-18  
> Scope: W1 composition generation method validation  
> Shipping assets produced: **0**  
> Result: **generation context rejected; method revised**

## 1. Purpose

Validate whether the locked W1 Image Contract and isolated prompt pack can reliably produce a shipping-quality composition inside the current long-lived project conversation.

The experiment intentionally kept failed candidates out of Git. Only generation IDs, measured composition metrics and rejection reasons are recorded here.

## 2. Experiment design

Six fresh candidates were produced:

- A — street-depth observation
- B — rooftop / avenue oblique
- C — river-industrial district
- D — institutional street / hidden-order pressure
- E — physical-cue rewrite with occult nouns removed
- F — **control group** with all occult / mystery semantics removed

A targeted edit experiment was also run against A:

- remove all readable text;
- reduce monumental Gothic skyline;
- preserve quiet zone and street-depth composition.

The control group F was critical: it asked only for an ordinary historically grounded 1895 British industrial city and explicitly excluded fantasy, religious monuments, symbols, banners, posters and readable text.

## 3. Quantitative composition results

All candidates were generated at approximately `1586×992`.

The following metrics were measured from the actual generated pixels:

- `quiet/focus edge ratio`: mean luminance-gradient density in left 35% divided by the locked focus region;
- `quiet/focus luminance ratio`: mean luminance in left 35% divided by focus region;
- `bright centroid`: normalized centroid of the brightest 0.5% pixels.

| Candidate | Quiet / Focus Edge | Quiet / Focus Luminance | Bright Centroid (x,y) | Composition |
|---|---:|---:|---:|---|
| A | 0.193 | 0.546 | (0.761, 0.438) | strong |
| B | 0.203 | 0.414 | (0.739, 0.593) | strong |
| C | 0.116 | 0.426 | (0.702, 0.432) | very strong quiet zone |
| D | 0.246 | 0.471 | (0.716, 0.617) | acceptable |
| E | 0.153 | 0.500 | (0.713, 0.647) | strong |
| F control | 0.245 | 0.310 | (0.738, 0.488) | acceptable |

### Interpretation

The prompt pack is **successfully controlling macro composition**:

- all brightest centroids land in the intended right-side region;
- all left quiet zones are materially less detailed than the focus region;
- the generator consistently understands the left-quiet/right-focus geometry.

The failure is therefore not primarily composition.

## 4. Semantic rejection results

### A

Useful:

- strongest overall street-depth composition;
- left quiet zone works;
- industrial material language is directionally useful.

Rejected because:

- readable store / society text was baked into the image;
- skyline became too monumental and Gothic;
- occult identity was literalized into explicit institutional signage.

### B

Rejected because:

- readable banners / slogans;
- overt celestial halo / magical sky structure;
- monumental fantasy-Gothic skyline.

### C

Rejected because:

- vortex-like supernatural sky;
- zeppelin / spectacle;
- dominant cathedral-scale architecture;
- explicit emblem/banner language.

### D

Rejected because:

- baked readable shop and wall text;
- monumental Gothic skyline;
- distant impossible ruin became a fantasy spectacle.

### E — physical-cue rewrite

This prompt removed direct occult nouns and attempted to express mystery only through:

- closed gates;
- curtained windows;
- ordinary brass instruments;
- non-textual worn metal details;
- spatial observation pressure.

It still produced:

- readable slogan text;
- banners / occult emblems;
- monumental fantasy architecture;
- celestial / monolithic spectacle.

**Conclusion:** simply rewriting occult concepts into physical cues is insufficient inside this conversation context.

### F — control group

F removed all occult / mystery intent and asked for a plain 1895 industrial city historical reconstruction.

It still produced:

- propaganda-like readable text;
- occult-style banners / emblems;
- monumental Gothic cathedral skyline;
- cinematic fantasy treatment.

**This is the decisive result.**

The semantic failures persist even when the candidate prompt itself does not contain the triggering concepts.

## 5. Edit-path validation

A targeted edit was requested against Candidate A:

- delete all readable text;
- remove visible emblems;
- replace monumental Gothic skyline with ordinary industrial roofs / chimneys / modest civic architecture.

Result:

- the edit did not remove the failure mode;
- it introduced additional propaganda-like text and explicit banner content;
- the skyline remained strongly Gothic.

### Conclusion

Inside a contaminated generation context, targeted editing is **not a reliable escape hatch**. Editing inherits the same semantic prior.

## 6. Root cause

The experiment isolates two separate behaviors:

### Working

- spatial layout;
- quiet-zone placement;
- right-of-center focal control;
- blue-gray / amber palette;
- rain / industrial-city material language.

### Failing

- typography suppression;
- ordinary-vs-monumental architecture;
- removal of generic Gothic fantasy;
- suppression of symbolic/banner literalization.

Because control group F failed despite removing the relevant concepts, the dominant cause is:

> **long-lived conversation context contamination / automatic generation-context inference**, not insufficient prompt wording.

The current project conversation contains a high concentration of:

- Lord of Mysteries / occult art direction;
- cosmic entities;
- cards / symbols;
- earlier failed fantasy city candidates;
- W1/W2 asset discussions.

The image generator is therefore repeatedly reconstructing a latent “Gothic occult game world” prior even when the immediate candidate prompt explicitly asks for plain historical realism.

## 7. Method revision: G-CTX Context Gate

A new gate is inserted **before G0 Semantic Gate**.

```text
G-CTX Generation Context
        ↓
G0 Semantic
        ↓
G1 Canon / Atmosphere
        ↓
...
```

### G-CTX PASS requirements

Production generation must run in a clean, isolated image-generation context containing only:

1. the single artwork contract;
2. the isolated generation pack;
3. the selected candidate direction;
4. no previous candidate images;
5. no W2 / Artifact / cosmic-entity artwork;
6. no PR / GitHub / SwiftUI / Asset Catalog discussion;
7. no earlier rejected fantasy outputs.

### Control probe

Before spending a candidate batch, the context must pass a cheap control probe:

> Generate an ordinary historically grounded late-19th-century industrial-city environment with no occult semantics.

Reject the generation context if the control probe introduces any two of:

- monumental fantasy cathedral / castle;
- readable slogans / invented organization names;
- occult banners / sigils;
- celestial halo / portal / impossible moon;
- floating architecture / fantasy landscape;
- promotional key-art composition.

A failed control probe means:

> **abort the context; do not optimize the prompt inside it.**

## 8. Candidate isolation policy

After G-CTX passes:

- W1 gets its own generation context;
- W2 must not be discussed or generated in the W1 context;
- Artifact generation uses separate contexts by production batch;
- failed candidate images are not carried forward as references unless a specific local repair is approved;
- one context should not accumulate dozens of rejected visual priors.

Recommended hierarchy:

```text
Project / PR context
        │
        ├── W1 generation context
        │     ├── control probe
        │     ├── A variations
        │     └── selected candidate repair
        │
        ├── W2 generation context
        │
        └── Artifact batch contexts
```

## 9. Prompt optimization after context isolation

Once G-CTX passes, retain the useful findings from A–F:

### Keep

- explicit left 35% quiet zone;
- right-of-center street-depth focal cluster;
- concrete late-19th-century material vocabulary;
- practical amber light / blue-gray ambient separation;
- one local anomaly maximum;
- 4–6 candidate batch and blind semantic selection.

### Reduce

Avoid direct generator-facing phrases such as:

- secret society;
- occult order;
- hidden church;
- cosmic horror;
- dark fantasy;
- mysterious world.

Express the desired Lord-of-Mysteries quality primarily through:

- material age;
- institutional restraint;
- privacy / guarded interiors;
- lighting;
- mist;
- observation geometry;
- one low-frequency physical anomaly.

### Never rely on negative prompt alone

The experiment proves that “no text / no cathedral / no banner” is not sufficient when context prior is stronger than the immediate prompt.

## 10. Production decision

No A–F candidate is approved.

No failed image is committed.

Current W1 status remains:

```text
Image Contract: LOCKED
Generation method: REVISED
G-CTX: NOT YET PASSED
G0–G5: PENDING
Shipping artwork: NONE
```

The next valid production action is **not another prompt revision in the same conversation**.

It is:

> establish a clean W1-only generation context, run the control probe, then restart the A/B candidate batch only after G-CTX passes.
