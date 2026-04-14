---
name: "worldbuilding"
description: "Use when a novel project needs worldbuilding patches, institutional logic, regional staging, power-system constraints, or writing-facing setting completions. Best for planning/bootstrap, manifesto gaps, chapter-prep proposals, and any task where the world needs more executable detail without turning into encyclopedia text."
---

# Worldbuilding

Use this skill to patch setting gaps in a way that directly improves scene writing.

## Use when

- The project needs worldbuilding completion proposals.
- Manifest materials are thematic but not yet operational.
- The task needs institutional response, spatial hierarchy, power-system limits, or region-specific survival logic.
- The user wants setting that affects behavior, pressure, and consequences.

## Do not use when

- The task is pure naming.
- The task is only about scene-level prose.
- The task is just continuity checking.

## Required inputs

Read only what is necessary:

- `00_manifest/novel_manifest.md`
- `00_manifest/world_bible.md`
- relevant planning patches under `02_working/planning/`
- chapter outline if the patch must support a specific chapter

## Workflow

1. Identify the missing operational dimension.
2. Translate abstract setting into constraints on ordinary life.
3. Prefer systems that can show up in labor, trade, risk, surveillance, travel, or ritual.
4. Produce a patch proposal with direct writer hooks.
5. Keep the patch compatible with current canon.

## Output contract

Recommended shape:

```json
{
  "skill": "worldbuilding",
  "mode": "institutional",
  "gaps": ["ecology and social response"],
  "patches": [
    "show how abnormal danger enters the ordinary handling chain",
    "define how officials and common people respond differently"
  ],
  "writer_usable_hooks": [
    "labor roles that absorb danger",
    "spatial signs of pressure"
  ]
}
```

## Hard rules

- Patch for writeability, not for lore volume.
- Every addition should answer who benefits, who pays, and how the pressure reaches the body.
- Do not introduce a separate cosmology unless the manifest already supports it.
- Do not use worldbuilding as an excuse to open a new main plot.

## Modes

- `institutional`: laws, taxes, labor chains, surveillance, official response
- `regional`: geography, trade flow, local survival patterns, stage hierarchy
- `power-system`: costs, boundaries, access rules, ordinary-world consequences

## Reference map

Read only what you need:

- `references/patch-patterns.md` for setting patch templates
- `references/writer-hooks.md` for converting setting into scene-usable hooks
