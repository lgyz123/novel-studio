import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import requests
import yaml
from chapter_trackers import (
    classify_scene_function,
    chapter_id_from_task_or_locked,
    detect_artifact_state_conflicts as detect_tracker_artifact_state_conflicts,
    detect_forbidden_reveal_violations,
    load_tracker_bundle,
    motif_entries_in_text,
)
from deepseek_reviewer import review_scene_with_deepseek, save_structured_deepseek_review, structured_review_to_legacy_result
from issue_filters import filter_shared_issues, is_mostly_english
from jsonschema import validate
from review_models import StructuredReviewResult, build_structured_review_result, save_repair_plan, save_structured_review_result


ROOT = Path(__file__).resolve().parent.parent


def should_use_deepseek(config: dict) -> bool:
    reviewer = config.get("reviewer", {})
    base_url = str(reviewer.get("base_url", "")).rstrip("/")
    model = str(reviewer.get("model", "")).strip()
    provider = str(reviewer.get("provider", "")).strip().lower()
    return provider == "deepseek" or (base_url == "https://api.deepseek.com" and model == "deepseek-chat")


def read_text(rel_path: str) -> str:
    path = ROOT / rel_path
    return path.read_text(encoding="utf-8")


def save_text(rel_path: str, content: str) -> None:
    path = ROOT / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_yaml(rel_path: str) -> dict:
    path = ROOT / rel_path
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def clip_text(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[已截断]"


def call_ollama(
    model: str,
    system_prompt: str,
    user_prompt: str,
    base_url: str,
    num_ctx: int,
    temperature: float,
    timeout: int,
    num_predict: int,
    response_format: Any = None,
) -> dict:
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {
            "num_ctx": num_ctx,
            "temperature": temperature,
            "num_predict": num_predict,
        },
    }
    if response_format is not None:
        payload["format"] = response_format

    print(f"正在请求 Reviewer 模型: {model} @ {base_url}")
    last_error: Exception | None = None
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as error:
            last_error = error
            status_code = error.response.status_code if error.response is not None else None
            if status_code is None or status_code < 500 or attempt >= max_attempts:
                raise
            print(f"Reviewer 请求失败（HTTP {status_code}），正在重试 {attempt}/{max_attempts}...")
            time.sleep(min(attempt, 3))
        except requests.exceptions.RequestException as error:
            last_error = error
            if attempt >= max_attempts:
                raise
            print(f"Reviewer 请求异常，正在重试 {attempt}/{max_attempts}...")
            time.sleep(min(attempt, 3))

    assert last_error is not None
    raise last_error


def summarize_response_for_debug(response_data: dict) -> str:
    message = response_data.get("message", {})
    summary = {
        "top_level_keys": sorted(response_data.keys()),
        "message_keys": sorted(message.keys()) if isinstance(message, dict) else [],
        "done": response_data.get("done"),
        "done_reason": response_data.get("done_reason"),
        "prompt_eval_count": response_data.get("prompt_eval_count"),
        "eval_count": response_data.get("eval_count"),
        "content_length": len(message.get("content", "")) if isinstance(message, dict) and isinstance(message.get("content"), str) else 0,
    }
    return json.dumps(summary, ensure_ascii=False, indent=2)


def extract_message_text(response_data: dict) -> str:
    message = response_data.get("message", {}) if isinstance(response_data, dict) else {}

    candidates = [
        message.get("content") if isinstance(message, dict) else None,
        message.get("reasoning") if isinstance(message, dict) else None,
        message.get("thinking") if isinstance(message, dict) else None,
        response_data.get("response") if isinstance(response_data, dict) else None,
        response_data.get("content") if isinstance(response_data, dict) else None,
        response_data.get("reasoning") if isinstance(response_data, dict) else None,
        response_data.get("thinking") if isinstance(response_data, dict) else None,
    ]

    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def normalize_text_key(text: str) -> str:
    lowered = str(text).strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    lowered = re.sub(r"[\W_]+", "", lowered)
    return lowered


def split_text_fragments(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", str(text).strip())
    return [part.strip() for part in re.split(r"(?<=[。！？.!?；;])\s+|[；;]\s*", normalized) if part.strip()]


def dedupe_repeated_fragments(text: str, max_unique_fragments: int = 8) -> tuple[str, int]:
    fragments = split_text_fragments(text)
    if not fragments:
        return str(text).strip(), 0

    kept: list[str] = []
    seen: set[str] = set()
    repeated_count = 0

    for fragment in fragments:
        key = normalize_text_key(fragment)
        if not key:
            continue
        if key in seen:
            repeated_count += 1
            continue
        seen.add(key)
        kept.append(fragment)
        if len(kept) >= max_unique_fragments:
            remaining = len(fragments) - len(kept)
            repeated_count += max(remaining, 0)
            break

    return " ".join(kept).strip(), repeated_count


def is_low_value_english_analysis(text: str) -> bool:
    stripped = str(text).strip()
    if not stripped or not is_mostly_english(stripped):
        return False

    lower_text = stripped.lower()
    marker_count = sum(
        1
        for marker in [
            "we need to",
            "the assistant must",
            "must output",
            "single json object",
            "the draft must",
            "we should output",
            "we need to evaluate",
            "we need to review",
            "status and message",
            "pass or fail",
        ]
        if marker in lower_text
    )
    compressed, repeated_count = dedupe_repeated_fragments(stripped)
    return marker_count >= 2 or repeated_count >= 3 or len(compressed) < len(stripped) * 0.55


def sanitize_reviewer_raw_output(raw_text: str, max_chars: int = 2200) -> tuple[str, dict[str, Any]]:
    stripped = str(raw_text).strip()
    if not stripped:
        return "", {"low_value_english": False, "repeated_fragments": 0, "truncated": False}

    compressed, repeated_count = dedupe_repeated_fragments(stripped)
    low_value_english = is_low_value_english_analysis(stripped)
    sanitized = compressed or stripped
    truncated = False

    if low_value_english and len(sanitized) > 1200:
        sanitized = sanitized[:1200].rstrip()
        truncated = True
    elif len(sanitized) > max_chars:
        sanitized = sanitized[:max_chars].rstrip()
        truncated = True

    if truncated:
        sanitized = sanitized + "\n\n[审稿原文已截断]"
    if repeated_count > 0:
        sanitized = sanitized + f"\n\n[重复片段已压缩 {repeated_count} 处]"

    return sanitized, {
        "low_value_english": low_value_english,
        "repeated_fragments": repeated_count,
        "truncated": truncated,
    }


def sanitize_issue_text(text: str) -> str:
    compacted, repeated_count = dedupe_repeated_fragments(str(text).strip(), max_unique_fragments=4)
    cleaned = compacted.strip()
    if repeated_count > 0 and cleaned:
        cleaned = f"{cleaned}（重复内容已压缩）"
    return cleaned[:180].strip()


def strip_scene_heading(text: str) -> str:
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^【scene\s*\d+】\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^scene\s*\d+[:：]\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


INFORMATION_GAIN_MARKERS = [
    "发现",
    "看见",
    "看到",
    "摸到",
    "捡到",
    "拾到",
    "认出",
    "确认",
    "注意到",
    "露出",
    "写着",
    "系着",
    "挂着",
    "藏着",
    "放着",
    "多了",
    "少了",
    "不见",
    "原来",
    "竟是",
    "不是",
    "留下",
]

DECISION_OR_SHIFT_MARKERS = [
    "决定",
    "藏起",
    "藏好",
    "记住",
    "记下",
    "转向",
    "询问",
    "隐瞒",
    "回去",
    "停止",
    "撒谎",
    "跟踪",
    "取走",
    "放弃",
    "索性",
    "改成",
    "改为",
    "先把",
    "没有立刻",
    "没立刻",
    "暂缓",
    "拖到",
    "拖延",
    "收起",
    "藏起",
    "塞进",
    "记下",
    "绕开",
    "避开",
    "不交",
    "压下",
    "停下",
    "回头",
    "重新",
    "推迟",
    "扣住",
    "挪开",
]

PLOT_PROGRESS_MARKERS = [
    "于是",
    "便",
    "随后",
    "接着",
    "结果",
    "差点",
    "终于",
    "开始",
    "改成",
    "改为",
    "导致",
    "让他",
    "没能",
    "只好",
]

WRONG_PROTAGONIST_NAMES = ["孟繁灯", "孟繁星", "孟浮星"]

INTROSPECTIVE_ONLY_MARKERS = [
    "想起",
    "记起",
    "觉得",
    "仿佛",
    "像是",
    "忽然想",
    "发怔",
    "出神",
    "恍惚",
    "喉头发紧",
    "心里一沉",
]

INVESTIGATION_MARKERS = [
    "追问",
    "打听",
    "调查",
    "追查",
    "跟踪",
    "查清",
    "问清",
    "盯梢",
    "探查",
]

def load_review_tracker_bundle(task_text: str | None, chapter_state: str = "") -> dict[str, Any]:
    if not str(task_text or "").strip():
        return {}
    try:
        chapter_id = chapter_id_from_task_or_locked(str(task_text or ""), "")
    except Exception:
        return {}
    story_state_path = ROOT / "03_locked/state/story_state.json"
    story_state: dict[str, Any] | None = None
    if story_state_path.exists():
        try:
            loaded = json.loads(story_state_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                story_state = loaded
        except Exception:
            story_state = None
    try:
        return load_tracker_bundle(ROOT, chapter_id, chapter_state_text=str(chapter_state or ""), story_state=story_state)
    except Exception:
        return {}


def build_empty_structural_review() -> dict[str, Any]:
    return {
        "information_gain": {
            "has_new_information": False,
            "new_information_items": [],
        },
        "plot_progress": {
            "has_plot_progress": False,
            "progress_reason": "未识别到明确的情节推进。",
        },
        "character_decision": {
            "has_decision_or_behavior_shift": False,
            "decision_detail": "主角尚未做出可追踪的决策或行为偏移。",
        },
        "motif_redundancy": {
            "repeated_motifs": [],
            "new_function_motifs": [],
            "stale_function_motifs": [],
            "repeated_same_function_motifs": [],
            "consecutive_same_function_motifs": [],
            "repetition_has_new_function": True,
            "same_function_reuse_allowed": True,
            "redundancy_reason": "未识别到明显的高频母题复读。",
        },
        "canon_consistency": {
            "is_consistent": True,
            "consistency_issues": [],
        },
    }


def ensure_non_empty_structural_fields(result: dict[str, Any]) -> dict[str, Any]:
    merged = dict(result)
    fallback = build_empty_structural_review()

    for field, defaults in fallback.items():
        candidate = merged.get(field) if isinstance(merged.get(field), dict) else {}
        payload = dict(defaults)
        payload.update(candidate)

        if field == "information_gain":
            payload["has_new_information"] = bool(payload.get("has_new_information", False))
            payload["new_information_items"] = [sanitize_issue_text(item) for item in payload.get("new_information_items", []) if str(item).strip()][:3]
        elif field == "plot_progress":
            payload["has_plot_progress"] = bool(payload.get("has_plot_progress", False))
            payload["progress_reason"] = sanitize_issue_text(payload.get("progress_reason") or defaults["progress_reason"]) or defaults["progress_reason"]
        elif field == "character_decision":
            payload["has_decision_or_behavior_shift"] = bool(payload.get("has_decision_or_behavior_shift", False))
            payload["decision_detail"] = sanitize_issue_text(payload.get("decision_detail") or defaults["decision_detail"]) or defaults["decision_detail"]
        elif field == "motif_redundancy":
            for key in ["repeated_motifs", "new_function_motifs", "stale_function_motifs", "repeated_same_function_motifs", "consecutive_same_function_motifs"]:
                payload[key] = [sanitize_issue_text(item) for item in payload.get(key, []) if str(item).strip()][:5]
            payload["repetition_has_new_function"] = bool(payload.get("repetition_has_new_function", True))
            payload["same_function_reuse_allowed"] = bool(payload.get("same_function_reuse_allowed", True))
            payload["redundancy_reason"] = sanitize_issue_text(payload.get("redundancy_reason") or defaults["redundancy_reason"]) or defaults["redundancy_reason"]
        elif field == "canon_consistency":
            payload["is_consistent"] = bool(payload.get("is_consistent", True))
            payload["consistency_issues"] = [sanitize_issue_text(item) for item in payload.get("consistency_issues", []) if str(item).strip()][:3]

        merged[field] = payload

    if not str(merged.get("summary") or "").strip():
        merged["summary"] = "本场审稿结果已由本地规则补齐。"
    return merged


def sentence_has_information_gain(sentence: str) -> bool:
    text = str(sentence).strip()
    if not text:
        return False
    if any(marker in text for marker in INFORMATION_GAIN_MARKERS):
        return True
    return bool(re.search(r"(位置|来处|来源|物件|尸体|袖口|袋口|腕上|背面).*(变|露|写|挂|放|藏|缺|多|少)", text))


def sentence_has_decision_or_shift(sentence: str) -> bool:
    text = str(sentence).strip()
    if not text:
        return False
    if any(marker in text for marker in DECISION_OR_SHIFT_MARKERS):
        return True
    return bool(re.search(r"(把|将).*(收起|塞进|压回|挪开|藏起|推迟|避开|绕开|记下|取走|放弃|隐瞒|询问|跟踪)", text))


def sentence_has_plot_progress(sentence: str) -> bool:
    text = str(sentence).strip()
    if not text:
        return False
    if any(marker in text for marker in PLOT_PROGRESS_MARKERS):
        return True
    return bool(re.search(r"(差点|结果|于是|随后|接着).*(翻倒|暴露|滑出|漏出|停下|改变|延后)", text))


def summarize_sentence(sentence: str, max_chars: int = 36) -> str:
    compact = re.sub(r"\s+", " ", str(sentence).strip())
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rstrip() + "…"


def count_term_occurrences(text: str, term: str) -> int:
    return str(text).count(term)


def reviewer_missing_structural_detail(reviewer_result: dict[str, Any], field: str, detail_key: str) -> bool:
    payload = reviewer_result.get(field, {}) if isinstance(reviewer_result, dict) else {}
    if not isinstance(payload, dict):
        return True
    detail = payload.get(detail_key)
    if isinstance(detail, list):
        return not any(str(item).strip() for item in detail)
    return not str(detail or "").strip()


def build_structural_review_signals(task_text: str | None, draft_text: str, based_on_text: str = "", chapter_state: str = "") -> dict[str, Any]:
    signals = build_empty_structural_review()
    draft_sentences = split_sentences(strip_scene_heading(draft_text))
    based_on_keys = {normalize_text_key(item) for item in split_sentences(strip_scene_heading(based_on_text))}
    tracker_bundle = load_review_tracker_bundle(task_text, chapter_state=chapter_state)
    chapter_motif_tracker = tracker_bundle.get("chapter_motif_tracker", {}) if isinstance(tracker_bundle, dict) else {}
    revelation_tracker = tracker_bundle.get("revelation_tracker", {}) if isinstance(tracker_bundle, dict) else {}
    artifact_state = tracker_bundle.get("artifact_state", {}) if isinstance(tracker_bundle, dict) else {}
    chapter_progress = tracker_bundle.get("chapter_progress", {}) if isinstance(tracker_bundle, dict) else {}

    new_information_items: list[str] = []
    decision_detail = ""
    progress_reason = ""

    for sentence in draft_sentences:
        key = normalize_text_key(sentence)
        if key and key not in based_on_keys and sentence_has_information_gain(sentence):
            new_information_items.append(summarize_sentence(sentence))
        if not decision_detail and sentence_has_decision_or_shift(sentence):
            decision_detail = summarize_sentence(sentence, max_chars=48)
        if not progress_reason and sentence_has_plot_progress(sentence):
            progress_reason = summarize_sentence(sentence, max_chars=48)

    deduped_information_items: list[str] = []
    for item in new_information_items:
        if item not in deduped_information_items:
            deduped_information_items.append(item)

    signals["information_gain"] = {
        "has_new_information": bool(deduped_information_items),
        "new_information_items": deduped_information_items[:3],
    }

    has_decision = bool(decision_detail)
    if not decision_detail:
        decision_detail = "主角主要停留在感受、回想或氛围反应，没有形成可追踪的行为偏移。"
    signals["character_decision"] = {
        "has_decision_or_behavior_shift": has_decision,
        "decision_detail": decision_detail,
    }

    has_plot_progress = bool(progress_reason) or has_decision
    scene_function = classify_scene_function(draft_text)
    chapter_state_shift_reasons: list[str] = []
    if any(marker in draft_text for marker in INVESTIGATION_MARKERS) and str(chapter_progress.get("investigation_stage") or "") != "主动调查":
        chapter_state_shift_reasons.append("调查阶段从未启动/留意推进到更明确的调查动作")
    if any(marker in draft_text for marker in ["差点", "险些", "暴露", "惹来", "更难", "盯上"]):
        chapter_state_shift_reasons.append("风险等级发生变化")
    if any(isinstance(item, dict) and str(item.get("label") or "") in draft_text for item in artifact_state.get("items", []) if isinstance(artifact_state, dict)) and any(marker in draft_text for marker in ["塞回", "藏在", "摸出来", "揣着", "露出", "挂着"]):
        chapter_state_shift_reasons.append("关键物件状态发生变化")
    if chapter_state_shift_reasons and not has_plot_progress:
        has_plot_progress = True
        progress_reason = "；".join(chapter_state_shift_reasons[:2])
    if not progress_reason:
        if has_plot_progress:
            progress_reason = "场景中存在可追踪的行为偏移，局面因此发生了轻微变化。"
        else:
            progress_reason = "全文主要在重复动作与感受，没有形成可追踪的局面变化、风险变化或认知推进。"
    signals["plot_progress"] = {
        "has_plot_progress": has_plot_progress,
        "progress_reason": progress_reason,
    }

    if not has_decision:
        introspective_only = all(any(marker in sentence for marker in INTROSPECTIVE_ONLY_MARKERS) or not sentence_has_decision_or_shift(sentence) for sentence in draft_sentences[: min(len(draft_sentences), 4)])
        if introspective_only:
            signals["character_decision"]["decision_detail"] = "全文主要停留在想起、发怔、感受发紧等内心反应，没有落成明确的动作结果或决策动词。"

    repeated_entries = motif_entries_in_text(draft_text, chapter_motif_tracker)
    repeated_motifs = []
    new_function_motifs: list[str] = []
    stale_function_motifs: list[str] = []
    repeated_same_function_motifs: list[str] = []
    consecutive_same_function_motifs: list[str] = []
    disallowed_same_function_motifs: list[str] = []
    for entry in repeated_entries:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or "").strip()
        if label and label not in repeated_motifs:
            repeated_motifs.append(label)
    motif_has_new_function = True
    same_function_reuse_allowed = True
    redundancy_reason = "未识别到明显的高频母题复读。"
    if repeated_motifs:
        dense_repetition = [
            motif
            for motif in repeated_motifs
            if count_term_occurrences(draft_text, motif) >= 2 and count_term_occurrences(based_on_text, motif) >= 1
        ]
        repeated_entry_map = {
            str(entry.get("label") or "").strip(): entry
            for entry in repeated_entries
            if isinstance(entry, dict) and str(entry.get("label") or "").strip()
        }
        for label in repeated_motifs:
            entry = repeated_entry_map.get(label, {})
            recent_functions = [str(item).strip() for item in entry.get("recent_functions", []) if str(item).strip()]
            if not recent_functions:
                recent_functions = [str(item).strip() for item in entry.get("narrative_functions", []) if str(item).strip()]
            last_function = str(entry.get("last_function") or (recent_functions[-1] if recent_functions else "")).strip()
            same_function_reuse = bool(scene_function and scene_function in recent_functions)
            consecutive_same_function = bool(scene_function and last_function and scene_function == last_function)
            sentences_for_label = [sentence for sentence in draft_sentences if label in sentence]
            local_function_gain = any(
                sentence_has_information_gain(sentence) or sentence_has_decision_or_shift(sentence) or sentence_has_plot_progress(sentence)
                for sentence in sentences_for_label
            )
            function_is_new = bool(scene_function and scene_function not in recent_functions)
            has_new_function = function_is_new or local_function_gain
            only_if_new_function = bool(entry.get("only_if_new_function"))
            allow_next_scene = bool(entry.get("allow_next_scene", True))

            if same_function_reuse and label not in repeated_same_function_motifs:
                repeated_same_function_motifs.append(label)
            if consecutive_same_function and label not in consecutive_same_function_motifs:
                consecutive_same_function_motifs.append(label)
            if has_new_function:
                if label not in new_function_motifs:
                    new_function_motifs.append(label)
            else:
                if label not in stale_function_motifs:
                    stale_function_motifs.append(label)

            if same_function_reuse and ((only_if_new_function and not has_new_function) or ((not allow_next_scene) and not has_new_function) or (consecutive_same_function and not has_new_function)):
                if label not in disallowed_same_function_motifs:
                    disallowed_same_function_motifs.append(label)

        motif_has_new_function = not stale_function_motifs
        same_function_reuse_allowed = not disallowed_same_function_motifs
        if consecutive_same_function_motifs and stale_function_motifs:
            redundancy_reason = f"母题 {', '.join(consecutive_same_function_motifs[:4])} 在相邻场景连续承担同一功能，且本场没有提供新的功能增量。"
        elif disallowed_same_function_motifs:
            redundancy_reason = f"母题 {', '.join(disallowed_same_function_motifs[:4])} 延续了受限的同功能复用，本场应改为新功能承担。"
        elif dense_repetition and not motif_has_new_function:
            redundancy_reason = f"高频母题 {', '.join(dense_repetition[:4])} 在相邻场景连续复现，但没有承担新的信息、动作或推进功能。"
        elif motif_has_new_function:
            redundancy_reason = f"复现母题 {', '.join(repeated_motifs[:4])}，且本场至少为 {', '.join(new_function_motifs[:3]) or '其中一项'} 提供了新的叙事功能。"
        else:
            redundancy_reason = f"复现母题 {', '.join(repeated_motifs[:4])}，但没有带来新信息、动作决策或认知反转。"
    signals["motif_redundancy"] = {
        "repeated_motifs": repeated_motifs[:5],
        "new_function_motifs": new_function_motifs[:5],
        "stale_function_motifs": stale_function_motifs[:5],
        "repeated_same_function_motifs": repeated_same_function_motifs[:5],
        "consecutive_same_function_motifs": consecutive_same_function_motifs[:5],
        "repetition_has_new_function": motif_has_new_function,
        "same_function_reuse_allowed": same_function_reuse_allowed,
        "redundancy_reason": redundancy_reason,
    }

    consistency_issues: list[str] = []
    for wrong_name in WRONG_PROTAGONIST_NAMES:
        if wrong_name in draft_text:
            consistency_issues.append(f"主角姓名漂移为“{wrong_name}”，与既有 canon 不一致。")
    consistency_issues.extend(detect_forbidden_reveal_violations(draft_text, revelation_tracker))
    if chapter_state and ("尚未形成调查念头" in chapter_state or "不该主动追问" in chapter_state):
        for marker in INVESTIGATION_MARKERS:
            if marker in draft_text:
                consistency_issues.append(f"chapter_state 明确禁止主动调查，但正文出现了“{marker}”式调查推进。")
                break
    consistency_issues.extend(detect_tracker_artifact_state_conflicts(draft_text, artifact_state))
    signals["canon_consistency"] = {
        "is_consistent": not consistency_issues,
        "consistency_issues": consistency_issues[:3],
    }

    return signals


def structural_gate_failures(signals: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    information_gain = signals.get("information_gain", {})
    plot_progress = signals.get("plot_progress", {})
    character_decision = signals.get("character_decision", {})
    motif_redundancy = signals.get("motif_redundancy", {})
    canon_consistency = signals.get("canon_consistency", {})

    if not information_gain.get("has_new_information"):
        failures.append("missing_information_gain")
    if not plot_progress.get("has_plot_progress"):
        failures.append("missing_plot_progress")
    if not character_decision.get("has_decision_or_behavior_shift"):
        failures.append("missing_character_decision")
    if motif_redundancy.get("repeated_motifs") and not motif_redundancy.get("repetition_has_new_function"):
        failures.append("motif_redundancy_without_new_function")
    if motif_redundancy.get("repeated_same_function_motifs") and not motif_redundancy.get("same_function_reuse_allowed", True):
        failures.append("motif_same_function_reuse_not_allowed")
    if not canon_consistency.get("is_consistent") and canon_consistency.get("consistency_issues"):
        failures.append("canon_inconsistency")
    return failures


def build_structural_issue_summary(signals: dict[str, Any]) -> tuple[list[str], list[str], str]:
    major_issues: list[str] = []
    minor_issues: list[str] = []

    information_gain = signals.get("information_gain", {})
    plot_progress = signals.get("plot_progress", {})
    character_decision = signals.get("character_decision", {})
    motif_redundancy = signals.get("motif_redundancy", {})
    canon_consistency = signals.get("canon_consistency", {})

    if not information_gain.get("has_new_information"):
        major_issues.append("本场缺少可验证的新信息增量，新增内容主要停留在氛围、疲惫或既有意象复现。")
    elif information_gain.get("new_information_items"):
        minor_issues.append(f"本场新增信息：{'；'.join(information_gain['new_information_items'][:2])}")

    if not plot_progress.get("has_plot_progress"):
        major_issues.append("本场没有形成可追踪的情节推进，局面、风险、关系或认知没有发生明确变化。")

    if not character_decision.get("has_decision_or_behavior_shift"):
        major_issues.append("主角没有做出可追踪的决策或行为偏移，只有感受变化，不足以支撑 scene 推进。")

    repeated_motifs = motif_redundancy.get("repeated_motifs") or []
    if repeated_motifs and not motif_redundancy.get("repetition_has_new_function"):
        major_issues.append(f"高频母题复读但未承担新功能：{', '.join(repeated_motifs[:4])}。")
    if motif_redundancy.get("repeated_same_function_motifs") and not motif_redundancy.get("same_function_reuse_allowed", True):
        major_issues.append(f"母题同功能连续复用已超限：{', '.join((motif_redundancy.get('repeated_same_function_motifs') or [])[:4])}。")

    for issue in (canon_consistency.get("consistency_issues") or [])[:2]:
        major_issues.append(f"canon 一致性风险：{issue}")

    if major_issues:
        summary = major_issues[0]
    else:
        summary = "本场具备信息增量、情节推进、行为偏移，且未发现明显母题空转或 canon 漂移。"

    return major_issues[:5], minor_issues[:3], summary


def evaluate_scene_gate(
    task_text: str | None,
    draft_text: str,
    based_on_text: str = "",
    chapter_state: str = "",
    reviewer_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    signals = build_structural_review_signals(task_text, draft_text, based_on_text=based_on_text, chapter_state=chapter_state)
    failures = structural_gate_failures(signals)
    major_issues, minor_issues, summary = build_structural_issue_summary(signals)
    reviewer_result = reviewer_result or {}
    guardrail_failures: list[str] = []

    if reviewer_missing_structural_detail(reviewer_result, "information_gain", "new_information_items"):
        if not signals["information_gain"].get("has_new_information"):
            major_issues.insert(0, "Reviewer 未列出 `new_information_items`，且本地规则也未识别出新信息，本场属于高风险空转。")
            guardrail_failures.append("reviewer_missing_information_items")
        else:
            minor_issues.insert(0, "Reviewer 未列出 `new_information_items`，已由本地规则补做信息增量判定。")

    if reviewer_missing_structural_detail(reviewer_result, "character_decision", "decision_detail") and not signals["character_decision"].get("has_decision_or_behavior_shift"):
        major_issues.append("Reviewer 没有给出可核对的 `decision_detail`，本地规则也未识别到明确决策动词或动作结果。")
        guardrail_failures.append("reviewer_missing_decision_detail")

    reviewer_motif = reviewer_result.get("motif_redundancy", {}) if isinstance(reviewer_result, dict) else {}
    if signals["motif_redundancy"].get("repeated_motifs") and not signals["motif_redundancy"].get("repetition_has_new_function"):
        if reviewer_motif.get("repetition_has_new_function"):
            major_issues.append("Reviewer 认为母题复现有新功能，但本地规则判定仍是复读场，需按高风险处理。")
            guardrail_failures.append("motif_redundancy_overridden_locally")
    if signals["motif_redundancy"].get("repeated_same_function_motifs") and not signals["motif_redundancy"].get("same_function_reuse_allowed", True):
        if reviewer_motif.get("same_function_reuse_allowed", True):
            major_issues.append("Reviewer 放过了母题同功能连续复用，但本地规则判定该复用已超预算，需按结构风险处理。")
            guardrail_failures.append("motif_same_function_reuse_overridden_locally")

    reviewer_canon = reviewer_result.get("canon_consistency", {}) if isinstance(reviewer_result, dict) else {}
    if reviewer_canon.get("is_consistent") and not signals["canon_consistency"].get("is_consistent"):
        major_issues.append("Reviewer 未拦下明显 canon 冲突，本地规则已自动标红处理。")
        guardrail_failures.append("canon_conflict_overridden_locally")

    deduped_major: list[str] = []
    for item in major_issues:
        text = sanitize_issue_text(item)
        if text and text not in deduped_major:
            deduped_major.append(text)

    deduped_minor: list[str] = []
    for item in minor_issues:
        text = sanitize_issue_text(item)
        if text and text not in deduped_minor:
            deduped_minor.append(text)

    return {
        "signals": signals,
        "failures": failures,
        "guardrail_failures": guardrail_failures,
        "major_issues": deduped_major[:6],
        "minor_issues": deduped_minor[:4],
        "summary": summary,
    }


def apply_structural_guardrails(
    result: dict[str, Any],
    structural_payload: dict[str, Any],
    guardrail_report: dict[str, Any],
    major_issues: list[str],
    minor_issues: list[str],
    summary: str,
) -> tuple[dict[str, Any], list[str], list[str], str, list[str]]:
    updated = dict(result)
    merged_major = list(major_issues)
    merged_minor = list(minor_issues)

    for item in reversed(guardrail_report.get("minor_issues", [])):
        if item not in merged_minor:
            merged_minor.insert(0, item)
    for item in reversed(guardrail_report.get("major_issues", [])):
        if item not in merged_major:
            merged_major.insert(0, item)

    all_failures = []
    for item in list(guardrail_report.get("failures", [])) + list(guardrail_report.get("guardrail_failures", [])):
        if item not in all_failures:
            all_failures.append(item)

    if all_failures:
        summary = str(guardrail_report.get("summary") or summary).strip() or summary
        updated["task_goal_fulfilled"] = False
        severe_failure = "canon_inconsistency" in all_failures or "canon_conflict_overridden_locally" in all_failures or {
            "missing_information_gain",
            "missing_plot_progress",
            "missing_character_decision",
        }.issubset(set(all_failures))
        updated["verdict"] = "rewrite" if severe_failure else "revise"
        updated["recommended_next_step"] = "rewrite_scene" if updated["verdict"] == "rewrite" else "create_revision_task"

    for field, value in structural_payload.items():
        updated[field] = value

    return updated, merged_major[:6], merged_minor[:4], summary, all_failures


def extract_json_object(raw_text: str) -> dict:
    text = raw_text.strip()
    if not text:
        raise ValueError("Reviewer 模型返回空内容")

    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].startswith("```"):
            text = "\n".join(lines[1:-1]).strip()
            if text.lower().startswith("json"):
                text = text[4:].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("Reviewer 没有输出可提取的 JSON")

    return json.loads(match.group(0))


def validate_review_content(result: dict) -> None:
    summary = str(result.get("summary", "")).strip()
    major_issues = [item for item in result.get("major_issues", []) if str(item).strip()]
    minor_issues = [item for item in result.get("minor_issues", []) if str(item).strip()]

    if not summary:
        raise ValueError("Reviewer 输出缺少有效 summary")

    if result.get("verdict") in {"revise", "rewrite"} and not (major_issues or minor_issues):
        raise ValueError("Reviewer 给出了 revise/rewrite，但没有任何具体修改意见")

    if result.get("task_goal_fulfilled") is False and not (major_issues or minor_issues):
        raise ValueError("Reviewer 判定任务未完成，但没有给出具体问题")

    for field in ["information_gain", "plot_progress", "character_decision", "motif_redundancy", "canon_consistency"]:
        if not isinstance(result.get(field), dict):
            raise ValueError(f"Reviewer 输出缺少结构检查字段：{field}")


def build_chinese_issue_fallback(
    verdict: str,
    raw_review_text: str,
    task_text: str | None = None,
    draft_text: str = "",
    based_on_text: str = "",
    chapter_state: str = "",
) -> tuple[list[str], list[str], str, dict[str, Any]]:
    lower_text = raw_review_text.lower()
    structural_signals = build_structural_review_signals(task_text, draft_text, based_on_text=based_on_text, chapter_state=chapter_state)
    major_issues, minor_issues, structural_summary = build_structural_issue_summary(structural_signals)

    if verdict == "lock":
        if structural_gate_failures(structural_signals):
            verdict = "revise"
        else:
            return [], [], "当前 scene 已满足任务目标与约束条件，且通过结构硬检查，可直接锁定。", structural_signals

    if "too short" in lower_text or "500-900" in raw_review_text or "200-250" in lower_text:
        major_issues.append("篇幅与动作承载量偏弱，导致本场的完成度不足。")

    if "missing the hesitation" in lower_text or "influences action" in lower_text:
        major_issues.append("“阿绣”之名被想起后，对现实动作的轻微牵引还不够明确。")

    if "lingering" in lower_text or "fatigue" in lower_text or "low intensity" in lower_text:
        minor_issues.append("疲惫后的动作偏移与停顿感还能再落得更实一些。")

    if "closure" in lower_text or "not enough" in lower_text:
        minor_issues.append("场景尾部的收束略弱，闭环感还可以再加强。")

    if verdict == "rewrite":
        if not major_issues:
            major_issues.append("当前 scene 在方向或约束执行上存在明显偏差，需要整体重写。")
        summary = structural_summary or "当前 scene 存在方向性问题，建议整体重写后再进入审稿。"
    else:
        if not major_issues:
            major_issues.append("方向基本正确，但本场结构推进信号仍不足。")
        summary = structural_summary or "当前 scene 方向正确，但动作牵引与场景闭环仍不够完整，更适合先小修。"

    return major_issues[:5], minor_issues[:3], summary, structural_signals


def normalize_review_result(
    result: dict,
    raw_review_text: str,
    task_text: str | None = None,
    low_confidence: bool = False,
    draft_text: str = "",
    based_on_text: str = "",
    chapter_state: str = "",
) -> dict:
    allowed_keys = {
        "task_id",
        "verdict",
        "task_goal_fulfilled",
        "major_issues",
        "minor_issues",
        "recommended_next_step",
        "summary",
        "information_gain",
        "plot_progress",
        "character_decision",
        "motif_redundancy",
        "canon_consistency",
    }

    def infer_recommended_next_step(current_verdict: str) -> str:
        if current_verdict == "lock":
            return "lock_scene"
        if current_verdict == "rewrite":
            return "rewrite_scene"
        return "create_revision_task"

    def raw_review_has_strong_negative_signal(text: str) -> bool:
        lower_text = text.lower()
        negative_markers = [
            "reject",
            "not acceptable",
            "does not meet",
            "doesn't meet",
            "fails the task",
            "fails to meet",
            "too short",
            "not in the required setting",
            "not in the dock",
            "missing the core goal",
            "core line is missing",
            "is too short",
            "should reject",
        ]
        return any(marker in lower_text for marker in negative_markers)

    def is_bad_issue(text: str) -> bool:
        text = text.strip()

        bad_exact_or_prefix = [
            "The task:",
            "Must not",
            "We need to check",
            "But maybe",
            "So maybe",
            "No new characters.",
            "No new characters",
            "不引入新人物。",
            "不新增制度性设定。",
            "保持单视角。",
        ]
        if any(text.startswith(prefix) for prefix in bad_exact_or_prefix):
            return True

        if re.search(r"[A-Za-z]{3,}", text):
            return True

        if task_text:
            short_lines = [
                line.strip("- ").strip()
                for line in task_text.splitlines()
                if line.strip()
            ]
            for line in short_lines:
                if len(line) >= 4 and text == line:
                    return True

        return False

    def clean_list(items: list[str]) -> list[str]:
        cleaned = []
        seen: set[str] = set()

        for item in items:
            text = sanitize_issue_text(item)
            if not text:
                continue
            if is_bad_issue(text):
                continue
            key = normalize_text_key(text)
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(text)

        return cleaned

    verdict = result.get("verdict", "revise")
    cleaned_major = clean_list(filter_shared_issues(result.get("major_issues", []), task_text=task_text, limit=3))
    cleaned_minor = clean_list(filter_shared_issues(result.get("minor_issues", []), task_text=task_text, limit=3))
    summary = str(result.get("summary", "")).strip()
    guardrail_report = evaluate_scene_gate(
        task_text,
        draft_text,
        based_on_text=based_on_text,
        chapter_state=chapter_state,
        reviewer_result=result,
    )
    local_structural = guardrail_report["signals"]

    def merge_structural_payload() -> dict[str, Any]:
        merged = build_empty_structural_review()
        for field, local_value in local_structural.items():
            candidate = result.get(field) if isinstance(result.get(field), dict) else {}
            merged[field] = dict(local_value)
            if field == "information_gain":
                reviewer_items = [sanitize_issue_text(item) for item in candidate.get("new_information_items", []) if str(item).strip()]
                merged[field]["has_new_information"] = bool(candidate.get("has_new_information", local_value["has_new_information"])) and bool(local_value["has_new_information"])
                merged[field]["new_information_items"] = (reviewer_items or local_value["new_information_items"])[:3]
            elif field == "plot_progress":
                merged[field]["has_plot_progress"] = bool(candidate.get("has_plot_progress", local_value["has_plot_progress"])) and bool(local_value["has_plot_progress"])
                merged[field]["progress_reason"] = sanitize_issue_text(candidate.get("progress_reason") or local_value["progress_reason"]) or local_value["progress_reason"]
            elif field == "character_decision":
                merged[field]["has_decision_or_behavior_shift"] = bool(candidate.get("has_decision_or_behavior_shift", local_value["has_decision_or_behavior_shift"])) and bool(local_value["has_decision_or_behavior_shift"])
                merged[field]["decision_detail"] = sanitize_issue_text(candidate.get("decision_detail") or local_value["decision_detail"]) or local_value["decision_detail"]
            elif field == "motif_redundancy":
                reviewer_motifs = [sanitize_issue_text(item) for item in candidate.get("repeated_motifs", []) if str(item).strip()]
                merged[field]["repeated_motifs"] = (reviewer_motifs or local_value["repeated_motifs"])[:5]
                merged[field]["new_function_motifs"] = [sanitize_issue_text(item) for item in candidate.get("new_function_motifs", local_value["new_function_motifs"]) if str(item).strip()][:5]
                merged[field]["stale_function_motifs"] = [sanitize_issue_text(item) for item in candidate.get("stale_function_motifs", local_value["stale_function_motifs"]) if str(item).strip()][:5]
                merged[field]["repeated_same_function_motifs"] = [sanitize_issue_text(item) for item in candidate.get("repeated_same_function_motifs", local_value["repeated_same_function_motifs"]) if str(item).strip()][:5]
                merged[field]["consecutive_same_function_motifs"] = [sanitize_issue_text(item) for item in candidate.get("consecutive_same_function_motifs", local_value["consecutive_same_function_motifs"]) if str(item).strip()][:5]
                merged[field]["repetition_has_new_function"] = bool(candidate.get("repetition_has_new_function", local_value["repetition_has_new_function"])) and bool(local_value["repetition_has_new_function"])
                merged[field]["same_function_reuse_allowed"] = bool(candidate.get("same_function_reuse_allowed", local_value["same_function_reuse_allowed"])) and bool(local_value["same_function_reuse_allowed"])
                merged[field]["redundancy_reason"] = sanitize_issue_text(candidate.get("redundancy_reason") or local_value["redundancy_reason"]) or local_value["redundancy_reason"]
            elif field == "canon_consistency":
                reviewer_issues = [sanitize_issue_text(item) for item in candidate.get("consistency_issues", []) if str(item).strip()]
                merged[field]["is_consistent"] = bool(candidate.get("is_consistent", local_value["is_consistent"])) and bool(local_value["is_consistent"])
                merged[field]["consistency_issues"] = (reviewer_issues or local_value["consistency_issues"])[:3]
        return merged

    structural_payload = merge_structural_payload()
    structural_major, structural_minor, structural_summary = build_structural_issue_summary(structural_payload)
    hard_failures = structural_gate_failures(structural_payload)

    if verdict == "lock" and raw_review_has_strong_negative_signal(raw_review_text):
        verdict = "revise"
        result["verdict"] = "revise"
        result["recommended_next_step"] = "create_revision_task"
        if not cleaned_major:
            cleaned_major = ["原始审稿明确指出当前草稿未满足核心任务或关键约束，不应直接锁定。"]

    if verdict == "rewrite" and not cleaned_major:
        verdict = "revise"
        result["verdict"] = "revise"
        result["recommended_next_step"] = "create_revision_task"

    if low_confidence and verdict == "rewrite":
        verdict = "revise"
        result["verdict"] = "revise"
        result["recommended_next_step"] = "create_revision_task"

    if low_confidence:
        low_confidence_note = "Reviewer 原始输出主要是无效英文分析，已降权处理。"
        if low_confidence_note not in cleaned_minor:
            cleaned_minor = [low_confidence_note] + cleaned_minor

    if is_mostly_english(summary) or not summary:
        _, _, fallback_summary, _ = build_chinese_issue_fallback(
            verdict,
            raw_review_text,
            task_text=task_text,
            draft_text=draft_text,
            based_on_text=based_on_text,
            chapter_state=chapter_state,
        )
        summary = fallback_summary

    if verdict in {"revise", "rewrite"} and not (cleaned_major or cleaned_minor):
        cleaned_major, cleaned_minor, fallback_summary, _ = build_chinese_issue_fallback(
            verdict,
            raw_review_text,
            task_text=task_text,
            draft_text=draft_text,
            based_on_text=based_on_text,
            chapter_state=chapter_state,
        )
        summary = fallback_summary

    for item in reversed(structural_minor):
        if item not in cleaned_minor:
            cleaned_minor.insert(0, item)
    for item in reversed(structural_major):
        if item not in cleaned_major:
            cleaned_major.insert(0, item)

    skill_major, skill_minor = audit_scene_writing_skill_router(ROOT, task_text)
    for item in reversed(skill_minor):
        if item not in cleaned_minor:
            cleaned_minor.insert(0, item)
    for item in reversed(skill_major):
        if item not in cleaned_major:
            cleaned_major.insert(0, item)

    if not cleaned_major and verdict in {"revise", "rewrite"}:
        cleaned_major = ["当前草稿未充分完成 task 的核心推进目标。"]

    result, cleaned_major, cleaned_minor, summary, guardrail_failures = apply_structural_guardrails(
        result,
        structural_payload,
        guardrail_report,
        cleaned_major,
        cleaned_minor,
        structural_summary if hard_failures else summary,
    )
    hard_failures = list(dict.fromkeys(hard_failures + guardrail_failures))
    verdict = str(result.get("verdict") or verdict)

    rewrite_hard_markers = [
        "角色越界",
        "设定越界",
        "节奏失控",
        "文体错误",
        "方向错误",
        "场景功能错位",
    ]
    major_text = " ".join(cleaned_major)
    if verdict == "rewrite":
        if not any(marker in major_text for marker in rewrite_hard_markers):
            verdict = "revise"
            result["verdict"] = "revise"
            result["recommended_next_step"] = "create_revision_task"

    positive_summary_markers = ["方向正确", "基本满足", "可作为终稿"]
    negative_summary_markers = ["未完成", "不足", "需要小修", "仍需", "还需", "不够", "偏弱"]
    heavy_minor_markers = ["核心推进", "未完成", "不足", "偏弱", "不够", "需要补", "需要加强"]
    minor_is_light = len(cleaned_minor) <= 2 and not any(
        any(marker in item for marker in heavy_minor_markers) for item in cleaned_minor
    )
    if (
        verdict == "revise"
        and len(cleaned_major) == 1
        and not hard_failures
        and any(marker in summary for marker in positive_summary_markers)
        and not any(marker in summary for marker in negative_summary_markers)
        and minor_is_light
    ):
        cleaned_minor = cleaned_major + cleaned_minor
        cleaned_major = []
        verdict = "lock"
        result["verdict"] = "lock"
        result["recommended_next_step"] = "lock_scene"

    if verdict != "lock":
        result["task_goal_fulfilled"] = False
    else:
        result["task_goal_fulfilled"] = True

    result["major_issues"] = cleaned_major
    result["minor_issues"] = cleaned_minor
    result["summary"] = summary
    result["verdict"] = verdict
    result["recommended_next_step"] = str(result.get("recommended_next_step") or infer_recommended_next_step(verdict)).strip()
    for field, value in structural_payload.items():
        result[field] = value
    result = ensure_non_empty_structural_fields(result)
    return {key: result.get(key) for key in allowed_keys}


def split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[。！？.!?])\s+", normalized)
    return [part.strip() for part in parts if part.strip()]


def infer_verdict_from_text(text: str) -> str:
    lower_text = text.lower()

    rewrite_markers = [
        "rewrite",
        "must rewrite",
        "should rewrite",
        "direction is wrong",
        "functionally fails",
        "violates constraints badly",
    ]
    strong_revise_markers = [
        "revise",
        "needs revision",
        "not enough",
        "too short",
        "too long",
        "should tighten",
        "should trim",
        "needs more work",
        "does not satisfy",
        "fails to",
    ]
    lock_markers = [
        "can be locked",
        "can lock",
        "can be lock",
        "satisfy constraints",
        "satisfies all constraints",
        "seems to satisfy constraints",
        "satisfy all constraints",
        "no major issues",
        "no minor issues",
        "suitable to lock",
        "lock_scene",
        "can be directly locked",
    ]

    if any(marker in lower_text for marker in rewrite_markers):
        return "rewrite"
    if any(marker in lower_text for marker in lock_markers):
        return "lock"
    if any(marker in lower_text for marker in strong_revise_markers):
        return "revise"

    return "revise"


def extract_issue_candidates(text: str) -> tuple[list[str], list[str]]:
    sentences = split_sentences(text)
    major_keywords = (
        "major issue",
        "violat",
        "wrong",
        "fails",
        "not satisfy",
        "out of bounds",
        "too much",
        "investigation",
        "new characters",
        "new institutions",
    )
    minor_keywords = (
        "minor issue",
        "too short",
        "too long",
        "slightly",
        "could",
        "maybe",
        "approximate",
        "length",
        "check",
    )

    major_issues: list[str] = []
    minor_issues: list[str] = []

    for sentence in sentences:
        lower_sentence = sentence.lower()
        if any(keyword in lower_sentence for keyword in major_keywords):
            major_issues.append(sentence)
        elif any(keyword in lower_sentence for keyword in minor_keywords):
            minor_issues.append(sentence)

    return major_issues[:3], minor_issues[:3]


def build_local_review_fallback(
    task_id: str,
    raw_review_text: str,
    task_text: str | None = None,
    draft_text: str = "",
    based_on_text: str = "",
    chapter_state: str = "",
    low_confidence: bool = False,
) -> dict:
    verdict = infer_verdict_from_text(raw_review_text)
    extracted_major, extracted_minor = extract_issue_candidates(raw_review_text)
    structural_signals = build_structural_review_signals(task_text, draft_text, based_on_text=based_on_text, chapter_state=chapter_state)
    structural_major, structural_minor, structural_summary = build_structural_issue_summary(structural_signals)
    major_issues = structural_major + extracted_major
    minor_issues = structural_minor + extracted_minor
    failures = structural_gate_failures(structural_signals)

    if low_confidence:
        verdict = "revise"
        low_confidence_note = "Reviewer 原始输出主要是无效英文分析，已降权处理并转为保守小修。"
        if low_confidence_note not in minor_issues:
            minor_issues = [low_confidence_note] + minor_issues

    if failures and verdict == "lock":
        verdict = "rewrite" if "canon_inconsistency" in failures else "revise"

    if verdict == "lock":
        summary = "审稿分析认为当前 scene 基本满足任务约束、人物边界与低烈度推进要求，可直接锁定。"
        task_goal_fulfilled = True
        recommended_next_step = "lock_scene"
        major_issues = []
        minor_issues = []
    elif verdict == "rewrite":
        summary = structural_summary or "审稿分析认为当前 scene 存在方向性或约束性问题，建议整体重写。"
        task_goal_fulfilled = False
        recommended_next_step = "rewrite_scene"
        if not major_issues:
            major_issues = ["当前审稿分析指向重写，但原始输出未提供足够结构化的问题列表，需人工补充复核。"]
    else:
        summary = structural_summary or "审稿分析认为当前 scene 方向基本正确，但仍有若干问题需要小修。"
        task_goal_fulfilled = False
        recommended_next_step = "create_revision_task"
        if not (major_issues or minor_issues):
            minor_issues = ["原始审稿输出未按 JSON 返回，需人工根据审稿分析补充细化修改点。"]

    return {
        "task_id": task_id,
        "verdict": verdict,
        "task_goal_fulfilled": task_goal_fulfilled,
        "major_issues": major_issues[:5],
        "minor_issues": minor_issues[:3],
        "recommended_next_step": recommended_next_step,
        "summary": summary,
        "information_gain": structural_signals["information_gain"],
        "plot_progress": structural_signals["plot_progress"],
        "character_decision": structural_signals["character_decision"],
        "motif_redundancy": structural_signals["motif_redundancy"],
        "canon_consistency": structural_signals["canon_consistency"],
    }


def audit_scene_writing_skill_router(root: Path, task_text: str) -> tuple[list[str], list[str]]:
    output_target = extract_markdown_field(task_text, "output_target") or ""
    if output_target and not output_target.startswith("02_working/drafts/"):
        return [], []

    router_path = root / "02_working/planning/scene_writing_skill_router.json"
    if not router_path.exists():
        return [], []

    try:
        data = json.loads(router_path.read_text(encoding="utf-8"))
    except Exception:
        return ["scene writing skill router 结果文件损坏或不可解析，当前 skill 选择不可回放。"], []

    selected = data.get("selected_skills", []) if isinstance(data, dict) else []
    if not isinstance(selected, list):
        selected = []

    selected_names = [
        str(item.get("skill") or "").strip()
        for item in selected
        if isinstance(item, dict) and str(item.get("skill") or "").strip()
    ]

    major_issues: list[str] = []
    minor_issues: list[str] = []

    chapter_state_path = extract_markdown_field(task_text, "chapter_state") or ""
    if chapter_state_path and "continuity-guard" not in selected_names:
        major_issues.append("scene writing skill router 漏选 `continuity-guard`，但当前任务依赖 chapter_state 承接，存在明显连续性风险。")

    if len(selected_names) > 3:
        major_issues.append(f"scene writing skill router 选择了 {len(selected_names)} 个 skill，已超过当前约定上限 3 个，存在上下文过载风险。")

    if not major_issues and selected_names:
        minor_issues.append(f"本轮 scene writing skill router 已启用：{'、'.join(selected_names)}。")

    return major_issues, minor_issues


def extract_markdown_field(task_text: str, field_name: str) -> str | None:
    import re

    pattern = rf"(?ms)^#\s*{field_name}\s*\n(.*?)(?=^\s*#\s|\Z)"
    match = re.search(pattern, task_text)
    if not match:
        return None
    value = match.group(1).strip()
    return value if value else None


def build_review_prompt(
    task_text: str,
    chapter_state: str,
    based_on_text: str,
    draft_text: str,
) -> str:
    normalized_based_on = strip_scene_heading(based_on_text)
    normalized_draft = strip_scene_heading(draft_text)
    tracker_bundle = load_review_tracker_bundle(task_text, chapter_state=chapter_state)
    prompt_tracker_summary = {}
    if tracker_bundle:
        prompt_tracker_summary = {
            "chapter_motif_tracker": {
                "active_motifs": [
                    {
                        "label": item.get("label"),
                        "category": item.get("category"),
                        "recent_usage_count": item.get("recent_usage_count"),
                        "recent_functions": item.get("recent_functions"),
                        "last_function": item.get("last_function"),
                        "function_novelty_score": item.get("function_novelty_score"),
                        "allow_next_scene": item.get("allow_next_scene"),
                        "only_if_new_function": item.get("only_if_new_function"),
                        "redundancy_risk": item.get("redundancy_risk"),
                    }
                    for item in (tracker_bundle.get("chapter_motif_tracker", {}) or {}).get("active_motifs", [])[:8]
                    if isinstance(item, dict)
                ]
            },
            "revelation_tracker": tracker_bundle.get("revelation_tracker", {}),
            "artifact_state": tracker_bundle.get("artifact_state", {}),
            "chapter_progress": tracker_bundle.get("chapter_progress", {}),
        }
    tracker_summary_text = json.dumps(prompt_tracker_summary, ensure_ascii=False, indent=2) if prompt_tracker_summary else "{}"
    return f"""请审查下面这段 scene 草稿。

你只能输出一个合法 JSON 对象。
禁止先输出分析过程、英文说明、推理草稿或自然语言结论。
如果判断可以锁定，也必须把理由写进 summary 字段。
你审查的对象只有“待审草稿”一节；“直接前文 / 基准文本”只用于核对承接关系，绝不是本次草稿本身。
不要把“直接前文 / 基准文本”误判为待审草稿，不要因为它属于上一场 scene 就说当前稿件还是上一场。
你不是文风评论员，而是结构质量闸门。禁止只给“氛围到位、画面感强、文风统一、scene purpose 不够”这类泛评。
你必须逐项回答以下五类硬检查：
- information_gain：本场是否新增了至少一条可验证的新信息；若有，必须列出 `new_information_items`。
- plot_progress：本场是否推动了情节或让局面发生变化；`progress_reason` 必须说明推进了什么。
- character_decision：主角是否做出了可追踪的决策或行为偏移；`decision_detail` 必须写明具体动作。
- motif_redundancy：本场复读了哪些母题；若复读，本次是否承担了新功能、是否仍在复用同一功能、这种同功能复用是否仍被允许；`redundancy_reason` 必须明确。
- canon_consistency：是否与 `chapter_state` / 前文 / locked notes 冲突；若冲突，列出 `consistency_issues`。
如果以下任一项不满足，默认不能 lock：没有新信息、没有情节推进、没有决策变化、母题复读且无新功能、存在 canon 冲突。

你输出的 JSON 必须包含这些字段：
- `task_id`
- `verdict`
- `task_goal_fulfilled`
- `major_issues`
- `minor_issues`
- `recommended_next_step`
- `summary`
- `information_gain` {{ `has_new_information`, `new_information_items` }}
- `plot_progress` {{ `has_plot_progress`, `progress_reason` }}
- `character_decision` {{ `has_decision_or_behavior_shift`, `decision_detail` }}
- `motif_redundancy` {{ `repeated_motifs`, `new_function_motifs`, `stale_function_motifs`, `repeated_same_function_motifs`, `consecutive_same_function_motifs`, `repetition_has_new_function`, `same_function_reuse_allowed`, `redundancy_reason` }}
- `canon_consistency` {{ `is_consistent`, `consistency_issues` }}

【当前任务】
{task_text}

【当前章节状态】
{chapter_state}

【动态章节 tracker】
{tracker_summary_text}

【直接前文 / 基准文本】
{normalized_based_on}

【待审草稿】
{normalized_draft}

再次强调：你的最终输出必须是单个 JSON 对象本身，首字符必须是 {{，末字符必须是 }}。
"""
def extract_reviewer_json(
    config: dict,
    task_id: str,
    raw_review_text: str,
) -> dict:
    system_prompt = """你是 JSON 提纯助手。
你的任务是把一段审稿意见提炼成一个合法 JSON 对象。
不要输出解释，不要输出 markdown，不要输出代码块，只输出 JSON。"""

    user_prompt = f"""请把下面这段审稿意见提炼为合法 JSON。

JSON 必须包含这些字段：
- task_id
- verdict (lock / revise / rewrite)
- task_goal_fulfilled (true / false)
- major_issues (string array)
- minor_issues (string array)
- recommended_next_step (lock_scene / create_revision_task / rewrite_scene)
- summary (string)
- information_gain ({'{'} has_new_information, new_information_items {'}'})
- plot_progress ({'{'} has_plot_progress, progress_reason {'}'})
- character_decision ({'{'} has_decision_or_behavior_shift, decision_detail {'}'})
- motif_redundancy ({'{'} repeated_motifs, repetition_has_new_function, redundancy_reason {'}'})
- canon_consistency ({'{'} is_consistent, consistency_issues {'}'})

task_id 固定为：
{task_id}

下面是待提炼的审稿意见：
{raw_review_text}
"""

    refined = call_ollama(
        model=config["reviewer"]["model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        base_url=config["reviewer"]["base_url"],
        num_ctx=config["reviewer"]["num_ctx"],
        temperature=config["reviewer"].get("temperature", 0.1),
        timeout=config["reviewer"]["request_timeout"],
        num_predict=config["reviewer"].get("refine_num_predict", 700),
        response_format={"type": "object"},
    )

    return extract_json_object(extract_message_text(refined))


def review_scene_file(config: dict, draft_rel_path: str) -> tuple[dict, str]:
    draft_text = clip_text(
        read_text(draft_rel_path),
        config["reviewer"].get("draft_max_chars", 3000),
    )

    task_text = clip_text(
        read_text("01_inputs/tasks/current_task.md"),
        config["reviewer"].get("task_max_chars", 2200),
    )
    task_id = extract_markdown_field(task_text, "task_id") or "unknown-task"

    chapter_state_path = extract_markdown_field(task_text, "chapter_state")
    if chapter_state_path:
        chapter_state = clip_text(
            read_text(chapter_state_path),
            config["reviewer"].get("chapter_state_max_chars", 2200),
        )
    else:
        chapter_state = "[未提供 chapter_state]"

    based_on_path = extract_markdown_field(task_text, "based_on")
    if based_on_path:
        based_on_text = clip_text(
            read_text(based_on_path),
            config["reviewer"].get("based_on_max_chars", 2200),
        )
    else:
        based_on_text = "[未提供 based_on]"

    tracker_bundle = load_review_tracker_bundle(task_text, chapter_state=chapter_state)

    if should_use_deepseek(config):
        structured_result = review_scene_with_deepseek(
            scene_text=draft_text,
            scene_metadata={
                "task_id": task_id,
                "draft_rel_path": draft_rel_path,
                "api_key": str(config["reviewer"].get("api_key", "")).strip(),
                "api_key_env": str(config["reviewer"].get("api_key_env", "")).strip(),
                "request_timeout": config["reviewer"].get("request_timeout", 120),
                "max_retries": config["reviewer"].get("max_retries", 3),
                "retry_backoff_base": config["reviewer"].get("retry_backoff_base", 1.0),
            },
            canon_context={
                "task_id": task_id,
                "task_text": task_text,
                "chapter_state": chapter_state,
                "based_on_text": based_on_text,
                "tracker_bundle": tracker_bundle,
            },
        )
        result = structured_review_to_legacy_result(structured_result)
        result = normalize_review_result(
            result,
            json.dumps(structured_result, ensure_ascii=False),
            task_text=task_text,
            draft_text=draft_text,
            based_on_text=based_on_text,
            chapter_state=chapter_state,
        )
        result["task_id"] = task_id
        result = ensure_non_empty_structural_fields(result)
        out_path = f"02_working/reviews/{task_id}_reviewer.json"
        save_text(out_path, json.dumps(result, ensure_ascii=False, indent=2))
        result["review_result_path"] = save_structured_deepseek_review(ROOT, structured_result)
        result["repair_plan_path"] = save_repair_plan(ROOT, StructuredReviewResult.from_dict(structured_result))
        return result, out_path

    system_prompt = read_text("prompts/reviewer_system.md")
    schema = json.loads(read_text("prompts/reviewer_output_schema.json"))

    user_prompt = build_review_prompt(
        task_text=task_text,
        chapter_state=chapter_state,
        based_on_text=based_on_text,
        draft_text=draft_text,
    )

    raw_response = call_ollama(
        model=config["reviewer"]["model"],
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        base_url=config["reviewer"]["base_url"],
        num_ctx=config["reviewer"]["num_ctx"],
        temperature=config["reviewer"].get("temperature", 0.1),
        timeout=config["reviewer"]["request_timeout"],
        num_predict=config["reviewer"].get("num_predict", 900),
        response_format=schema,
    )
    raw_output = extract_message_text(raw_response)
    raw_output_for_retry = raw_output
    raw_output_meta = {"low_value_english": False, "repeated_fragments": 0, "truncated": False}

    try:
        result = extract_json_object(raw_output)
    except Exception:
        raw_output_for_retry, raw_output_meta = sanitize_reviewer_raw_output(raw_output)
        print("Reviewer 原始输出如下：")
        print("=" * 40)
        print(raw_output_for_retry)
        print("=" * 40)
        if not raw_output.strip():
            print("Reviewer 原始响应摘要：")
            print(summarize_response_for_debug(raw_response))
            raise ValueError(
                "Reviewer 模型返回空内容；请求已成功到达服务端，但可读输出字段为空，可能是模型空 content 或返回在非标准字段。"
            )
        print("Reviewer 未直接输出 JSON，正在尝试提纯为 JSON...")
        try:
            result = extract_reviewer_json(config, task_id, raw_output_for_retry)
        except Exception:
            print("Reviewer 二次提纯失败，正在使用本地规则生成兜底审稿结果...")
            result = build_local_review_fallback(
                task_id,
                raw_output_for_retry,
                task_text=task_text,
                draft_text=draft_text,
                based_on_text=based_on_text,
                chapter_state=chapter_state,
                low_confidence=raw_output_meta["low_value_english"],
            )

    result = normalize_review_result(
        result,
        raw_output_for_retry,
        task_text=task_text,
        low_confidence=raw_output_meta["low_value_english"],
        draft_text=draft_text,
        based_on_text=based_on_text,
        chapter_state=chapter_state,
    )
    result["task_id"] = task_id
    result = ensure_non_empty_structural_fields(result)
    validate(instance=result, schema=schema)
    validate_review_content(result)

    out_path = f"02_working/reviews/{task_id}_reviewer.json"
    save_text(out_path, json.dumps(result, ensure_ascii=False, indent=2))
    result["review_result_path"] = save_structured_review_result(ROOT, result)
    result["repair_plan_path"] = save_repair_plan(ROOT, build_structured_review_result(result))
    return result, out_path

def main() -> None:
    try:
        config = load_yaml("app/config.yaml")

        if len(sys.argv) < 2:
            print("用法: python3 app/review_scene.py <scene_draft_path>")
            sys.exit(1)

        result, out_path = review_scene_file(config, sys.argv[1])

        print(f"已保存 reviewer 结果: {out_path}")
        print("审稿结论：", result["verdict"])
        print("建议下一步：", result["recommended_next_step"])

    except FileNotFoundError as e:
        print(f"缺少输入文件: {e}")
    except json.JSONDecodeError as e:
        print(f"JSON 解析失败: {e}")
    except requests.exceptions.ReadTimeout:
        print("运行失败: reviewer 请求超时")
    except Exception as e:
        print(f"运行失败: {e}")


if __name__ == "__main__":
    main()
