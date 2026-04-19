"""
Configuration validation module for novel-studio.

This module provides schema validation for configuration files to ensure
they have the correct structure and required fields.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from jsonschema import Draft7Validator, ValidationError
from jsonschema.exceptions import SchemaError


class ConfigValidationError(Exception):
    """Exception raised when configuration validation fails."""

    def __init__(self, message: str, errors: Optional[List[str]] = None):
        super().__init__(message)
        self.errors = errors or []


def load_config_schema() -> Dict[str, Any]:
    """Load the JSON schema for configuration validation."""
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "project_name": {"type": "string"},
            "language": {"type": "string", "enum": ["zh-CN", "en-US"]},
            "paths": {
                "type": "object",
                "properties": {
                    "manifest_dir": {"type": "string"},
                    "inputs_dir": {"type": "string"},
                    "working_dir": {"type": "string"},
                    "locked_dir": {"type": "string"},
                    "prompts_dir": {"type": "string"},
                    "context_dir": {"type": "string"},
                },
                "required": ["manifest_dir", "inputs_dir", "working_dir", "locked_dir"],
            },
            "agent": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "mode": {"type": "string"},
                    "validate_local_models_on_start": {"type": "boolean"},
                },
                "required": ["name", "mode"],
            },
            "writer": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string"},
                    "model": {"type": "string"},
                    "base_url": {"type": "string"},
                    "api_key_env": {"type": "string"},
                },
                "required": ["provider", "model"],
            },
            "reviewer": {
                "type": "object",
                "properties": {
                    "provider": {"type": "string"},
                    "model": {"type": "string"},
                    "base_url": {"type": "string"},
                    "api_key_env": {"type": "string"},
                    "num_ctx": {"type": "integer", "minimum": 1},
                    "temperature": {"type": "number", "minimum": 0, "maximum": 2},
                    "request_timeout": {"type": "integer", "minimum": 1},
                    "num_predict": {"type": "integer", "minimum": 1},
                    "reference_num_predict": {"type": "integer", "minimum": 1},
                    "refine_num_predict": {"type": "integer", "minimum": 1},
                    "task_max_chars": {"type": "integer", "minimum": 1},
                    "chapter_state_max_chars": {"type": "integer", "minimum": 1},
                    "based_on_max_chars": {"type": "integer", "minimum": 1},
                    "draft_max_chars": {"type": "integer", "minimum": 1},
                },
                "required": ["provider", "model"],
            },
            "supervisor": {
                "type": "object",
                "properties": {
                    "enabled": {"type": "boolean"},
                    "model": {"type": "string"},
                    "base_url": {"type": "string"},
                    "api_key_env": {"type": "string"},
                    "request_timeout": {"type": "integer", "minimum": 1},
                    "max_retries": {"type": "integer", "minimum": 0},
                    "retry_backoff_base": {"type": "number", "minimum": 0},
                    "scene_type_policy": {
                        "type": "object",
                        "properties": {
                            "max_consecutive_weak_scenes": {"type": "integer", "minimum": 0},
                            "weak_scene_types": {"type": "array", "items": {"type": "string"}},
                            "forced_after_weak_streak": {"type": "array", "items": {"type": "string"}},
                            "min_type_ratios": {"type": "object", "additionalProperties": {"type": "number", "minimum": 0, "maximum": 1}},
                            "combined_min_type_ratios": {"type": "object"},
                            "combined_max_type_ratios": {"type": "object"},
                        },
                    },
                },
                "required": ["enabled", "model"],
            },
            "generation": {
                "type": "object",
                "properties": {
                    "compile_num_ctx": {"type": "integer", "minimum": 1},
                    "write_num_ctx": {"type": "integer", "minimum": 1},
                    "writer_context_max_chars": {"type": "integer", "minimum": 1},
                    "temperature": {"type": "number", "minimum": 0, "maximum": 2},
                    "request_timeout": {"type": "integer", "minimum": 1},
                    "preferred_length_override": {"type": "string"},
                    "deepseek_takeover_enabled": {"type": "boolean"},
                    "deepseek_takeover_after_local_fallbacks": {"type": "integer", "minimum": 0},
                    "deepseek_takeover_request_timeout": {"type": "integer", "minimum": 1},
                    "deepseek_takeover_num_predict": {"type": "integer", "minimum": 1},
                    "max_auto_revisions": {"type": "integer", "minimum": 0},
                    "local_manual_intervention_after": {"type": "integer", "minimum": 0},
                    "auto_continue_until_scene": {"type": "integer", "minimum": 0},
                    "max_supervisor_rounds": {"type": "integer", "minimum": 0},
                    "supervisor_rescue_draft_enabled": {"type": "boolean"},
                },
                "required": ["compile_num_ctx", "write_num_ctx", "writer_context_max_chars", "temperature", "request_timeout"],
            },
            "run": {
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["continue", "restart"]},
                    "start_chapter": {"type": "integer", "minimum": 1},
                    "start_scene": {"type": "integer", "minimum": 1},
                    "target_chapter": {"type": "integer", "minimum": 1},
                    "target_scene": {"type": "integer", "minimum": 1},
                    "max_scenes_per_chapter": {"type": ["integer", "null"], "minimum": 1},
                    "restart_from_task": {"type": "string"},
                },
                "required": ["mode", "start_chapter", "start_scene", "target_chapter", "target_scene"],
            },
            "output": {
                "type": "object",
                "properties": {
                    "working_dir": {"type": "string"},
                    "context_file": {"type": "string"},
                    "review_dir": {"type": "string"},
                    "draft_dir": {"type": "string"},
                },
                "required": ["working_dir", "context_file", "review_dir", "draft_dir"],
            },
        },
        "required": ["project_name", "language", "paths", "writer", "reviewer", "generation", "run"],
    }
    return schema


def load_human_input_schema() -> Dict[str, Any]:
    """Load the JSON schema for human input validation."""
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "project": {
                "type": "object",
                "properties": {
                    "novel_title": {"type": "string"},
                    "genre": {"type": "string"},
                    "audience": {"type": "string"},
                    "style": {"type": "string"},
                    "tone": {"type": "string"},
                    "hook": {"type": "string"},
                    "premise": {"type": "string"},
                    "themes": {"type": "string"},
                },
                "required": ["novel_title", "genre"],
            },
            "cast": {
                "type": "object",
                "properties": {
                    "protagonist": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "role": {"type": "string"},
                            "background": {"type": "string"},
                            "description": {"type": "string"},
                            "goal": {"type": "string"},
                            "desire": {"type": "string"},
                            "fear": {"type": "string"},
                        },
                        "required": ["name", "role"],
                    },
                    "supporting_roles": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "role": {"type": "string"},
                                "relationship": {"type": "string"},
                                "description": {"type": "string"},
                            },
                            "required": ["name", "role"],
                        },
                    },
                },
                "required": ["protagonist"],
            },
            "story_blueprint": {
                "type": "object",
                "properties": {
                    "opening_status": {"type": "string"},
                    "core_conflict": {"type": "string"},
                    "chapter_goal": {"type": "string"},
                    "first_chapter_goal": {"type": "string"},
                    "required_beats": {"type": "array", "items": {"type": "string"}},
                    "taboo_beats": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["opening_status", "core_conflict", "chapter_goal"],
            },
            "world": {
                "type": "object",
                "properties": {
                    "era": {"type": "string"},
                    "setting": {"type": "string"},
                    "power_system": {"type": "string"},
                    "social_order": {"type": "string"},
                    "taboos": {"type": "string"},
                },
            },
            "manual_required": {
                "type": "object",
                "properties": {
                    "must_have": {"type": "array", "items": {"type": "string"}},
                    "must_avoid": {"type": "array", "items": {"type": "string"}},
                    "open_questions": {"type": "array", "items": {"type": "string"}},
                    "review_checklist": {"type": "array", "items": {"type": "string"}},
                },
            },
            "manual_reference_files": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["project", "cast", "story_blueprint"],
    }
    return schema


def validate_config(config_data: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
    """
    Validate configuration data against a schema.

    Args:
        config_data: Configuration data to validate
        schema: JSON schema to validate against

    Returns:
        List of validation error messages (empty if valid)
    """
    try:
        validator = Draft7Validator(schema)
        errors = list(validator.iter_errors(config_data))

        error_messages = []
        for error in errors:
            # Format the error message
            path = ".".join(str(p) for p in error.path) if error.path else "root"
            error_messages.append(f"{path}: {error.message}")

        return error_messages

    except SchemaError as e:
        return [f"Schema error: {str(e)}"]


def validate_main_config(config_path: Path) -> List[str]:
    """
    Validate the main configuration file.

    Args:
        config_path: Path to the configuration file

    Returns:
        List of validation error messages (empty if valid)
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)

        if not isinstance(config_data, dict):
            return ["Configuration file must contain a YAML dictionary"]

        schema = load_config_schema()
        return validate_config(config_data, schema)

    except yaml.YAMLError as e:
        return [f"YAML parsing error: {str(e)}"]
    except Exception as e:
        return [f"Error reading configuration: {str(e)}"]


def validate_human_input_config(config_path: Path) -> List[str]:
    """
    Validate the human input configuration file.

    Args:
        config_path: Path to the human input configuration file

    Returns:
        List of validation error messages (empty if valid)
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)

        if not isinstance(config_data, dict):
            return ["Human input file must contain a YAML dictionary"]

        schema = load_human_input_schema()
        return validate_config(config_data, schema)

    except yaml.YAMLError as e:
        return [f"YAML parsing error: {str(e)}"]
    except Exception as e:
        return [f"Error reading human input: {str(e)}"]


def validate_all_configs(project_root: Path) -> Dict[str, List[str]]:
    """
    Validate all configuration files in the project.

    Args:
        project_root: Root directory of the project

    Returns:
        Dictionary mapping config file names to lists of error messages
    """
    results = {}

    # Validate main config
    main_config_path = project_root / "app" / "config.yaml"
    if main_config_path.exists():
        results["config.yaml"] = validate_main_config(main_config_path)

    # Validate human input
    human_input_path = project_root / "01_inputs" / "human_input.yaml"
    if human_input_path.exists():
        results["human_input.yaml"] = validate_human_input_config(human_input_path)

    # Validate run config (optional)
    run_config_path = project_root / "01_inputs" / "run_config.yaml"
    if run_config_path.exists():
        try:
            with open(run_config_path, 'r', encoding='utf-8') as f:
                run_config = yaml.safe_load(f)

            if not isinstance(run_config, dict):
                results["run_config.yaml"] = ["Run config must contain a YAML dictionary"]
            else:
                # Simple validation for run config
                errors = []
                if "run" not in run_config:
                    errors.append("Missing 'run' section")
                else:
                    run_section = run_config["run"]
                    required_fields = ["mode", "start_chapter", "start_scene", "target_chapter", "target_scene"]
                    for field in required_fields:
                        if field not in run_section:
                            errors.append(f"Missing required field in run section: {field}")

                results["run_config.yaml"] = errors

        except yaml.YAMLError as e:
            results["run_config.yaml"] = [f"YAML parsing error: {str(e)}"]
        except Exception as e:
            results["run_config.yaml"] = [f"Error reading run config: {str(e)}"]

    return results


def print_validation_results(results: Dict[str, List[str]]) -> bool:
    """
    Print validation results and return whether all configs are valid.

    Args:
        results: Dictionary mapping config file names to lists of error messages

    Returns:
        True if all configs are valid, False otherwise
    """
    all_valid = True

    for config_file, errors in results.items():
        if not errors:
            print(f"✓ {config_file}: Valid")
        else:
            all_valid = False
            print(f"✗ {config_file}: {len(errors)} error(s)")
            for error in errors:
                print(f"  - {error}")

    return all_valid


if __name__ == "__main__":
    """Command-line interface for configuration validation."""
    import sys

    project_root = Path(__file__).resolve().parent.parent
    results = validate_all_configs(project_root)

    is_valid = print_validation_results(results)

    if not is_valid:
        print("\nConfiguration validation failed. Please fix the errors above.")
        sys.exit(1)
    else:
        print("\nAll configuration files are valid.")
        sys.exit(0)