---
name: "character-design"
description: "Use when a novel workflow needs character cards, supporting-role functions, relationship tension design, behavior markers, or compact person-building that can directly guide scenes. Best for character creation, planning, outline work, and scene writing tasks centered on a person's role or interaction pattern."
---

# Character Design

Use this skill to build role cards that are small, functional, and scene-usable.

## Use when

- The task asks for character setup, role cards, supporting roles, or relationship tension.
- Planning/bootstrap needs a sharper protagonist, supporting role, or pressure source.
- A scene depends on how a person behaves, speaks, blocks, tempts, or redirects action.

## Do not use when

- The task is only naming.
- The task is only worldbuilding or timeline work.
- The task already has a complete locked role card and only needs continuity checking.

## Required inputs

Read only what is necessary:

- `01_inputs/tasks/current_task.md`
- relevant excerpts from `00_manifest/character_bible.md`
- chapter outline or planning notes if the character serves a specific scene function

## Workflow

1. Decide whether the task needs a protagonist card, supporting-role card, or relationship-tension card.
2. Start from function, not biography.
3. Add behavior markers that can show up in scene action.
4. Keep speech tendency and tension direction explicit.
5. Return a compact card rather than a long profile.

## Output contract

Recommended shape:

```json
{
  "skill": "character-design",
  "mode": "supporting-role",
  "card": {
    "core_drive": "求稳避险",
    "external_function": "提供低烈度阻力",
    "behavior_markers": ["说话收着", "先看人脸色再答"],
    "speech_tendency": "短句，偏试探",
    "tension_with_protagonist": "让主角更难直接问出口"
  }
}
```

## Hard rules

- Function first, backstory second.
- Do not inflate a supporting role into a second protagonist.
- Behavior markers must be writable as concrete action.
- Keep the card compatible with current canon.

## Modes

- `protagonist-card`
- `supporting-role`
- `relationship-tension`

## Reference map

Read only what you need:

- `references/cards.md` for compact role-card patterns
- `references/tension.md` for relationship and interaction pressure design
