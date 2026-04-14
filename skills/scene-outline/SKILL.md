---
name: "scene-outline"
description: "Use when a novel task needs chapter outline work, scene contracts, plot-progress scaffolding, next-scene seeds, or structural constraints like required information gain, decision shift, and end-state change. Best for planning/bootstrap, chapter outlining, and repair tasks where the writer needs a clearer scene goal."
---

# Scene Outline

Use this skill to turn vague scene intent into a compact structural contract the writer can actually satisfy.

## Use when

- The task is for chapter outline, scene planning, or next-scene generation.
- The task includes fields like `scene_purpose`, `required_information_gain`, `required_plot_progress`, `required_decision_shift`, or `required_state_change`.
- Reviewer output says the scene lacks new information, plot progress, or a decision shift.

## Do not use when

- The task is pure prose polishing with no structural changes.
- The task is only about naming or lore expansion.

## Required inputs

Read only what matters:

- `01_inputs/tasks/current_task.md`
- recent structured scene summaries when available
- current chapter outline or planning assets
- relevant tracker slices if the scene must preserve chapter pacing

## Workflow

1. Extract the scene's function in the chapter.
2. Convert vague goals into 3-5 structural obligations.
3. Make the ending shape explicit.
4. Remove obligations that do not affect scene behavior.
5. Return a concise contract the writer can follow.

## Output contract

Recommended shape:

```json
{
  "skill": "scene-outline",
  "mode": "scene-contract",
  "scene_function": "introduce external resistance",
  "must_land": {
    "new_information": ["confirm a new risk condition"],
    "plot_progress": "the obstruction escalates before the end",
    "decision_shift": "the protagonist changes how he handles the clue",
    "state_change": ["risk level changes"]
  },
  "ending_shape": "the ending must contain a real consequence, not only mood"
}
```

## Hard rules

- Define structure, not finished prose.
- Keep the contract behavior-first: what changes, what is learned, what action shifts.
- Do not expand unrelated subplots.
- If the task already has a strong contract, compress it rather than replacing it.

## Modes

- `chapter-outline`: chapter-level sequence and anchors
- `scene-contract`: one scene's structural obligations
- `next-scene-seed`: handoff for the next scene task

## Reference map

Read only what you need:

- `references/contract-patterns.md` for scene-contract templates
- `references/chapter-shapes.md` for chapter-level pacing patterns
