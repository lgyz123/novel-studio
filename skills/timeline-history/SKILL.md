---
name: "timeline-history"
description: "Use when a novel workflow needs world-history anchors, chapter time sequencing, scene-to-scene bridging, relative time clarity, or timeline risk detection. Best for planning/bootstrap, chapter preparation, and any task where chronology must be explicit and stable."
---

# Timeline History

Use this skill to make chronology explicit enough for planning and scene writing to stay stable.

## Use when

- The project needs historical anchors or chapter-sequence planning.
- A scene must clearly bridge from the previous time point.
- The task mentions current time, next day, prior event, or historical context.
- The writer needs help preventing time blur.

## Do not use when

- The task is pure naming.
- The task is only prose style enhancement.
- The task is only continuity checking with no timeline gap.

## Required inputs

Read only what is necessary:

- `01_inputs/tasks/current_task.md`
- `03_locked/canon/chXX_state.md` if present
- `03_locked/state/story_state.json`
- planning patches when they already exist

## Workflow

1. Identify the current time anchor.
2. Clarify relative order against the previous scene or prior event.
3. Add history anchors only when they support the present situation.
4. Surface likely time-drift risks.
5. Return a compact timeline note, not a long chronology essay.

## Output contract

Recommended shape:

```json
{
  "skill": "timeline-history",
  "mode": "scene-bridge",
  "current_time": "次日清早",
  "relative_order": [
    "上一场发生在夜里",
    "本场与上一场相隔一夜"
  ],
  "history_anchors": [
    "旧制成形",
    "一场大灾后差役加重"
  ],
  "timeline_risks": [
    "如果不写明白天，读者会误以为仍在同一夜"
  ]
}
```

## Hard rules

- Relative order first, lore second.
- Do not invent distant history that does not affect the present chapter.
- Keep time markers scene-usable.
- If story_state has a stronger time signal, preserve it.

## Modes

- `world-history`
- `chapter-sequence`
- `scene-bridge`

## Reference map

Read only what you need:

- `references/anchors.md` for time-anchor patterns
- `references/drift.md` for common time-blur failures
