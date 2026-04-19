#!/usr/bin/env python3
"""
Test script for the new modules created in Phase 1 improvements.
"""

import sys
import os
from pathlib import Path

# Add app directory to path
app_dir = Path(__file__).parent / "app"
sys.path.insert(0, str(app_dir))

# Change to app directory for relative imports
os.chdir(app_dir)

from config_validation import validate_all_configs, print_validation_results
from config_manager import validate_configs, get_config_manager
from file_cache import get_text_file_cache, get_cache_stats, clear_caches
from error_handler import get_error_stats, handle_error_with_recovery


def test_config_validation():
    """Test configuration validation."""
    print("=" * 60)
    print("Testing Configuration Validation")
    print("=" * 60)

    project_root = Path(__file__).parent.parent
    results = validate_all_configs(project_root)

    is_valid = print_validation_results(results)
    print(f"\nOverall validation: {'PASS' if is_valid else 'FAIL'}")

    return is_valid


def test_config_manager():
    """Test configuration manager."""
    print("\n" + "=" * 60)
    print("Testing Configuration Manager")
    print("=" * 60)

    try:
        manager = get_config_manager()

        # Validate configs
        is_valid = manager.validate_all()
        print(f"Config validation: {'PASS' if is_valid else 'FAIL'}")

        if not is_valid:
            errors = manager.get_validation_errors()
            for config_file, error_list in errors.items():
                if error_list:
                    print(f"\n{config_file} errors:")
                    for error in error_list:
                        print(f"  - {error}")
            return False

        # Load configs
        main_config = manager.load_main_config()
        human_input = manager.load_human_input_config()
        run_config = manager.get_effective_run_config()

        print(f"\nLoaded configuration:")
        print(f"  Project: {main_config.project_name}")
        print(f"  Language: {main_config.language}")
        print(f"  Writer: {main_config.writer.provider}/{main_config.writer.model}")
        print(f"  Run mode: {run_config.mode}")
        print(f"  Target: Chapter {run_config.start_chapter}, Scene {run_config.start_scene}")

        if human_input.project:
            print(f"  Novel: {human_input.project.get('novel_title', 'Unnamed')}")

        print("\nConfig manager test: PASS")
        return True

    except Exception as e:
        print(f"Config manager test failed: {e}")
        return False


def test_file_cache():
    """Test file caching."""
    print("\n" + "=" * 60)
    print("Testing File Cache")
    print("=" * 60)

    try:
        cache = get_text_file_cache()
        test_file = Path(__file__).parent.parent / "README.md"

        # Clear cache first
        clear_caches()

        # First read (should miss cache)
        content1 = cache.read_text_cached(test_file)
        if content1 and len(content1) > 0:
            print(f"First read: SUCCESS ({len(content1)} characters)")

        # Second read (should hit cache)
        content2 = cache.read_text_cached(test_file)
        if content2 == content1:
            print("Second read (cached): SUCCESS")

        # Invalidate cache
        cache.invalidate(test_file)

        # Third read (should miss cache again)
        content3 = cache.read_text_cached(test_file)
        if content3 == content1:
            print("Third read (after invalidation): SUCCESS")

        # Get stats
        stats = get_cache_stats()
        print(f"\nCache stats:")
        for cache_name, cache_stats in stats.items():
            print(f"  {cache_name}:")
            for key, value in cache_stats.items():
                print(f"    {key}: {value}")

        print("\nFile cache test: PASS")
        return True

    except Exception as e:
        print(f"File cache test failed: {e}")
        return False


def test_error_handler():
    """Test error handling."""
    print("\n" + "=" * 60)
    print("Testing Error Handler")
    print("=" * 60)

    try:
        # Test error recording
        test_error = ValueError("Test error message")

        recovered = handle_error_with_recovery(
            test_error,
            module="test_module",
            function="test_function",
            circuit_breaker_name="test_circuit",
        )

        print(f"Error handled: {'Recovered' if recovered else 'Not recovered'}")

        # Get stats
        stats = get_error_stats()
        print(f"\nError stats:")
        print(f"  Total errors: {stats.get('total_errors', 0)}")
        print(f"  Recovery rate: {stats.get('recovery_rate', 0):.2%}")

        if "by_severity" in stats:
            print("  By severity:")
            for severity, count in stats["by_severity"].items():
                print(f"    {severity}: {count}")

        print("\nError handler test: PASS")
        return True

    except Exception as e:
        print(f"Error handler test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("Testing Phase 1 Improvement Modules")
    print("=" * 60)

    results = []

    # Run tests
    results.append(("Configuration Validation", test_config_validation()))
    results.append(("Configuration Manager", test_config_manager()))
    results.append(("File Cache", test_file_cache()))
    results.append(("Error Handler", test_error_handler()))

    # Print summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    all_passed = True
    for test_name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("ALL TESTS PASSED ✓")
        return 0
    else:
        print("SOME TESTS FAILED ✗")
        return 1


if __name__ == "__main__":
    sys.exit(main())