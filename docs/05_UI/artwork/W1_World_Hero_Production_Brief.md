# W1 — World Hero Production Brief

> Program: Premium Art A1  
> Artwork ID: `W1_WORLD_HERO`  
> Status: PRODUCTION BRIEF LOCKED  
> Role: `world_hero`

## 1. Product purpose

W1 is the primary visual statement for the World of Mysteries macOS experience. It must make the world feel physically inhabited before it feels supernatural.

The composition is not a splash-screen poster and must remain usable behind real SwiftUI chrome, titles, status and navigation.

## 2. Canon-safe visual thesis

**Industrial-age reality first; supernatural intrusion second.**

The scene should communicate:
- late-Victorian / early-industrial European urban fabric;
- wet stone, soot, dark timber, iron, brass, glass and paper-lit interiors;
- practical gas / warm window light against blue-gray exterior atmosphere;
- restrained occult evidence entering ordinary reality;
- no dependency on a specific copyrighted official composition or commercial key art.

This is a product-level world hero, not a claim that one exact street or landmark is canonically depicted.

## 3. Confirmed / allowed scene ingredients

Allowed:
- dense European industrial city streets and roofs;
- stone façades, brick, ironwork, gas lamps, chimneys, distant mechanical infrastructure;
- damp pavement / atmospheric haze / coal-smoke traces;
- small-scale human presence for lived-in scale;
- subtle impossible reflection, shadow error, distant anomalous light, or localized mist behavior;
- restrained aged-brass or cold-silver visual accents.

Do not imply a specific named canonical building unless separately evidenced and approved.

## 4. Forbidden visual shortcuts

- no all-purple occult palette;
- no giant glowing runes across the sky;
- no tentacle wallpaper;
- no floating fantasy castle;
- no giant moon/sigil as the dominant subject;
- no high-saturation mobile-game gold;
- no baked UI text, logos, labels or fake interface panels;
- no copied official animation/game/comic composition;
- no steampunk cosplay excess: gears are not decoration by default.

## 5. Visual verb

- **Primary verb:** `inhabit`
- **Secondary verb:** `intrude`

The image should first read as a real city one could walk into. Only on second inspection should the viewer notice that something is slightly wrong.

## 6. Material & lighting direction

### Materials
- rain-darkened stone;
- blackened iron;
- oxidized brass;
- stained glass and ordinary window glass;
- soot-aged brick;
- damp timber;
- paper and fabric glimpsed through interiors.

### Practical light
- warm gas lamps;
- restrained amber shop/window light;
- overcast blue-gray ambient sky.

### Supernatural local light
At most one or two localized anomalies:
- cold silver-blue reflection without a visible source;
- mist moving counter to wind;
- distant light behind fog with impossible depth;
- subtle window/reflection mismatch.

No global bloom wash.

## 7. Composition contract

### Master / derivatives
- Master target: `4096×2560`
- Runtime target: `2560×1600`
- Optional header crop: `2400×900`

### Focus zone
Primary environmental focal region should sit **right-of-center**, approximately x=55–78%, y=28–72%.

Suggested focal identity:
- layered street depth / roofs / tower silhouettes / practical light cluster;
- one subtle supernatural anomaly near or beyond that cluster.

### Quiet zone
Reserve **left 32–38%** as a relatively low-frequency region suitable for title, world status and shell UI.

Quiet zone requirements:
- no bright lamp directly under expected text;
- no face or critical subject;
- no high-frequency signage;
- stable dark-mid luminance suitable for controlled scrim.

### Crop reserve
- keep primary subject at least 12% away from right/top/bottom edges;
- avoid semantic content in outer 8%;
- center crop to 16:10 must preserve city depth + anomaly;
- 2400×900 derivative must preserve a recognizable city horizon and one practical-light cluster.

## 8. Contrast / UI overlay contract

The image itself does not need to make raw text readable everywhere.

Approved runtime treatment:
- left-to-right dark scrim over quiet zone;
- optional material/surface behind dense text;
- artwork detail may be reduced under Increased Contrast / Reduce Transparency modes.

Acceptance:
- `textPrimary` on the approved hero scrim >= 4.5:1;
- important long hero copy should target >= 7:1;
- artwork must not force body text directly over high-frequency detail.

## 9. Color target

Dominant:
- blue-gray slate;
- charcoal;
- wet stone;
- desaturated brown / dark timber.

Secondary:
- aged brass;
- gaslight amber;
- cold silver-blue supernatural accent.

Forbidden dominant:
- saturated purple;
- cyan-magenta neon;
- orange-gold fantasy glow.

## 10. Generation / production prompt core

Create an original cinematic late-Victorian industrial city environment for a premium macOS dark-fantasy application. The city must feel materially real and inhabited before it feels supernatural: wet dark stone streets, soot-aged brick and masonry, blackened iron, oxidized brass, practical gas lamps, warm window light, blue-gray overcast atmosphere, layered roofs and chimneys, restrained human scale. Place the strongest environmental focal cluster right-of-center and preserve a calm darker quiet zone across the left third for interface text. Introduce only one subtle supernatural intrusion—an impossible cold reflection, localized gray mist with unnatural depth, or distant silver-blue light with no visible source. Realistic materials, restrained cosmic horror, archival mysticism, premium cinematic environment art, no typography, no UI, no logos, no giant runes, no purple magic wash, no floating fantasy castle, no tentacles, no excessive gears, no excessive bloom. Composition must remain useful for 16:10 desktop crop and a wide 2400×900 header crop.

## 11. Negative prompt / rejection cues

Reject if any of the following dominate:
- baked text / fake signage / gibberish;
- character portrait as primary subject;
- giant occult sigil;
- purple/cyan neon palette;
- empty generic gothic castle;
- fantasy armor / heroic party staging;
- modern skyscrapers;
- steampunk gear collage;
- excessive fog hiding all material reality;
- no usable quiet zone.

## 12. QA checklist

- [ ] city reality reads before supernatural effect
- [ ] left quiet zone survives 16:10 crop
- [ ] optional 2400×900 crop remains coherent
- [ ] practical light remains believable
- [ ] no baked text / gibberish
- [ ] no dominant purple/neon
- [ ] no copied commercial composition
- [ ] anomaly is local, not a universal filter
- [ ] texture/detail does not destroy UI readability
- [ ] 960×640 hero crop remains useful
- [ ] 1180×760 default composition feels balanced
- [ ] provenance recorded

## 13. Provenance record

- Production method: AI-assisted original artwork + human visual QA
- Source references: project A0 research / canon-safe world art direction
- Copyright note: original derivative visual; no official commercial asset copying
- Final status: `DRAFT` until image-level QA passes
