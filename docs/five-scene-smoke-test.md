# Five-Scene Smoke Test

运行 5 个预定义 scene 的端到端 smoke test：

```bash
cd /Users/guan/git/novel-studio
export DEEPSEEK_API_KEY="your-key"
/Users/guan/git/.venv/bin/python app/run_five_scene_smoke_test.py
```

输出会保存到：

- `02_working/test_artifacts/five_scene_smoke/<run_id>/per_scene_results.json`
- `02_working/test_artifacts/five_scene_smoke/<run_id>/overall_summary.txt`

说明：

- `reviewer`/`writer` 主流程不变；这个 smoke test 单独调用 DeepSeek reviewer 来验证结构化 review 落盘稳定性。
- `lock gate` 仍然使用本地 deterministic 规则。
- 如果 DeepSeek 返回无效 JSON 或 schema 不匹配，会自动降级为 `manual_intervention`，并计入失败统计。
