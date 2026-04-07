import argparse
import json
import re
from pathlib import Path
from typing import Any

from chapter_trackers import build_scene_summary_report_path, classify_scene_function, list_locked_chapter_files, safe_load_json
from deepseek_supervisor import classify_scene_type_from_summary


ROOT = Path(__file__).resolve().parent.parent


def normalize_string_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def scene_type_from_function(scene_function: str) -> str:
    scene_function = str(scene_function or "").strip()
    if scene_function == "过渡/氛围":
        return "transition"
    pseudo_summary = {"scene_function": scene_function}
    return classify_scene_type_from_summary(pseudo_summary)


def find_scene_related_json(root: Path, scene_id: str, directory: str, suffixes: list[str]) -> dict[str, Any]:
    base_dir = root / directory
    if not base_dir.exists():
        return {}
    for suffix in suffixes:
        matches = sorted(base_dir.glob(f"*{scene_id}*{suffix}"))
        if matches:
            data = safe_load_json(matches[-1])
            if isinstance(data, dict):
                return data
    return {}


def build_fallback_scene_summary(scene_id: str, scene_text: str, reviewer_result: dict[str, Any]) -> dict[str, Any]:
    information_gain = reviewer_result.get("information_gain") or {}
    character_decision = reviewer_result.get("character_decision") or {}
    canon_consistency = reviewer_result.get("canon_consistency") or {}
    return {
        "scene_id": scene_id,
        "scene_function": classify_scene_function(scene_text),
        "new_information_items": normalize_string_list(information_gain.get("new_information_items", [])),
        "protagonist_decision": str(character_decision.get("decision_detail") or "").strip(),
        "state_changes": [],
        "motifs_used": [],
        "motif_functions": {},
        "artifacts_changed": [],
        "open_questions_created": [],
        "open_questions_resolved": [],
        "reveal_changes": {},
        "canon_risk_flags": normalize_string_list(canon_consistency.get("consistency_issues", [])),
    }


def count_decisions(scene_summary: dict[str, Any], reviewer_result: dict[str, Any]) -> int:
    if str(scene_summary.get("protagonist_decision") or "").strip():
        return 1
    character_decision = reviewer_result.get("character_decision") or {}
    return 1 if character_decision.get("has_decision_or_behavior_shift") else 0


def count_state_changes(scene_summary: dict[str, Any]) -> int:
    state_changes = normalize_string_list(scene_summary.get("state_changes", []))
    artifact_changes = scene_summary.get("artifacts_changed", []) if isinstance(scene_summary.get("artifacts_changed"), list) else []
    artifact_labels = []
    for item in artifact_changes:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("item_id") or "").strip()
        if label and label not in artifact_labels:
            artifact_labels.append(label)
    return len(state_changes) + len(artifact_labels)


def extract_artifact_drift_issues(scene_summary: dict[str, Any], reviewer_result: dict[str, Any], lock_gate_report: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    issues.extend([item for item in normalize_string_list(scene_summary.get("canon_risk_flags", [])) if "artifact_state" in item or "物件" in item])
    issues.extend([item for item in normalize_string_list((reviewer_result.get("canon_consistency") or {}).get("consistency_issues", [])) if "artifact_state" in item or "物件" in item])
    for check in lock_gate_report.get("checks", []) if isinstance(lock_gate_report.get("checks"), list) else []:
        if isinstance(check, dict) and str(check.get("name") or "") == "chapter_state_alignment" and not check.get("passed", True):
            details = str(check.get("details") or "").strip()
            if "artifact_state" in details or "物件" in details:
                issues.append(details)
    return normalize_string_list(issues)


def extract_reveal_risks(scene_summary: dict[str, Any], reviewer_result: dict[str, Any], lock_gate_report: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    reveal_markers = ["提前揭示", "关系未知", "熟识", "真实身份", "揭示"]
    issues.extend([item for item in normalize_string_list(scene_summary.get("canon_risk_flags", [])) if any(marker in item for marker in reveal_markers)])
    issues.extend([item for item in normalize_string_list((reviewer_result.get("canon_consistency") or {}).get("consistency_issues", [])) if any(marker in item for marker in reveal_markers)])
    for check in lock_gate_report.get("checks", []) if isinstance(lock_gate_report.get("checks"), list) else []:
        if isinstance(check, dict) and str(check.get("name") or "") == "chapter_state_alignment" and not check.get("passed", True):
            details = str(check.get("details") or "").strip()
            if any(marker in details for marker in reveal_markers):
                issues.append(details)
    return normalize_string_list(issues)


def compute_same_function_motif_repeats(previous_scene: dict[str, Any] | None, current_scene: dict[str, Any]) -> list[str]:
    if not previous_scene:
        return []
    current_motif_functions = current_scene.get("motif_functions", {}) if isinstance(current_scene.get("motif_functions"), dict) else {}
    previous_motif_functions = previous_scene.get("motif_functions", {}) if isinstance(previous_scene.get("motif_functions"), dict) else {}
    repeated: list[str] = []
    for label, functions in current_motif_functions.items():
        current_functions = set(normalize_string_list(functions))
        previous_functions_for_label = set(normalize_string_list(previous_motif_functions.get(label, [])))
        if current_functions and current_functions & previous_functions_for_label and label not in repeated:
            repeated.append(label)
    return repeated


def collect_same_function_runs(scene_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    current_run: list[dict[str, Any]] = []
    for record in scene_records:
        if not current_run or record["scene_function"] == current_run[-1]["scene_function"]:
            current_run.append(record)
            continue
        if len(current_run) >= 2:
            runs.append(
                {
                    "scene_function": current_run[0]["scene_function"],
                    "scene_type": current_run[0]["scene_type"],
                    "scene_ids": [item["scene_id"] for item in current_run],
                    "length": len(current_run),
                }
            )
        current_run = [record]
    if len(current_run) >= 2:
        runs.append(
            {
                "scene_function": current_run[0]["scene_function"],
                "scene_type": current_run[0]["scene_type"],
                "scene_ids": [item["scene_id"] for item in current_run],
                "length": len(current_run),
            }
        )
    return runs


def analyze_chapter(root: Path, chapter_id: str) -> dict[str, Any]:
    story_state = safe_load_json(root / "03_locked/state/story_state.json") or {}
    tracker_bundle = {
        "chapter_motif_tracker": safe_load_json(root / f"03_locked/state/trackers/{chapter_id}_chapter_motif_tracker.json"),
        "revelation_tracker": safe_load_json(root / f"03_locked/state/trackers/{chapter_id}_revelation_tracker.json"),
        "artifact_state": safe_load_json(root / f"03_locked/state/trackers/{chapter_id}_artifact_state.json"),
        "chapter_progress": safe_load_json(root / f"03_locked/state/trackers/{chapter_id}_chapter_progress.json"),
    }
    scene_paths = list_locked_chapter_files(root, chapter_id)
    scene_records: list[dict[str, Any]] = []

    previous_scene_summary: dict[str, Any] | None = None
    previous_record: dict[str, Any] | None = None
    for scene_path in scene_paths:
        scene_id = scene_path.stem
        scene_text = read_text(scene_path)
        scene_summary_report = safe_load_json(root / build_scene_summary_report_path(scene_id)) or {}
        reviewer_result = find_scene_related_json(root, scene_id, "02_working/reviews", ["_review_result.json", "_reviewer.json"])
        lock_gate_report = find_scene_related_json(root, scene_id, "03_locked/reports", ["_lock_gate_report.json"])

        scene_summary = scene_summary_report.get("scene_summary") if isinstance(scene_summary_report.get("scene_summary"), dict) else {}
        if not scene_summary:
            scene_summary = build_fallback_scene_summary(scene_id, scene_text, reviewer_result)

        scene_function = str(scene_summary.get("scene_function") or classify_scene_function(scene_text)).strip()
        scene_type = classify_scene_type_from_summary(scene_summary)
        new_information_items = normalize_string_list(scene_summary.get("new_information_items", []))
        if not new_information_items:
            new_information_items = normalize_string_list((reviewer_result.get("information_gain") or {}).get("new_information_items", []))
        motif_redundancy = reviewer_result.get("motif_redundancy") or {}
        same_function_motif_repeats = compute_same_function_motif_repeats(previous_scene_summary, scene_summary)
        same_function_motif_repeats.extend(normalize_string_list(motif_redundancy.get("repeated_same_function_motifs", [])))
        same_function_motif_repeats = normalize_string_list(same_function_motif_repeats)

        artifact_drift_issues = extract_artifact_drift_issues(scene_summary, reviewer_result, lock_gate_report)
        reveal_risks = extract_reveal_risks(scene_summary, reviewer_result, lock_gate_report)
        lock_failed_checks = [
            {"name": str(item.get("name") or "").strip(), "details": str(item.get("details") or "").strip()}
            for item in lock_gate_report.get("checks", [])
            if isinstance(item, dict) and not item.get("passed", True)
        ]

        record = {
            "scene_id": scene_id,
            "locked_file": scene_path.as_posix(),
            "scene_function": scene_function,
            "scene_type": scene_type,
            "new_information_count": len(new_information_items),
            "decision_count": count_decisions(scene_summary, reviewer_result),
            "state_change_count": count_state_changes(scene_summary),
            "motif_usage_count": len(normalize_string_list(scene_summary.get("motifs_used", []))),
            "repeated_motif_count": len(normalize_string_list(motif_redundancy.get("repeated_motifs", []))),
            "same_function_motif_repeat_count": len(same_function_motif_repeats),
            "artifact_drift_count": len(artifact_drift_issues),
            "reveal_risk_count": len(reveal_risks),
            "review_verdict": str(reviewer_result.get("verdict") or "unknown").strip(),
            "lock_passed": bool(lock_gate_report.get("passed", False)) if lock_gate_report else False,
            "lock_failed_checks": lock_failed_checks,
            "artifact_drift_issues": artifact_drift_issues,
            "reveal_risks": reveal_risks,
            "same_function_motif_repeats": same_function_motif_repeats,
            "new_information_items": new_information_items,
            "scene_summary": scene_summary,
        }
        progression_hits = sum(
            [
                1 if record["new_information_count"] > 0 else 0,
                1 if record["decision_count"] > 0 else 0,
                1 if record["state_change_count"] > 0 else 0,
            ]
        )
        record["progression_hit_count"] = progression_hits
        record["stagnant"] = progression_hits <= 1
        record["rewrite_candidate"] = (not record["lock_passed"]) or progression_hits == 0
        record["focus_review_candidate"] = bool(artifact_drift_issues or reveal_risks or same_function_motif_repeats or lock_failed_checks)
        record["merge_candidate_with_previous"] = bool(
            previous_record
            and record["stagnant"]
            and previous_record.get("stagnant")
            and (
                record["scene_function"] == previous_record.get("scene_function")
                or record["scene_type"] == previous_record.get("scene_type")
            )
        )
        scene_records.append(record)
        previous_scene_summary = scene_summary
        previous_record = record

    merge_candidates = [
        {
            "scene_ids": [scene_records[index - 1]["scene_id"], scene_records[index]["scene_id"]],
            "reason": f"连续 {scene_records[index]['scene_function']} / {scene_records[index]['scene_type']} 弱推进场，建议评估是否合并。",
        }
        for index in range(1, len(scene_records))
        if scene_records[index]["merge_candidate_with_previous"]
    ]

    motif_entries = (
        tracker_bundle.get("chapter_motif_tracker", {}).get("active_motifs", [])
        if isinstance(tracker_bundle.get("chapter_motif_tracker"), dict)
        else []
    )
    motif_stats = [
        {
            "label": str(item.get("label") or "").strip(),
            "recent_usage_count": int(item.get("recent_usage_count") or 0),
            "recent_functions": normalize_string_list(item.get("recent_functions", [])),
            "last_function": str(item.get("last_function") or "").strip(),
            "function_novelty_score": float(item.get("function_novelty_score") or 0.0),
            "redundancy_risk": str(item.get("redundancy_risk") or "low").strip(),
            "only_if_new_function": bool(item.get("only_if_new_function", False)),
            "allow_next_scene": bool(item.get("allow_next_scene", True)),
        }
        for item in motif_entries
        if isinstance(item, dict) and str(item.get("label") or "").strip()
    ]
    high_risk_motifs = [item for item in motif_stats if item["redundancy_risk"] in {"medium", "high"}]

    report = {
        "chapter_id": chapter_id,
        "scene_count": len(scene_records),
        "story_state_present": bool(story_state),
        "scene_type_sequence": [record["scene_type"] for record in scene_records],
        "scene_function_sequence": [record["scene_function"] for record in scene_records],
        "scene_records": scene_records,
        "same_function_runs": collect_same_function_runs(scene_records),
        "motif_stats": motif_stats,
        "high_risk_motifs": high_risk_motifs,
        "stagnant_scenes": [record["scene_id"] for record in scene_records if record["stagnant"]],
        "rewrite_candidates": [record["scene_id"] for record in scene_records if record["rewrite_candidate"]],
        "focus_review_scenes": [record["scene_id"] for record in scene_records if record["focus_review_candidate"]],
        "artifact_drift_scenes": [record["scene_id"] for record in scene_records if record["artifact_drift_count"] > 0],
        "reveal_risk_scenes": [record["scene_id"] for record in scene_records if record["reveal_risk_count"] > 0],
        "merge_candidates": merge_candidates,
    }
    return report


def render_text_report(report: dict[str, Any]) -> str:
    lines = [f"Chapter {report['chapter_id']} scene 体检", f"- scene_count: {report['scene_count']}"]
    lines.append(f"- scene_type_sequence: {' -> '.join(report.get('scene_type_sequence', [])) or 'n/a'}")
    lines.append("")
    lines.append("每场诊断：")
    for record in report.get("scene_records", []):
        lines.append(
            f"- {record['scene_id']}: function={record['scene_function']} type={record['scene_type']} info={record['new_information_count']} decision={record['decision_count']} state={record['state_change_count']} motif_repeat={record['repeated_motif_count']} same_function_motif={record['same_function_motif_repeat_count']} lock={'pass' if record['lock_passed'] else 'fail'}"
        )
    if report.get("same_function_runs"):
        lines.append("")
        lines.append("同功能连续段：")
        for run in report["same_function_runs"]:
            lines.append(f"- {run['scene_function']} ({run['scene_type']}): {', '.join(run['scene_ids'])}")
    if report.get("high_risk_motifs"):
        lines.append("")
        lines.append("高风险 motif：")
        for motif in report["high_risk_motifs"]:
            lines.append(
                f"- {motif['label']}: usage={motif['recent_usage_count']} last_function={motif['last_function'] or 'n/a'} recent_functions={', '.join(motif['recent_functions']) or 'n/a'} risk={motif['redundancy_risk']}"
            )
    lines.append("")
    lines.append(f"建议重写: {', '.join(report.get('rewrite_candidates', [])) or '无'}")
    lines.append(f"重点复查: {', '.join(report.get('focus_review_scenes', [])) or '无'}")
    lines.append(f"artifact drift: {', '.join(report.get('artifact_drift_scenes', [])) or '无'}")
    lines.append(f"reveal 风险: {', '.join(report.get('reveal_risk_scenes', [])) or '无'}")
    if report.get("merge_candidates"):
        lines.append("建议合并：")
        for item in report["merge_candidates"]:
            lines.append(f"- {', '.join(item['scene_ids'])}: {item['reason']}")
    else:
        lines.append("建议合并: 无")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="离线分析一整章 locked scenes 的结构完成度与空转风险。")
    parser.add_argument("chapter_id", help="要分析的章节编号，例如 ch01")
    parser.add_argument("--root", default=str(ROOT), help="项目根目录，默认当前仓库根目录")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="输出格式")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    root = Path(args.root).resolve()
    report = analyze_chapter(root, args.chapter_id)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    print(render_text_report(report))


if __name__ == "__main__":
    main()