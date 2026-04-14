---
name: "naming"
description: "Use when a novel workflow needs names for people, places, sects, organizations, artifacts, techniques, shops, or era labels. Best for planning, character creation, outline preparation, and scene writing tasks that explicitly ask for naming or title generation."
---

# Naming

Use this skill to generate names that fit the project's genre, social layer, tone, and existing canon.

## Use when

- The task explicitly asks for naming, titles, labels, or candidate lists.
- Character creation needs a person name.
- Worldbuilding needs place names, sect names, artifact names, or technique names.
- Outline work needs placeholder names upgraded into usable canon candidates.

## Do not use when

- The task already has fixed canon names.
- The task is about prose refinement with no naming need.

## Required inputs

Read only what you need:

- `01_inputs/tasks/current_task.md`
- relevant character or world manifest excerpts
- existing canon names when collision risk matters

## Workflow

1. Determine the `name_type`.
2. Extract genre, era, region, and class signals.
3. Avoid collisions with existing canon.
4. Produce compact candidates with style labels and usage hints.
5. Prefer usable names over ornamental names.

## Output contract

Recommended shape:

```json
{
  "skill": "naming",
  "mode": "person",
  "candidates": [
    {
      "name": "孟浮灯",
      "style_tags": ["古风", "冷感", "底层"],
      "meaning_or_feel": "漂泊里带一点微光",
      "fit_for": "主角"
    }
  ]
}
```

## Hard rules

- Do not output names that obviously clash with current canon.
- Do not rely on rare-character gimmicks as the main source of distinction.
- Match genre and class first, flourish second.
- Explain why a candidate fits the role.

## Modes

- `person`
- `place`
- `organization`
- `artifact`
- `technique`

## Reference map

Read only what you need:

- `references/person.md` for person-name guidance
- `references/world.md` for place, sect, artifact, and technique naming
