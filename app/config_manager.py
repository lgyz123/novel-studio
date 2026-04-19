"""
Unified configuration manager for novel-studio.

This module provides a centralized interface for loading, validating,
and accessing all configuration files in the project.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

from config_validation import (
    ConfigValidationError,
    validate_all_configs,
    validate_human_input_config,
    validate_main_config,
)
from project_inputs import load_human_input as load_human_input_legacy
from runtime_config import load_runtime_config as load_runtime_config_legacy


@dataclass
class PathsConfig:
    """Configuration for directory paths."""

    manifest_dir: str = "00_manifest"
    inputs_dir: str = "01_inputs"
    working_dir: str = "02_working"
    locked_dir: str = "03_locked"
    prompts_dir: str = "prompts"
    context_dir: str = "02_working/context"

    def resolve(self, root: Path) -> Dict[str, Path]:
        """Resolve all paths relative to the project root."""
        return {
            "manifest": root / self.manifest_dir,
            "inputs": root / self.inputs_dir,
            "working": root / self.working_dir,
            "locked": root / self.locked_dir,
            "prompts": root / self.prompts_dir,
            "context": root / self.context_dir,
        }


@dataclass
class AgentConfig:
    """Configuration for the agent."""

    name: str = "single-agent"
    mode: str = "prototype"
    validate_local_models_on_start: bool = True


@dataclass
class ModelConfig:
    """Configuration for a model provider."""

    provider: str
    model: str
    base_url: str = ""
    api_key_env: str = ""
    num_ctx: Optional[int] = None
    temperature: Optional[float] = None
    request_timeout: Optional[int] = None
    num_predict: Optional[int] = None


@dataclass
class SceneTypePolicy:
    """Configuration for scene type policies."""

    max_consecutive_weak_scenes: int = 2
    weak_scene_types: List[str] = field(default_factory=lambda: ["atmosphere", "transition", "reflection"])
    forced_after_weak_streak: List[str] = field(
        default_factory=lambda: ["discovery", "decision", "consequence", "confrontation", "reveal"]
    )
    min_type_ratios: Dict[str, float] = field(default_factory=dict)
    combined_min_type_ratios: Dict[str, Any] = field(default_factory=dict)
    combined_max_type_ratios: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SupervisorConfig:
    """Configuration for the supervisor."""

    enabled: bool = True
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com"
    api_key_env: str = "MY_DEEPSEEK_API_KEY"
    request_timeout: int = 120
    max_retries: int = 3
    retry_backoff_base: float = 1.0
    scene_type_policy: SceneTypePolicy = field(default_factory=SceneTypePolicy)


@dataclass
class GenerationConfig:
    """Configuration for text generation."""

    compile_num_ctx: int = 4096
    write_num_ctx: int = 6144
    writer_context_max_chars: int = 8000
    temperature: float = 0.25
    request_timeout: int = 900
    preferred_length_override: str = "1500-2600字"
    deepseek_takeover_enabled: bool = True
    deepseek_takeover_after_local_fallbacks: int = 2
    deepseek_takeover_request_timeout: int = 180
    deepseek_takeover_num_predict: int = 1800
    max_auto_revisions: int = 5
    local_manual_intervention_after: int = 3
    auto_continue_until_scene: int = 20
    max_supervisor_rounds: int = 8
    supervisor_rescue_draft_enabled: bool = True


@dataclass
class RunConfig:
    """Configuration for runtime behavior."""

    mode: str = "continue"
    start_chapter: int = 1
    start_scene: int = 1
    target_chapter: int = 1
    target_scene: int = 20
    max_scenes_per_chapter: Optional[int] = None
    restart_from_task: str = ""


@dataclass
class OutputConfig:
    """Configuration for output directories."""

    working_dir: str = "02_working"
    context_file: str = "02_working/context/current_context.md"
    review_dir: str = "02_working/reviews"
    draft_dir: str = "02_working/drafts"


@dataclass
class MainConfig:
    """Main configuration container."""

    project_name: str = "novel-studio"
    language: str = "zh-CN"
    paths: PathsConfig = field(default_factory=PathsConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    writer: ModelConfig = field(default_factory=lambda: ModelConfig(provider="deepseek", model="deepseek-chat"))
    reviewer: ModelConfig = field(default_factory=lambda: ModelConfig(provider="deepseek", model="deepseek-chat"))
    supervisor: SupervisorConfig = field(default_factory=SupervisorConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    run: RunConfig = field(default_factory=RunConfig)
    output: OutputConfig = field(default_factory=OutputConfig)


@dataclass
class HumanInputConfig:
    """Human input configuration container."""

    project: Dict[str, str] = field(default_factory=dict)
    cast: Dict[str, Any] = field(default_factory=dict)
    story_blueprint: Dict[str, Any] = field(default_factory=dict)
    world: Dict[str, str] = field(default_factory=dict)
    manual_required: Dict[str, List[str]] = field(default_factory=dict)
    manual_reference_files: List[str] = field(default_factory=list)


class ConfigManager:
    """Manager for loading and accessing all configuration files."""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root or Path(__file__).resolve().parent.parent
        self._main_config: Optional[MainConfig] = None
        self._human_input_config: Optional[HumanInputConfig] = None
        self._run_config_overrides: Dict[str, Any] = {}
        self._validation_errors: Dict[str, List[str]] = {}

    def validate_all(self) -> bool:
        """Validate all configuration files."""
        self._validation_errors = validate_all_configs(self.project_root)
        return all(len(errors) == 0 for errors in self._validation_errors.values())

    def get_validation_errors(self) -> Dict[str, List[str]]:
        """Get validation errors for all configuration files."""
        return self._validation_errors.copy()

    def load_main_config(self, validate: bool = True) -> MainConfig:
        """Load and parse the main configuration file."""
        if self._main_config is not None:
            return self._main_config

        config_path = self.project_root / "app" / "config.yaml"

        if validate:
            errors = validate_main_config(config_path)
            if errors:
                raise ConfigValidationError(
                    f"Main configuration validation failed with {len(errors)} error(s)",
                    errors=errors,
                )

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}

            # Parse paths
            paths_data = data.get("paths", {})
            paths = PathsConfig(
                manifest_dir=paths_data.get("manifest_dir", "00_manifest"),
                inputs_dir=paths_data.get("inputs_dir", "01_inputs"),
                working_dir=paths_data.get("working_dir", "02_working"),
                locked_dir=paths_data.get("locked_dir", "03_locked"),
                prompts_dir=paths_data.get("prompts_dir", "prompts"),
                context_dir=paths_data.get("context_dir", "02_working/context"),
            )

            # Parse agent
            agent_data = data.get("agent", {})
            agent = AgentConfig(
                name=agent_data.get("name", "single-agent"),
                mode=agent_data.get("mode", "prototype"),
                validate_local_models_on_start=agent_data.get("validate_local_models_on_start", True),
            )

            # Parse writer
            writer_data = data.get("writer", {})
            writer = ModelConfig(
                provider=writer_data.get("provider", "deepseek"),
                model=writer_data.get("model", "deepseek-chat"),
                base_url=writer_data.get("base_url", ""),
                api_key_env=writer_data.get("api_key_env", ""),
            )

            # Parse reviewer
            reviewer_data = data.get("reviewer", {})
            reviewer = ModelConfig(
                provider=reviewer_data.get("provider", "deepseek"),
                model=reviewer_data.get("model", "deepseek-chat"),
                base_url=reviewer_data.get("base_url", ""),
                api_key_env=reviewer_data.get("api_key_env", ""),
                num_ctx=reviewer_data.get("num_ctx"),
                temperature=reviewer_data.get("temperature"),
                request_timeout=reviewer_data.get("request_timeout"),
                num_predict=reviewer_data.get("num_predict"),
            )

            # Parse supervisor
            supervisor_data = data.get("supervisor", {})
            scene_type_policy_data = supervisor_data.get("scene_type_policy", {})
            scene_type_policy = SceneTypePolicy(
                max_consecutive_weak_scenes=scene_type_policy_data.get("max_consecutive_weak_scenes", 2),
                weak_scene_types=scene_type_policy_data.get("weak_scene_types", ["atmosphere", "transition", "reflection"]),
                forced_after_weak_streak=scene_type_policy_data.get(
                    "forced_after_weak_streak", ["discovery", "decision", "consequence", "confrontation", "reveal"]
                ),
                min_type_ratios=scene_type_policy_data.get("min_type_ratios", {}),
                combined_min_type_ratios=scene_type_policy_data.get("combined_min_type_ratios", {}),
                combined_max_type_ratios=scene_type_policy_data.get("combined_max_type_ratios", {}),
            )
            supervisor = SupervisorConfig(
                enabled=supervisor_data.get("enabled", True),
                model=supervisor_data.get("model", "deepseek-chat"),
                base_url=supervisor_data.get("base_url", "https://api.deepseek.com"),
                api_key_env=supervisor_data.get("api_key_env", "MY_DEEPSEEK_API_KEY"),
                request_timeout=supervisor_data.get("request_timeout", 120),
                max_retries=supervisor_data.get("max_retries", 3),
                retry_backoff_base=supervisor_data.get("retry_backoff_base", 1.0),
                scene_type_policy=scene_type_policy,
            )

            # Parse generation
            generation_data = data.get("generation", {})
            generation = GenerationConfig(
                compile_num_ctx=generation_data.get("compile_num_ctx", 4096),
                write_num_ctx=generation_data.get("write_num_ctx", 6144),
                writer_context_max_chars=generation_data.get("writer_context_max_chars", 8000),
                temperature=generation_data.get("temperature", 0.25),
                request_timeout=generation_data.get("request_timeout", 900),
                preferred_length_override=generation_data.get("preferred_length_override", "1500-2600字"),
                deepseek_takeover_enabled=generation_data.get("deepseek_takeover_enabled", True),
                deepseek_takeover_after_local_fallbacks=generation_data.get("deepseek_takeover_after_local_fallbacks", 2),
                deepseek_takeover_request_timeout=generation_data.get("deepseek_takeover_request_timeout", 180),
                deepseek_takeover_num_predict=generation_data.get("deepseek_takeover_num_predict", 1800),
                max_auto_revisions=generation_data.get("max_auto_revisions", 5),
                local_manual_intervention_after=generation_data.get("local_manual_intervention_after", 3),
                auto_continue_until_scene=generation_data.get("auto_continue_until_scene", 20),
                max_supervisor_rounds=generation_data.get("max_supervisor_rounds", 8),
                supervisor_rescue_draft_enabled=generation_data.get("supervisor_rescue_draft_enabled", True),
            )

            # Parse run config (will be overridden by run_config.yaml if it exists)
            run_data = data.get("run", {})
            run = RunConfig(
                mode=run_data.get("mode", "continue"),
                start_chapter=run_data.get("start_chapter", 1),
                start_scene=run_data.get("start_scene", 1),
                target_chapter=run_data.get("target_chapter", 1),
                target_scene=run_data.get("target_scene", 20),
                max_scenes_per_chapter=run_data.get("max_scenes_per_chapter"),
                restart_from_task=run_data.get("restart_from_task", ""),
            )

            # Parse output
            output_data = data.get("output", {})
            output = OutputConfig(
                working_dir=output_data.get("working_dir", "02_working"),
                context_file=output_data.get("context_file", "02_working/context/current_context.md"),
                review_dir=output_data.get("review_dir", "02_working/reviews"),
                draft_dir=output_data.get("draft_dir", "02_working/drafts"),
            )

            self._main_config = MainConfig(
                project_name=data.get("project_name", "novel-studio"),
                language=data.get("language", "zh-CN"),
                paths=paths,
                agent=agent,
                writer=writer,
                reviewer=reviewer,
                supervisor=supervisor,
                generation=generation,
                run=run,
                output=output,
            )

            return self._main_config

        except Exception as e:
            raise ConfigValidationError(f"Failed to load main configuration: {str(e)}")

    def load_human_input_config(self, validate: bool = True) -> HumanInputConfig:
        """Load and parse the human input configuration file."""
        if self._human_input_config is not None:
            return self._human_input_config

        config_path = self.project_root / "01_inputs" / "human_input.yaml"

        if not config_path.exists():
            self._human_input_config = HumanInputConfig()
            return self._human_input_config

        if validate:
            errors = validate_human_input_config(config_path)
            if errors:
                raise ConfigValidationError(
                    f"Human input configuration validation failed with {len(errors)} error(s)",
                    errors=errors,
                )

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}

            self._human_input_config = HumanInputConfig(
                project=data.get("project", {}),
                cast=data.get("cast", {}),
                story_blueprint=data.get("story_blueprint", {}),
                world=data.get("world", {}),
                manual_required=data.get("manual_required", {}),
                manual_reference_files=data.get("manual_reference_files", []),
            )

            return self._human_input_config

        except Exception as e:
            raise ConfigValidationError(f"Failed to load human input configuration: {str(e)}")

    def load_run_config_overrides(self) -> Dict[str, Any]:
        """Load run configuration overrides from run_config.yaml."""
        if self._run_config_overrides:
            return self._run_config_overrides

        config_path = self.project_root / "01_inputs" / "run_config.yaml"

        if not config_path.exists():
            self._run_config_overrides = {}
            return self._run_config_overrides

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}

            self._run_config_overrides = data.get("run", {})
            return self._run_config_overrides

        except Exception as e:
            raise ConfigValidationError(f"Failed to load run configuration: {str(e)}")

    def get_effective_run_config(self) -> RunConfig:
        """Get the effective run configuration with overrides applied."""
        main_config = self.load_main_config()
        overrides = self.load_run_config_overrides()

        # Create a copy of the run config
        run_config_dict = {
            "mode": main_config.run.mode,
            "start_chapter": main_config.run.start_chapter,
            "start_scene": main_config.run.start_scene,
            "target_chapter": main_config.run.target_chapter,
            "target_scene": main_config.run.target_scene,
            "max_scenes_per_chapter": main_config.run.max_scenes_per_chapter,
            "restart_from_task": main_config.run.restart_from_task,
        }

        # Apply overrides
        for key, value in overrides.items():
            if key in run_config_dict:
                run_config_dict[key] = value

        return RunConfig(**run_config_dict)

    def get_resolved_paths(self) -> Dict[str, Path]:
        """Get resolved paths for all directories."""
        main_config = self.load_main_config()
        return main_config.paths.resolve(self.project_root)

    def get_writer_config(self) -> ModelConfig:
        """Get writer configuration."""
        main_config = self.load_main_config()
        return main_config.writer

    def get_reviewer_config(self) -> ModelConfig:
        """Get reviewer configuration."""
        main_config = self.load_main_config()
        return main_config.reviewer

    def get_supervisor_config(self) -> SupervisorConfig:
        """Get supervisor configuration."""
        main_config = self.load_main_config()
        return main_config.supervisor

    def get_generation_config(self) -> GenerationConfig:
        """Get generation configuration."""
        main_config = self.load_main_config()
        return main_config.generation

    def legacy_compat_load_runtime_config(self) -> Dict[str, Any]:
        """Legacy compatibility method to load runtime config as dictionary."""
        return load_runtime_config_legacy(self.project_root)

    def legacy_compat_load_human_input(self) -> Dict[str, Any]:
        """Legacy compatibility method to load human input as dictionary."""
        return load_human_input_legacy(self.project_root)


# Global instance for convenience
_config_manager: Optional[ConfigManager] = None


def get_config_manager(project_root: Optional[Path] = None) -> ConfigManager:
    """Get or create the global configuration manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(project_root)
    return _config_manager


def validate_configs() -> bool:
    """Validate all configuration files and print results."""
    manager = get_config_manager()
    is_valid = manager.validate_all()
    errors = manager.get_validation_errors()

    for config_file, error_list in errors.items():
        if not error_list:
            print(f"✓ {config_file}: Valid")
        else:
            print(f"✗ {config_file}: {len(error_list)} error(s)")
            for error in error_list:
                print(f"  - {error}")

    return is_valid


if __name__ == "__main__":
    """Command-line interface for configuration management."""
    import sys

    try:
        # Validate all configs
        is_valid = validate_configs()

        if not is_valid:
            print("\nConfiguration validation failed. Please fix the errors above.")
            sys.exit(1)

        # Load and display config summary
        manager = get_config_manager()
        main_config = manager.load_main_config()
        human_input = manager.load_human_input_config()
        run_config = manager.get_effective_run_config()

        print("\n" + "=" * 60)
        print("Configuration Summary")
        print("=" * 60)

        print(f"\nProject: {main_config.project_name} ({main_config.language})")
        print(f"Agent: {main_config.agent.name} ({main_config.agent.mode})")

        print(f"\nWriter: {main_config.writer.provider}/{main_config.writer.model}")
        print(f"Reviewer: {main_config.reviewer.provider}/{main_config.reviewer.model}")
        print(f"Supervisor: {'Enabled' if main_config.supervisor.enabled else 'Disabled'}")

        print(f"\nRun Mode: {run_config.mode}")
        print(f"Target: Chapter {run_config.start_chapter}, Scene {run_config.start_scene}")
        print(f"  → Chapter {run_config.target_chapter}, Scene {run_config.target_scene}")

        if human_input.project:
            print(f"\nNovel: {human_input.project.get('novel_title', 'Unnamed')}")
            print(f"Genre: {human_input.project.get('genre', 'Unknown')}")

        print("\n" + "=" * 60)
        print("All configuration files are valid and loaded successfully.")
        sys.exit(0)

    except ConfigValidationError as e:
        print(f"\nConfiguration error: {e}")
        if e.errors:
            for error in e.errors:
                print(f"  - {error}")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        sys.exit(1)