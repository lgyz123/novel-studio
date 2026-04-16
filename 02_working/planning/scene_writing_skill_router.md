# scene writing skill router

- phase：scene_writing
- genre_tags：xianxia
- trope_tags：system
- demand_tags：continuity、scene-writing、naming

## selected_skills
- continuity-guard｜mode=scene-canon｜score=0.95｜scene 写作依赖 chapter_state、story_state 或 tracker 承接，默认必须启用 continuity-guard。
- naming｜mode=person｜score=0.64｜当前任务包含明确命名需求，应补充 naming 候选与风格约束。

## rejected_candidates
- scene-outline｜mode=scene-contract｜score=0.42｜当前由 task contract 直接约束场景，暂不重复加载 scene-outline。
- worldbuilding｜mode=institutional｜score=0.2｜当前是正文落稿阶段，世界观补丁已应在 planning 阶段提前生成。

## risk_flags
- 无
