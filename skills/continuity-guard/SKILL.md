---
name: "continuity-guard"
description: "Use when writing or revising novel scenes that must stay aligned with canon, chapter state, tracker summaries, artifact positions, risk levels, relationship status, or timeline continuity. Best for scene writing, repair rounds, and any task that depends on recent locked scenes or story_state."
---

# Continuity Guard

Use this skill to keep a scene inside the project's established state instead of letting prose drift override canon.

## Use when

- The task depends on `chapter_state`, `story_state`, or tracker slices.
- The scene is a continuation, `revise`, or `rewrite` task.
- The draft must preserve artifact locations, risk levels, relationship status, or investigation stage.
- The user asks for stronger continuity or canon consistency.

## Do not use when

- The task is pure brainstorming with no canon constraints.
- The task is only naming or only worldbuilding.

## Required inputs

Read only the files you need:

- `01_inputs/tasks/current_task.md`
- `03_locked/canon/chXX_state.md` when present in the task
- `03_locked/state/story_state.json`
- relevant tracker files under `03_locked/state/trackers/`
- recent locked scenes or structured summaries only if needed

## Workflow

1. Extract the non-drift fields from the task and current state.
2. Identify the highest-risk continuity items before writing.
3. Convert those items into short writer guardrails.
4. If a draft already exists, compare the draft against those guardrails.
5. Prefer blocking drift over inventing patch explanations.

## Output contract

Produce a short structured checklist, not freeform lore. Keep it to the fields the writer must actively preserve.

Recommended shape:

```json
{
  "skill": "continuity-guard",
  "mode": "scene-canon",
  "must_check": [
    "current book time",
    "investigation stage",
    "artifact holder and location"
  ],
  "high_risk_conflicts": [
    "Do not move a hidden item back into storage if tracker says it is carried on body."
  ],
  "non_drift_fields": [
    "risk level",
    "relationship status",
    "last locked scene consequence"
  ]
}
```

## Hard rules

- Do not create new canon to cover a continuity mistake.
- Do not explain away conflicts with vague narration.
- If canon and task conflict, surface the conflict explicitly and preserve canon unless the user changed it.
- Prefer short, testable statements over interpretive summaries.

## Modes

- `scene-canon`: general scene writing continuity
- `artifact-state`: object holder, location, visibility
- `timeline-check`: current time, relative order, scene bridge
- `repair-check`: high-risk items for revise/rewrite rounds

## Reference map

Read only what you need:

- `references/checklist.md` for the standard continuity checklist
- `references/conflicts.md` for typical drift patterns and what to do
