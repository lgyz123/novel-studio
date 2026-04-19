"""
Enhanced error handling module for novel-studio.

This module provides comprehensive error handling, recovery strategies,
and circuit breakers to prevent infinite loops and improve robustness.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar, Union

from config_manager import ConfigManager, get_config_manager


class ErrorSeverity(Enum):
    """Severity levels for errors."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Categories for errors."""

    CONFIGURATION = "configuration"
    FILE_IO = "file_io"
    NETWORK = "network"
    VALIDATION = "validation"
    PROCESSING = "processing"
    RESOURCE = "resource"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class ErrorContext:
    """Context information for an error."""

    module: str = ""
    function: str = ""
    line_number: Optional[int] = None
    timestamp: float = field(default_factory=time.time)
    extra_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ErrorRecord:
    """Record of an error for logging and analysis."""

    message: str
    severity: ErrorSeverity
    category: ErrorCategory
    context: ErrorContext
    exception: Optional[Exception] = None
    recovery_action: Optional[str] = None
    retry_count: int = 0


class CircuitBreaker:
    """
    Circuit breaker pattern implementation.

    Prevents repeated calls to failing operations by opening the circuit
    after a threshold of failures is reached.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: int = 60,
        half_open_max_attempts: int = 3,
    ):
        """
        Initialize the circuit breaker.

        Args:
            failure_threshold: Number of failures before opening the circuit
            reset_timeout: Time in seconds before attempting to close the circuit
            half_open_max_attempts: Max attempts in half-open state before opening again
        """
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.half_open_max_attempts = half_open_max_attempts

        self.state = "closed"  # closed, open, half_open
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.half_open_attempts = 0

    def can_execute(self) -> bool:
        """Check if the operation can be executed."""
        current_time = time.time()

        if self.state == "closed":
            return True

        elif self.state == "open":
            if self.last_failure_time is None:
                return False

            # Check if reset timeout has passed
            if current_time - self.last_failure_time >= self.reset_timeout:
                self.state = "half_open"
                self.half_open_attempts = 0
                return True
            return False

        elif self.state == "half_open":
            if self.half_open_attempts < self.half_open_max_attempts:
                return True
            # Too many attempts in half-open state, open again
            self.state = "open"
            self.last_failure_time = current_time
            return False

        return False

    def record_success(self) -> None:
        """Record a successful execution."""
        if self.state == "half_open":
            # Success in half-open state, close the circuit
            self.state = "closed"
            self.failure_count = 0
            self.last_failure_time = None
            self.half_open_attempts = 0
        elif self.state == "closed":
            # Reset failure count on success
            self.failure_count = 0

    def record_failure(self) -> None:
        """Record a failed execution."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == "half_open":
            self.half_open_attempts += 1
            if self.half_open_attempts >= self.half_open_max_attempts:
                self.state = "open"

        elif self.state == "closed":
            if self.failure_count >= self.failure_threshold:
                self.state = "open"

    def get_state(self) -> Dict[str, Any]:
        """Get the current state of the circuit breaker."""
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time,
            "half_open_attempts": self.half_open_attempts,
        }


class ErrorHandler:
    """
    Main error handler with recovery strategies and circuit breakers.
    """

    def __init__(self, config_manager: Optional[ConfigManager] = None):
        """
        Initialize the error handler.

        Args:
            config_manager: Configuration manager instance
        """
        self.config_manager = config_manager or get_config_manager()
        self.error_log: List[ErrorRecord] = []
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.recovery_strategies: Dict[ErrorCategory, List[Callable]] = {}

        # Load configuration for error handling
        self._load_config()

    def _load_config(self) -> None:
        """Load error handling configuration."""
        # Default configuration
        self.max_error_log_size = 1000
        self.enable_circuit_breakers = True
        self.circuit_breaker_defaults = {
            "failure_threshold": 5,
            "reset_timeout": 60,
            "half_open_max_attempts": 3,
        }

        # TODO: Load from config file when error handling config is added

    def get_circuit_breaker(self, name: str) -> CircuitBreaker:
        """
        Get or create a circuit breaker for a specific operation.

        Args:
            name: Name of the circuit breaker

        Returns:
            CircuitBreaker instance
        """
        if name not in self.circuit_breakers:
            self.circuit_breakers[name] = CircuitBreaker(**self.circuit_breaker_defaults)
        return self.circuit_breakers[name]

    def record_error(
        self,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        context: Optional[ErrorContext] = None,
        exception: Optional[Exception] = None,
        recovery_action: Optional[str] = None,
    ) -> ErrorRecord:
        """
        Record an error.

        Args:
            message: Error message
            severity: Error severity
            category: Error category
            context: Error context
            exception: Original exception (if any)
            recovery_action: Recovery action taken

        Returns:
            ErrorRecord instance
        """
        if context is None:
            context = ErrorContext()

        record = ErrorRecord(
            message=message,
            severity=severity,
            category=category,
            context=context,
            exception=exception,
            recovery_action=recovery_action,
        )

        # Add to log
        self.error_log.append(record)

        # Trim log if too large
        if len(self.error_log) > self.max_error_log_size:
            self.error_log = self.error_log[-self.max_error_log_size:]

        return record

    def handle_error(
        self,
        error: Exception,
        context: Optional[ErrorContext] = None,
        circuit_breaker_name: Optional[str] = None,
        recovery_callback: Optional[Callable] = None,
    ) -> bool:
        """
        Handle an error with recovery strategies.

        Args:
            error: The exception to handle
            context: Error context
            circuit_breaker_name: Name of circuit breaker to update
            recovery_callback: Optional callback for custom recovery

        Returns:
            True if error was handled/recovered, False otherwise
        """
        # Determine error category
        category = self._categorize_error(error)

        # Create context if not provided
        if context is None:
            context = ErrorContext()

        # Record the error
        record = self.record_error(
            message=str(error),
            severity=self._determine_severity(error, category),
            category=category,
            context=context,
            exception=error,
        )

        # Update circuit breaker if specified
        if circuit_breaker_name and self.enable_circuit_breakers:
            circuit_breaker = self.get_circuit_breaker(circuit_breaker_name)
            circuit_breaker.record_failure()

        # Attempt recovery
        recovered = False
        recovery_action = None

        if recovery_callback:
            try:
                recovery_callback()
                recovery_action = "custom_recovery_callback"
                recovered = True
            except Exception as recovery_error:
                # Record recovery failure
                self.record_error(
                    message=f"Recovery callback failed: {recovery_error}",
                    severity=ErrorSeverity.WARNING,
                    category=category,
                    context=context,
                )

        elif category in self.recovery_strategies:
            # Try registered recovery strategies
            for strategy in self.recovery_strategies[category]:
                try:
                    strategy(error, context)
                    recovery_action = strategy.__name__
                    recovered = True
                    break
                except Exception as strategy_error:
                    # Record strategy failure
                    self.record_error(
                        message=f"Recovery strategy {strategy.__name__} failed: {strategy_error}",
                        severity=ErrorSeverity.WARNING,
                        category=category,
                        context=context,
                    )

        # Update record with recovery info
        if recovered and recovery_action:
            record.recovery_action = recovery_action

        return recovered

    def _categorize_error(self, error: Exception) -> ErrorCategory:
        """Categorize an error based on its type."""
        error_type = type(error).__name__
        error_str = str(error).lower()

        # File I/O errors
        if any(file_error in error_type for file_error in ["FileNotFound", "Permission", "IOError", "OSError"]):
            return ErrorCategory.FILE_IO

        # Network errors
        if any(network_error in error_type for network_error in ["Connection", "Timeout", "HTTP", "API"]):
            return ErrorCategory.NETWORK

        # Configuration errors
        if any(config_error in error_type for config_error in ["Config", "Validation", "Schema"]):
            return ErrorCategory.CONFIGURATION

        # Validation errors
        if any(validation_error in error_type for validation_error in ["Validation", "Schema", "TypeError", "ValueError"]):
            return ErrorCategory.VALIDATION

        # Timeout errors
        if "timeout" in error_str or "timed out" in error_str:
            return ErrorCategory.TIMEOUT

        # Resource errors
        if any(resource_error in error_str for resource_error in ["memory", "disk", "resource", "quota"]):
            return ErrorCategory.RESOURCE

        return ErrorCategory.UNKNOWN

    def _determine_severity(self, error: Exception, category: ErrorCategory) -> ErrorSeverity:
        """Determine the severity of an error."""
        error_str = str(error).lower()

        # Critical errors
        if any(critical in error_str for critical in ["fatal", "critical", "cannot proceed", "unrecoverable"]):
            return ErrorSeverity.CRITICAL

        # Configuration errors are usually critical
        if category == ErrorCategory.CONFIGURATION:
            return ErrorSeverity.CRITICAL

        # Resource errors are usually critical
        if category == ErrorCategory.RESOURCE:
            return ErrorSeverity.CRITICAL

        # Network errors are usually errors
        if category == ErrorCategory.NETWORK:
            return ErrorSeverity.ERROR

        # File I/O errors are usually errors
        if category == ErrorCategory.FILE_IO:
            return ErrorSeverity.ERROR

        # Validation errors are usually warnings
        if category == ErrorCategory.VALIDATION:
            return ErrorSeverity.WARNING

        # Timeout errors are usually warnings
        if category == ErrorCategory.TIMEOUT:
            return ErrorSeverity.WARNING

        return ErrorSeverity.ERROR

    def register_recovery_strategy(
        self,
        category: ErrorCategory,
        strategy: Callable,
    ) -> None:
        """
        Register a recovery strategy for an error category.

        Args:
            category: Error category
            strategy: Recovery function (takes error and context as arguments)
        """
        if category not in self.recovery_strategies:
            self.recovery_strategies[category] = []
        self.recovery_strategies[category].append(strategy)

    def get_error_summary(self, last_n: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get a summary of recent errors.

        Args:
            last_n: Number of recent errors to include (None for all)

        Returns:
            List of error summaries
        """
        errors = self.error_log if last_n is None else self.error_log[-last_n:]

        summary = []
        for error in errors:
            summary.append({
                "message": error.message,
                "severity": error.severity.value,
                "category": error.category.value,
                "timestamp": error.context.timestamp,
                "module": error.context.module,
                "recovery_action": error.recovery_action,
                "retry_count": error.retry_count,
            })

        return summary

    def get_error_stats(self) -> Dict[str, Any]:
        """Get statistics about errors."""
        if not self.error_log:
            return {
                "total_errors": 0,
                "by_severity": {},
                "by_category": {},
                "recovery_rate": 0.0,
            }

        total = len(self.error_log)
        by_severity = {}
        by_category = {}
        recovered_count = 0

        for error in self.error_log:
            # Count by severity
            severity = error.severity.value
            by_severity[severity] = by_severity.get(severity, 0) + 1

            # Count by category
            category = error.category.value
            by_category[category] = by_category.get(category, 0) + 1

            # Count recoveries
            if error.recovery_action:
                recovered_count += 1

        return {
            "total_errors": total,
            "by_severity": by_severity,
            "by_category": by_category,
            "recovery_rate": recovered_count / total if total > 0 else 0.0,
            "circuit_breakers": {
                name: breaker.get_state()
                for name, breaker in self.circuit_breakers.items()
            },
        }

    def save_error_log(self, filepath: Path) -> bool:
        """
        Save error log to a file.

        Args:
            filepath: Path to save the error log

        Returns:
            True if successful, False otherwise
        """
        try:
            summary = self.get_error_summary()
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, default=str)
            return True
        except Exception:
            return False

    def clear_error_log(self) -> None:
        """Clear the error log."""
        self.error_log.clear()


# Global error handler instance
_error_handler: Optional[ErrorHandler] = None


def get_error_handler() -> ErrorHandler:
    """Get or create the global error handler instance."""
    global _error_handler
    if _error_handler is None:
        _error_handler = ErrorHandler()
    return _error_handler


def handle_error_with_recovery(
    error: Exception,
    module: str = "",
    function: str = "",
    circuit_breaker_name: Optional[str] = None,
    recovery_callback: Optional[Callable] = None,
) -> bool:
    """
    Handle an error with the global error handler.

    Args:
        error: The exception to handle
        module: Module where error occurred
        function: Function where error occurred
        circuit_breaker_name: Name of circuit breaker to update
        recovery_callback: Optional callback for custom recovery

    Returns:
        True if error was handled/recovered, False otherwise
    """
    handler = get_error_handler()
    context = ErrorContext(module=module, function=function)
    return handler.handle_error(error, context, circuit_breaker_name, recovery_callback)


def get_error_stats() -> Dict[str, Any]:
    """Get statistics from the global error handler."""
    handler = get_error_handler()
    return handler.get_error_stats()


def save_error_log(filepath: Path) -> bool:
    """Save error log from the global error handler."""
    handler = get_error_handler()
    return handler.save_error_log(filepath)


# Common recovery strategies
def retry_operation(
    operation: Callable,
    max_retries: int = 3,
    delay_seconds: float = 1.0,
    backoff_factor: float = 2.0,
    circuit_breaker_name: Optional[str] = None,
) -> Any:
    """
    Retry an operation with exponential backoff.

    Args:
        operation: Function to retry
        max_retries: Maximum number of retries
        delay_seconds: Initial delay between retries
        backoff_factor: Multiplier for delay after each retry
        circuit_breaker_name: Name of circuit breaker to check

    Returns:
        Result of the operation

    Raises:
        Exception: If all retries fail
    """
    handler = get_error_handler()
    last_exception = None

    for attempt in range(max_retries + 1):
        # Check circuit breaker if specified
        if circuit_breaker_name:
            circuit_breaker = handler.get_circuit_breaker(circuit_breaker_name)
            if not circuit_breaker.can_execute():
                raise Exception(f"Circuit breaker '{circuit_breaker_name}' is open")

        try:
            result = operation()
            # Record success to circuit breaker
            if circuit_breaker_name:
                circuit_breaker.record_success()
            return result

        except Exception as e:
            last_exception = e

            # Handle the error
            recovered = handler.handle_error(
                e,
                context=ErrorContext(function=operation.__name__),
                circuit_breaker_name=circuit_breaker_name,
            )

            if attempt < max_retries:
                # Wait before retry
                wait_time = delay_seconds * (backoff_factor ** attempt)
                time.sleep(wait_time)
            else:
                # All retries failed
                if circuit_breaker_name:
                    circuit_breaker.record_failure()
                raise last_exception

    # This should never be reached
    raise last_exception


if __name__ == "__main__":
    """Command-line interface for error handling."""
    import sys

    handler = get_error_handler()

    if len(sys.argv) > 1 and sys.argv[1] == "stats":
        stats = handler.get_error_stats()
        print(json.dumps(stats, indent=2))

    elif len(sys.argv) > 1 and sys.argv[1] == "summary":
        last_n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        summary = handler.get_error_summary(last_n)
        print(json.dumps(summary, indent=2))

    elif len(sys.argv) > 1 and sys.argv[1] == "save":
        if len(sys.argv) > 2:
            filepath = Path(sys.argv[2])
        else:
            filepath = Path("error_log.json")

        if handler.save_error_log(filepath):
            print(f"Error log saved to {filepath}")
        else:
            print("Failed to save error log")

    elif len(sys.argv) > 1 and sys.argv[1] == "clear":
        handler.clear_error_log()
        print("Error log cleared")

    else:
        print("Usage:")
        print("  python error_handler.py stats           # Show error statistics")
        print("  python error_handler.py summary [N]     # Show last N errors (default: 10)")
        print("  python error_handler.py save [path]     # Save error log to file")
        print("  python error_handler.py clear           # Clear error log")