import time


def test_task_queue_runs_concurrently():
    # TaskQueueManager should support multiple workers so wall-clock time
    # is much shorter than sequential execution.
    from core.queue.queue import TaskQueueManager

    mgr = TaskQueueManager(tag="test", workers=4)
    mgr.run_task_background()

    start = time.monotonic()
    for _ in range(8):
        mgr.add_task(time.sleep, 0.2)

    mgr.join(timeout=10)
    elapsed = time.monotonic() - start

    # Sequential would be ~1.6s. With 4 workers, ~0.4-0.7s is expected.
    assert elapsed < 1.0

