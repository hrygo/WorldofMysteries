# W1 Art Direction Decision v3 — Crimson Moon Occult Metropolis

> Artwork: `W1_WORLD_HERO`  
> Decision: **APPROVED ART DIRECTION / SELECTED SOURCE LOCKED**  
> Finishing: **macOS pending**

## Why v3 exists

W1 v2 intentionally biased toward historical realism and very restrained supernatural cues. Interactive art review changed the product direction before shipping: the world hero should read more clearly as a premium narrative game, carry a much stronger occult atmosphere, and avoid photographic realism.

This is an explicit art-direction change, not a waiver of QA.

## Approved visual thesis

W1 should read as a stylized late-Victorian / industrial occult metropolis under a dominant crimson moon associated with the Evernight Goddess.

The image should preserve enough physical city logic to feel inhabited, while allowing the supernatural order to be visible in the sky, banners, silhouettes, architecture and atmosphere.

### Required

- premium-game illustration rather than historical-photo reconstruction;
- dense late-Victorian / industrial city readability;
- strong occult atmosphere at first glance;
- crimson moon as a major sky identity motif;
- rain, fog, smoke, wet stone and warm gaslight;
- small environmental figures / carriages for scale;
- dramatic but still navigable city depth;
- no dominant hero character.

### Allowed

- Gothic-inflected skyline and institutional silhouettes;
- non-textual occult banners, astronomical geometry and ritual motifs;
- visibly stylized clouds, moonlight and atmospheric exaggeration;
- stronger warm/cool contrast than a photoreal reference would use.

### Still forbidden

- readable invented slogans / fake shop copy as a visual motif;
- modern UI or baked interface chrome;
- floating islands / impossible fantasy geography;
- MMORPG party-poster composition;
- giant spell circles, laser-like magic or neon cyberpunk palette;
- independent regeneration of runtime derivatives.

## Selected source lock

Selected source generation ID:

```text
76a170ac-75e0-4013-9749-7f819fc1de0a
```

Native source:

```text
1586×992
SHA256 331d165b12f90bced6526e0f2dba36afb80c437100a10d88d194aa1653920ddd
```

Exact 16:10 working crop:

```text
1584×990
crop: 1 px from each edge
SHA256 b0417cab61588456fe0e3d554ff5b5f618d63dd84706cdced6a43e47914c9454
```

The source image itself is not added to `Assets.xcassets` until macOS finishing and G3–G5 are complete.

## Wide derivative decision

The crimson moon is an identity-bearing upper-frame subject. The previous centered 8:3 crop would remove it.

For W1 v3, the deterministic `2400×900` wide derivative must therefore use a **top-aligned 8:3 crop** from the 4096×2560 Master.

This preserves:

- the crimson moon;
- skyline identity;
- river / bridge depth;
- enough foreground city texture for the runtime card.

The full-frame `2560×1600` runtime derivative remains unchanged.

## Shipping boundary

Current state:

> **art direction approved / selected source locked / macOS finishing pending**

Shipping completion still requires the F1–F7 sequence in `docs/05_UI/artwork/W1_macOS_Finishing_Backlog.md`.
