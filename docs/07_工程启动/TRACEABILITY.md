# Implementation Traceability v1.0

| Design Requirement | Engineering Asset | Primary Gate |
|---|---|---|
| Embedded Local Engine Service | Local_Engine_Packaging_Spike_v1.0.md | GATE-PACKAGE |
| Swift/Python separation | IPC_Protocol_v1.0.md | GATE-PROTOCOL |
| AgentScope = execution, not truth | AgentScope_Spike_v1.0.md | GATE-AI |
| Domain proposal → validator → commit | AgentScope_Spike + Golden runtime | GATE-AI / GATE-GOLDEN-MOCK |
| SQLite Truth Kernel | Data_Kernel_Spike_v1.0.md | GATE-DATA |
| Transactional Outbox | Data_Kernel_Spike_v1.0.md | GATE-DATA |
| retrieval.db rebuildable | Data_Kernel_Spike_v1.0.md | GATE-DATA |
| Knowledge before semantic retrieval | Data Kernel + Golden runtime | GATE-DATA / GATE-GOLDEN-MOCK |
| Truth != Knowledge != Belief != Memory | Golden runtime + Domain implementation | GATE-GOLDEN-MOCK |
| Worldline isolation | Data_Kernel_Spike_v1.0.md | GATE-DATA |
| Advice != Command | Golden runtime action intents | GATE-GOLDEN-MOCK |
| Character Reasoner cannot decide success | Golden runtime + Resolver | GATE-GOLDEN-MOCK |
| Narrative after Commit | Golden runtime narrative blocks | GATE-GOLDEN-MOCK |
| Narrative/TTS retry cannot reroll fate | Golden runtime failure checkpoints | GATE-GOLDEN-MOCK |
| PRE_COMMIT cancel / POST_COMMIT no rollback | IPC + Runtime tests | GATE-PROTOCOL / GATE-VOICE |
| Raw audio ephemeral | Security_Privacy_Baseline_v1.0.md | GATE-SECURITY |
| Content provenance | Content_Provenance_Release_Gate_v1.0.md | GATE-CONTENT |
| Single contract source | IPC + contracts | GATE-PROTOCOL |
| Golden 001 = first vertical slice | golden_001_runtime/ | GATE-GOLDEN-MOCK |
