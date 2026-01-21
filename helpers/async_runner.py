# ================================================================
# Raven Framework
#
# Copyright (c) 2026 Raven Resonance, Inc.
# All Rights Reserved.
#
# This file is part of the Raven Framework and is proprietary
# to Raven Resonance, Inc. Unauthorized copying, modification,
# or distribution is prohibited without prior written permission.
#
# ================================================================

"""
Asynchronous task runner for Raven Framework.

This module provides functionality for running functions asynchronously in background
threads using Qt's thread pool, allowing non-blocking execution of CPU-intensive or
long-running operations.

Example:
    ```python
    from raven_framework.async_runner import AsyncRunner

    def long_running_task():
        # Do some work
        pass

    def on_complete():
        print("Task finished!")

    runner = AsyncRunner()
    runner.run(long_running_task, on_complete=on_complete)
    ```
"""

from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from .logger import get_logger

log = get_logger("AsyncRunner")


class AsyncSignalEmitter(QObject):
    """
    Signal emitter for asynchronous task completion notifications.

    This class emits a signal when an asynchronous task completes,
    allowing the main thread to be notified and execute callback functions.

    Signals:
        finished: Emitted when the async task completes (successfully or with error).
    """

    finished = Signal()
    """
    Signal emitted when the asynchronous task completes.
    
    This signal is emitted in the finally block of the worker,
    ensuring it's always sent regardless of success or failure.
    """


class AsyncRunner:
    """
    Asynchronous task runner using Qt's thread pool.

    This class manages the execution of functions in background threads,
    preventing blocking of the main UI thread. It automatically handles
    thread creation, execution, and cleanup.

    The AsyncRunner uses Qt's QThreadPool which manages a pool of reusable
    threads, making it efficient for running multiple concurrent tasks.

    Attributes:
        threadpool (QThreadPool): Qt thread pool managing worker threads.

    Example:
        ```python
        runner = AsyncRunner()

        def my_task():
            # Long-running operation
            result = expensive_computation()
            return result

        def callback():
            print("Task completed!")

        runner.run(my_task, on_complete=callback)
        ```
    """

    def __init__(self) -> None:
        """
        Initialize the AsyncRunner with a Qt thread pool.

        Creates a new QThreadPool instance for managing background threads.
        The thread pool automatically determines the optimal number of threads
        based on the system's CPU count.
        """
        self.threadpool = QThreadPool()
        log.info(
            f"Initialized AsyncRunner with max threads: {self.threadpool.maxThreadCount()}"
        )

    def run(
        self, func: Callable[[], Any], on_complete: Optional[Callable[[], None]] = None
    ) -> None:
        """
        Execute a function asynchronously in a background thread.

        Creates a worker thread and executes the provided function. If an
        `on_complete` callback is provided, it will be called when the task
        finishes (either successfully or with an error).

        Args:
            func: Function to execute asynchronously. Must be callable with no arguments.
            on_complete: Optional callback function to execute when the task completes.
                       This callback runs in the main thread. Defaults to None.

        Raises:
            RuntimeError: If the thread pool fails to start the worker.

        Note:
            - Exceptions in the worker function are caught and logged, but do not
              prevent the `on_complete` callback from being called.
            - The `on_complete` callback runs in the main thread (Qt event loop).
            - If the function raises an exception, it will be logged with full
              traceback information.

        Example:
            ```python
            runner = AsyncRunner()

            def process_data():
                # Heavy computation
                return process_large_dataset()

            def update_ui():
                print("Processing complete!")

            runner.run(process_data, on_complete=update_ui)
            ```
        """
        emitter = AsyncSignalEmitter()

        if not callable(func):
            raise TypeError(f"func must be callable, got {type(func).__name__}")

        if on_complete:
            emitter.finished.connect(on_complete)
            log.debug(f"Connected completion callback for function: {func.__name__}")

        class Worker(QRunnable):
            """
            Worker runnable that executes a function in a background thread.

            This inner class wraps the function execution with proper error handling
            and signal emission for completion notification.
            """

            @Slot()
            def run(self_inner) -> None:
                """
                Execute the function in the background thread.

                This method runs in a worker thread from the thread pool.
                It handles exceptions gracefully and always emits the finished signal.
                """
                try:
                    log.info(f"Worker started: {func.__name__}")
                    func()
                    log.info(f"Worker finished: {func.__name__}")
                except Exception as e:
                    log.error(f"Exception in AsyncRunner Worker: {e}", exc_info=True)
                finally:
                    emitter.finished.emit()

        worker = Worker()
        try:
            self.threadpool.start(worker)
            log.debug(f"Started worker thread for function: {func.__name__}")
        except RuntimeError as e:
            log.error(
                f"Failed to start worker thread for function {func.__name__}: {e}"
            )
            raise
