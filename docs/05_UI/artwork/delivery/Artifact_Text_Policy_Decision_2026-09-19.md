# Artifact text policy decision — decorative inscription accepted (2026-09-19)

## What was decided

The user approved the baked lettering that the structural inspection recorded on A02 and A03:

> 文字批准，那种类符文文字不是问题，因为它不是文案。

Spine printing and engraved cover inscriptions are rune-like ornament on the material and
decoration layer. They carry no UI copy and no narrative text, so the text-free-art product policy
does not cover them. The same decision confirms approval of all 15 Artifact artworks.

## Machine-readable record

[`../contracts/art_direction_text_decision.json`](../contracts/art_direction_text_decision.json)
holds the part a tool can act on: the decision kind, who decided it, and, per artwork, which
recorded defect ids the decision clears. Every revised QA / provenance record stores that file's
sha256, so the link between a decision and the records it changed is auditable rather than implied.

The exception is deliberately narrow, and the tool enforces each clause:

- only defects whose id starts with the tool's own lettering vocabulary (`baked_readable_text…`)
  can be cleared;
- only defects the inspection actually recorded for that artwork can be cleared;
- the inspection itself is never rewritten: the recorded defect stays in `defects_found`, and the
  cleared ones are mirrored into `accepted_defects` alongside the decision reference;
- any other defect — including everything non-lettering — keeps G3 open, and G0 only closes when a
  finished-master semantic read exists;
- a missing, malformed or non-covering decision file leaves G0 and G3 exactly as they were.

## Records revised

`finish_artifact_artwork.py apply-text-decision` was used instead of a full `record` re-run because
the runtime capture bytes behind G5 are not committed and are no longer on this machine: re-running
`record` would have to drop a verified G5 back to `PENDING_RUNTIME_QA`. The command revises only the
gates the decision touches, carries every other gate over verbatim, refuses to run when the QA and
provenance gate tables disagree, and records the sha256 of the input record.

| Artwork | G0 | G3 | Open after the decision |
|---|---|---|---|
| `A02_ALZUHOD_QUILL` | `PENDING_MACOS_FINISHING` → `PASSED` | `PENDING_MACOS_FINISHING` → `PASSED` | none — `final_verdict: PASSED`, provenance `APPROVED` |
| `A03_TRUNSOEST_BRASS_BOOK` | `PENDING_MACOS_FINISHING` → `PASSED` | `PENDING_MACOS_FINISHING` → `PASSED` | `G1_canon_atmosphere` |

Re-run either revision with the command recorded in
[`../Artifact_Finishing_Pipeline_v1.0.md`](../Artifact_Finishing_Pipeline_v1.0.md#running-it).

## What stays open

- **G1 Canon review** for the twelve objects with no recorded primary form claim (A03–A06 and
  A08–A15). Visual approval is not Canon verification, and this decision deliberately does not
  touch G1.
- **Shipping approval**: every Artifact record still carries `shipping_approved: false`. Delivering
  runtime bytes and passing gates is not a shipping approval.
