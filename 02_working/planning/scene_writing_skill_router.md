# scene writing skill router

- phase：scene_writing
- genre_tags：xianxia
- trope_tags：system
- demand_tags：continuity、scene-writing、character、naming

## selected_skills
- continuity-guard｜mode=scene-canon｜score=0.95｜scene 写作依赖 chapter_state、story_state 或 tracker 承接，默认必须启用 continuity-guard。
- character-design｜mode=supporting-role｜score=0.67｜当前任务显式涉及人物设定或关系描写，补充 character-design 可让人物功能与行为锚点更稳定。
- naming｜mode=person｜score=0.64｜当前任务包含明确命名需求，应补充 naming 候选与风格约束。

## rejected_candidates
- worldbuilding｜mode=institutional｜score=0.2｜当前是正文落稿阶段，世界观补丁已应在 planning 阶段提前生成。

## risk_flags
- 无
