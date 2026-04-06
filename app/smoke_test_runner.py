import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from deepseek_reviewer import review_scene_with_deepseek, structured_review_to_legacy_result
from lock_gate import apply_lock_gate, save_lock_gate_report
from main import build_manual_intervention_content
from review_models import ReviewStatus, StructuredReviewResult, save_repair_plan
from revision_lineage import append_revision_lineage


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = ROOT / "tests/fixtures/smoke_scenes"
ALLOWED_FINAL_STATUSES = {status.value for status in ReviewStatus}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def save_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_task_text(scene_meta: dict[str, Any]) -> str:
    constraints = "\n".join(f"- {item}" for item in scene_meta.get("constraints", []))
    sections = [
        f"# task_id\n{scene_meta['task_id']}",
        f"# goal\n{scene_meta['goal']}",
        f"# based_on\n{scene_meta['based_on']}",
        f"# chapter_state\n{scene_meta['chapter_state']}",
        f"# constraints\n{constraints}",
        f"# output_target\n{scene_meta['output_target']}",
    ]
    return "\n\n".join(sections) + "\n"


def build_artifact_root(base_root: Path | None = None) -> Path:
    if base_root is not None:
        return base_root
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    return ROOT / "02_working/test_artifacts/five_scene_smoke" / run_id


def build_manual_intervention_file(
    artifact_root: Path,
    task_text: str,
    reviewer_result: dict[str, Any],
    draft_file: str,
    max_revisions: int,
) -> str:
    task_id = reviewer_result["task_id"]
    rel_path = f"02_working/reviews/{task_id}_manual_intervention.md"
    save_text(
        artifact_root / rel_path,
        build_manual_intervention_content(
            task_text,
            reviewer_result,
            draft_file,
            max_revisions,
            trigger_reason=reviewer_result.get("force_manual_intervention_reason") or reviewer_result.get("summary"),
        ),
    )
    return rel_path


def classify_failure(decision_reason: str) -> tuple[int, int]:
    text = str(decision_reason).strip()
    parse_failures = 1 if "JSON 解析失败" in text else 0
    schema_failures = 1 if "schema 校验失败" in text else 0
    return parse_failures, schema_failures


def finalize_status(review_result: dict[str, Any]) -> str:
    status = str(review_result.get("verdict") or "manual_intervention").strip()
    if review_result.get("force_manual_intervention_reason"):
        return ReviewStatus.manual_intervention.value
    if status in {ReviewStatus.lock.value, ReviewStatus.revise.value, ReviewStatus.rewrite.value}:
        return status
    return ReviewStatus.manual_intervention.value


def ensure_expected_files(scene_result: dict[str, Any], artifact_root: Path) -> None:
    expected_paths = [
        scene_result["review_result_path"],
        scene_result["repair_plan_path"],
        scene_result["lineage_path"],
        scene_result["lock_gate_report_path"],
    ]
    if scene_result.get("manual_intervention_file"):
        expected_paths.append(scene_result["manual_intervention_file"])
    for rel_path in expected_paths:
        assert (artifact_root / rel_path).exists(), f"missing expected artifact: {rel_path}"


def run_five_scene_smoke_test(
    artifact_root: Path | None = None,
    reviewer_fn: Callable[[str, dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    artifact_root = build_artifact_root(artifact_root)
    artifact_root.mkdir(parents=True, exist_ok=True)
    manifest = read_json(FIXTURE_DIR / "scene_manifest.json")
    canon_context = read_json(FIXTURE_DIR / "canon_context.json")
    scenes = manifest.get("scenes", [])
    reviewer = reviewer_fn or review_scene_with_deepseek
    max_revisions = 5
    scene_results: list[dict[str, Any]] = []
    uncaught_exception_count = 0
    lock_count = 0
    revise_count = 0
    rewrite_count = 0
    manual_intervention_count = 0
    parse_failure_count = 0
    schema_failure_count = 0

    for scene_meta in scenes:
        task_id = scene_meta["task_id"]
        task_text = build_task_text(scene_meta)
        scene_text = read_text(FIXTURE_DIR / scene_meta["scene_file"])
        draft_file = scene_meta["output_target"]
        review_rel_path = f"02_working/reviews/{task_id}_review_result.json"
        repair_plan_path = f"02_working/reviews/{task_id}_repair_plan.json"
        reviewer_json_path = f"02_working/reviews/{task_id}_reviewer.json"
        manual_intervention_file = None

        try:
            structured_payload = reviewer(
                scene_text,
                {
                    **scene_meta,
                    "api_key_env": "DEEPSEEK_API_KEY",
                    "request_timeout": 120,
                    "max_retries": 3,
                    "retry_backoff_base": 1.0,
                },
                canon_context,
            )
            structured = StructuredReviewResult.from_dict(structured_payload)
        except Exception as error:
            uncaught_exception_count += 1
            structured = StructuredReviewResult(
                task_id=task_id,
                status=ReviewStatus.manual_intervention,
                summary="Smoke test scene 处理异常，转人工介入。",
                issues=[],
                strengths=[],
                decision_reason=f"Smoke test uncaught exception: {error}",
            )

        structured.save(artifact_root / review_rel_path)
        repair_plan_rel_path = save_repair_plan(artifact_root, structured)
        legacy_result = structured_review_to_legacy_result(structured.to_dict())
        save_text(artifact_root / reviewer_json_path, json.dumps(legacy_result, ensure_ascii=False, indent=2))

        lineage, lineage_path = append_revision_lineage(
            artifact_root,
            structured,
            draft_file,
            max_revisions,
        )

        gated_result, lock_gate_report = apply_lock_gate(task_text, legacy_result, max_revisions)
        lock_gate_report_path = save_lock_gate_report(artifact_root, lock_gate_report)

        final_status = finalize_status(gated_result)
        if final_status != structured.status.value:
            structured = StructuredReviewResult.from_dict(
                {
                    **structured.to_dict(),
                    "status": final_status,
                    "summary": gated_result.get("summary") or structured.summary,
                    "decision_reason": gated_result.get("summary") or structured.decision_reason,
                }
            )
            structured.save(artifact_root / review_rel_path)

        if final_status == ReviewStatus.manual_intervention.value:
            manual_intervention_file = build_manual_intervention_file(
                artifact_root,
                task_text,
                gated_result,
                draft_file,
                max_revisions,
            )

        parse_delta, schema_delta = classify_failure(structured.decision_reason)
        parse_failure_count += parse_delta
        schema_failure_count += schema_delta

        if final_status == ReviewStatus.lock.value:
            lock_count += 1
        elif final_status == ReviewStatus.manual_intervention.value:
            manual_intervention_count += 1
        elif final_status == ReviewStatus.rewrite.value:
            rewrite_count += 1
        else:
            revise_count += 1

        scene_result = {
            "task_id": task_id,
            "final_status": final_status,
            "review_result_path": review_rel_path,
            "repair_plan_path": repair_plan_rel_path,
            "lineage_path": lineage_path,
            "lock_gate_report_path": lock_gate_report_path,
            "reviewer_json_path": reviewer_json_path,
            "manual_intervention_file": manual_intervention_file,
            "decision_reason": structured.decision_reason,
            "issues": len(structured.issues),
            "lineage_round": len(lineage.revisions),
        }
        ensure_expected_files(scene_result, artifact_root)
        assert scene_result["final_status"] in ALLOWED_FINAL_STATUSES, f"invalid final status for {task_id}: {scene_result['final_status']}"
        scene_results.append(scene_result)

    assert len(scene_results) == 5, f"expected 5 scenes, got {len(scene_results)}"

    summary = {
        "artifact_root": str(artifact_root),
        "processed_scene_count": len(scene_results),
        "uncaught_exception_count": uncaught_exception_count,
        "counts": {
            "lock": lock_count,
            "revise": revise_count,
            "rewrite": rewrite_count,
            "manual_intervention": manual_intervention_count,
            "json_parse_failures": parse_failure_count,
            "schema_failures": schema_failure_count,
        },
        "scene_results": scene_results,
    }

    per_scene_summary_path = artifact_root / "per_scene_results.json"
    overall_summary_path = artifact_root / "overall_summary.txt"
    save_text(per_scene_summary_path, json.dumps(scene_results, ensure_ascii=False, indent=2))
    save_text(
        overall_summary_path,
        "\n".join(
            [
                "Five-scene smoke test summary",
                f"artifact_root={artifact_root}",
                f"processed_scene_count={len(scene_results)}",
                f"uncaught_exception_count={uncaught_exception_count}",
                f"lock={lock_count}",
                f"revise={revise_count}",
                f"rewrite={rewrite_count}",
                f"manual_intervention={manual_intervention_count}",
                f"json_parse_failures={parse_failure_count}",
                f"schema_failures={schema_failure_count}",
            ]
        )
        + "\n",
    )

    assert per_scene_summary_path.exists(), "missing per-scene summary"
    assert overall_summary_path.exists(), "missing overall summary"
    summary["per_scene_summary_path"] = str(per_scene_summary_path)
    summary["overall_summary_path"] = str(overall_summary_path)
    return summary


def main() -> None:
    summary = run_five_scene_smoke_test()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
