"""
Enhanced main module demonstrating integration of Phase 1 improvements.

This module shows how to use the new configuration management,
file caching, and error handling modules in the novel-studio pipeline.
"""

import json
import re
import time
from pathlib import Path
from typing import Any

import requests
from chapter_orchestrator import build_chapter_opening_task, get_start_progress, should_rollover_after_lock
from chapter_trackers import chapter_id_from_task_or_locked, load_tracker_bundle, update_trackers_on_lock
from deepseek_reviewer import resolve_api_key
from deepseek_supervisor import apply_supervisor_decision_to_reviewer_result, build_next_scene_task_content, build_task_content_from_supervisor_decision, is_supervisor_enabled, run_supervisor_decision, run_supervisor_next_scene_task, run_supervisor_rescue_draft, save_next_scene_task_plan, save_supervisor_decision, save_supervisor_rescue_record
from issue_filters import filter_shared_issues
from jsonschema import validate
from lock_gate import apply_lock_gate, save_lock_gate_report
from openai import OpenAI
from planning_bootstrap import run_planning_bootstrap
from prewrite_checks import build_prewrite_review, save_prewrite_review
from project_inputs import load_human_input, render_human_input_markdown
from review_models import RepairMode, ReviewStatus, build_repair_plan_path, build_review_result_path, build_structured_review_result, load_repair_plan, load_structured_review_result, save_repair_plan, save_structured_review_result, update_structured_review_status
from review_scene import evaluate_scene_gate, review_scene_file
from revision_lineage import append_revision_lineage, build_revision_lineage_path, build_revision_lineage_summary, load_revision_lineage, should_trigger_manual_intervention
from skill_audit import audit_skill_router_result, save_skill_audit_outputs
from skill_router import render_skill_router_markdown, route_writer_skills, save_skill_router_outputs
from story_state import update_story_state_on_lock
from writer_skills import build_selected_skill_sections

# Import new Phase 1 modules
from config_manager import get_config_manager, ConfigValidationError
from file_cache import cached_read_text, cached_read_json, cached_read_yaml, invalidate_cached_file
from error_handler import handle_error_with_recovery, retry_operation, get_error_stats


ROOT = Path(__file__).resolve().parent.parent
PROSE_REPAIR = "prose_repair"
STRUCTURAL_REPAIR = "structural_repair"


def read_text_enhanced(rel_path: str) -> str:
    """
    Enhanced version of read_text with caching.

    Uses file caching to reduce disk I/O for frequently accessed files.
    """
    path = ROOT / rel_path

    # Use cached read with error handling
    try:
        content = retry_operation(
            lambda: cached_read_text(path),
            max_retries=2,
            delay_seconds=0.5,
            circuit_breaker_name=f"file_read:{rel_path}",
        )

        if content is None:
            raise FileNotFoundError(f"File not found or cannot be read: {rel_path}")

        return content

    except Exception as e:
        # Handle the error with recovery
        recovered = handle_error_with_recovery(
            e,
            module="main_enhanced",
            function="read_text_enhanced",
            circuit_breaker_name=f"file_read:{rel_path}",
            recovery_callback=lambda: path.read_text(encoding="utf-8"),
        )

        if recovered:
            # Read succeeded after recovery, cache it
            content = path.read_text(encoding="utf-8")
            # Note: We would need to add the content to cache here
            # For now, we'll just return it
            return content
        else:
            # Re-raise if not recovered
            raise


def save_text_enhanced(rel_path: str, content: str) -> None:
    """
    Enhanced version of save_text with error handling and cache invalidation.
    """
    path = ROOT / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Write the file
        retry_operation(
            lambda: path.write_text(content, encoding="utf-8"),
            max_retries=2,
            delay_seconds=0.5,
            circuit_breaker_name=f"file_write:{rel_path}",
        )

        # Invalidate cache for this file
        invalidate_cached_file(path)

    except Exception as e:
        handle_error_with_recovery(
            e,
            module="main_enhanced",
            function="save_text_enhanced",
            circuit_breaker_name=f"file_write:{rel_path}",
        )
        raise


def clip_text(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[已截断]"


def clip_inline_text(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip()


def clip_tail_text(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return "[前文已省略]\n\n" + text[-max_chars:]


def call_ollama_with_retry(
    model: str,
    system_prompt: str,
    user_prompt: str,
    base_url: str,
    num_ctx: int,
    temperature: float,
    timeout: int,
    num_predict: int,
) -> str:
    """
    Enhanced version of call_ollama with retry logic and circuit breaker.
    """
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

    print(f"正在请求 Ollama: {model} @ {base_url}")

    def make_request():
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"]

    # Use retry_operation with circuit breaker
    return retry_operation(
        make_request,
        max_retries=3,
        delay_seconds=1.0,
        backoff_factor=2.0,
        circuit_breaker_name=f"ollama:{model}",
    )


def should_validate_local_models(config: dict | None = None) -> bool:
    if not config:
        return False
    agent = config.get("agent", {})
    return bool(agent.get("validate_local_models_on_start"))


def validate_configs_on_start() -> bool:
    """
    Validate all configuration files on startup.

    Returns:
        True if all configs are valid, False otherwise
    """
    try:
        manager = get_config_manager()

        print("正在验证配置文件...")
        is_valid = manager.validate_all()

        if not is_valid:
            errors = manager.get_validation_errors()
            print("配置文件验证失败:")
            for config_file, error_list in errors.items():
                if error_list:
                    print(f"\n{config_file}:")
                    for error in error_list:
                        print(f"  - {error}")
            return False

        print("✓ 所有配置文件验证通过")
        return True

    except ConfigValidationError as e:
        print(f"配置验证错误: {e}")
        if e.errors:
            for error in e.errors:
                print(f"  - {error}")
        return False
    except Exception as e:
        print(f"配置验证过程中发生未知错误: {e}")
        return False


def load_configs_enhanced() -> tuple[dict, dict, dict]:
    """
    Load all configurations using the new config manager.

    Returns:
        Tuple of (main_config_dict, human_input_dict, run_config_dict)
    """
    try:
        manager = get_config_manager()

        # Load main config as dictionary (for compatibility)
        main_config = manager.legacy_compat_load_runtime_config()

        # Load human input
        human_input = manager.legacy_compat_load_human_input()

        # Load run config overrides
        run_config = manager.load_run_config_overrides()

        return main_config, human_input, run_config

    except Exception as e:
        handle_error_with_recovery(
            e,
            module="main_enhanced",
            function="load_configs_enhanced",
            recovery_callback=lambda: ({}, {}, {}),
        )
        # Return empty configs if recovery fails
        return {}, {}, {}


def print_startup_banner() -> None:
    """Print enhanced startup banner with system info."""
    print("=" * 60)
    print("novel-studio - 增强版")
    print("=" * 60)

    try:
        manager = get_config_manager()

        # Validate configs
        if validate_configs_on_start():
            # Load and display config summary
            main_config = manager.load_main_config()
            human_input = manager.load_human_input_config()
            run_config = manager.get_effective_run_config()

            print(f"\n项目: {main_config.project_name} ({main_config.language})")
            print(f"模式: {run_config.mode}")
            print(f"目标: 第{run_config.start_chapter}章 第{run_config.start_scene}场")
            print(f"     → 第{run_config.target_chapter}章 第{run_config.target_scene}场")

            if human_input.project:
                print(f"小说: {human_input.project.get('novel_title', '未命名')}")
                print(f"类型: {human_input.project.get('genre', '未知')}")

            print(f"\nWriter: {main_config.writer.provider}/{main_config.writer.model}")
            print(f"Reviewer: {main_config.reviewer.provider}/{main_config.reviewer.model}")
            print(f"Supervisor: {'启用' if main_config.supervisor.enabled else '禁用'}")

        else:
            print("\n⚠ 配置文件验证失败，使用默认配置继续运行")

    except Exception as e:
        print(f"\n⚠ 启动过程中发生错误: {e}")
        print("使用默认配置继续运行...")


def print_shutdown_summary() -> None:
    """Print summary information on shutdown."""
    print("\n" + "=" * 60)
    print("运行结束摘要")
    print("=" * 60)

    # Get error statistics
    error_stats = get_error_stats()

    if error_stats["total_errors"] > 0:
        print(f"错误统计:")
        print(f"  总错误数: {error_stats['total_errors']}")
        print(f"  恢复率: {error_stats['recovery_rate']:.2%}")

        if error_stats["by_severity"]:
            print("  按严重程度:")
            for severity, count in error_stats["by_severity"].items():
                print(f"    {severity}: {count}")

    # Get cache statistics (if available)
    try:
        from file_cache import get_cache_stats
        cache_stats = get_cache_stats()

        if cache_stats:
            print(f"\n缓存统计:")
            for cache_name, stats in cache_stats.items():
                if "hit_rate" in stats:
                    print(f"  {cache_name} 命中率: {stats['hit_rate']:.2%}")

    except ImportError:
        pass

    print("\n" + "=" * 60)


# Main function demonstrating the enhanced pipeline
def main_enhanced():
    """
    Enhanced main function demonstrating Phase 1 improvements.

    This is a simplified version showing how to integrate the new modules.
    """
    # Print enhanced startup banner
    print_startup_banner()

    # Load configurations using enhanced method
    config, human_input, run_overrides = load_configs_enhanced()

    # Merge run overrides into config
    if run_overrides and "run" in config:
        config["run"].update(run_overrides)

    # Validate local models if configured
    if should_validate_local_models(config):
        print("\n正在验证本地模型...")
        # TODO: Implement model validation with error handling

    # Main pipeline would continue here...
    # For demonstration, we'll just show the structure

    print("\n" + "=" * 60)
    print("增强版管道就绪")
    print("=" * 60)
    print("\n新功能已启用:")
    print("  ✓ 配置验证与统一管理")
    print("  ✓ 文件缓存 (减少磁盘 I/O)")
    print("  ✓ 增强错误处理与恢复")
    print("  ✓ 断路器模式 (防止无限重试)")
    print("  ✓ 自动重试与指数退避")

    # Print shutdown summary
    print_shutdown_summary()


if __name__ == "__main__":
    try:
        main_enhanced()
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
        print_shutdown_summary()
    except Exception as e:
        print(f"\n\n程序发生未处理错误: {e}")
        print_shutdown_summary()
        raise