import gc
import os
import queue
import threading
import time
from typing import Any, Callable

from core.print import print_error, print_info, print_success, print_warning


def _env_int(key: str, default: int) -> int:
    try:
        v = int(str(os.getenv(key, str(default))).strip() or default)
        return v
    except Exception:
        return default


class TaskQueueManager:
    """In-process task queue with a small worker pool (threads).

    Notes:
    - This project runs under uvicorn; using multiple uvicorn workers (processes) will create
      separate in-memory queues. Prefer uvicorn workers=1 and use queue workers for concurrency.
    - Tasks should be idempotent and create their own DB sessions.
    """

    def __init__(self, maxsize: int = 0, *, tag: str = "", workers: int = 1):
        self._queue: queue.Queue[tuple[Callable[..., Any], tuple[Any, ...], dict[str, Any]]] = queue.Queue(
            maxsize=maxsize
        )
        self._lock = threading.Lock()
        self._is_running = False
        self._threads: list[threading.Thread] = []

        self.tag = tag
        self.workers = max(1, int(workers or 1))

    def add_task(self, task: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        self._queue.put((task, args, kwargs))
        print_success(f"{self.tag}队列任务添加成功")

    def run_task_background(self) -> None:
        """Start worker threads once (idempotent)."""
        with self._lock:
            if self._is_running:
                return
            self._is_running = True

        for i in range(self.workers):
            t = threading.Thread(target=self._worker_loop, daemon=True, name=f"TaskQueue[{self.tag}]#{i}")
            t.start()
            self._threads.append(t)
        print_warning(f"{self.tag}队列任务后台运行 workers={self.workers}")

    def _worker_loop(self, timeout: float = 0.5) -> None:
        while True:
            with self._lock:
                if not self._is_running:
                    return
            try:
                task, args, kwargs = self._queue.get(timeout=timeout)
            except queue.Empty:
                continue

            try:
                start_time = time.time()
                task(*args, **kwargs)
                duration = time.time() - start_time
                print_info(f"\n任务执行完成，耗时: {duration:.2f}秒")
            except Exception as e:
                print_error(f"队列任务执行失败: {e}")
            finally:
                self._queue.task_done()
                gc.collect()

    def stop(self) -> None:
        with self._lock:
            self._is_running = False

    def join(self, timeout: float | None = None) -> None:
        """Block until all tasks are completed (or timeout)."""
        start = time.monotonic()
        while True:
            if self._queue.unfinished_tasks == 0:  # type: ignore[attr-defined]
                return
            if timeout is not None and (time.monotonic() - start) > timeout:
                raise TimeoutError(f"queue not drained: pending={self._queue.qsize()}")
            time.sleep(0.05)

    def get_queue_info(self) -> dict[str, Any]:
        with self._lock:
            return {
                "tag": self.tag,
                "workers": self.workers,
                "is_running": self._is_running,
                "pending_tasks": self._queue.qsize(),
            }

    def clear_queue(self) -> None:
        cleared = 0
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                cleared += 1
            except queue.Empty:
                break
        print_success(f"{self.tag}队列已清空: {cleared}")

    def delete_queue(self) -> None:
        self.stop()
        self.clear_queue()
        print_success(f"{self.tag}队列已删除")


# Default queues
TaskQueue = TaskQueueManager(tag="默认", workers=_env_int("QUEUE_WORKERS", 6))
InsightsQueue = TaskQueueManager(tag="洞察", workers=_env_int("INSIGHTS_QUEUE_WORKERS", 3))

# Start background workers by default for better UX (best-effort).
TaskQueue.run_task_background()
InsightsQueue.run_task_background()

