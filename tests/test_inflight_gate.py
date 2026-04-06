from core.queue.queue import InFlightGate


def test_inflight_gate_blocks_duplicate_until_release():
    gate = InFlightGate()

    assert gate.try_acquire("article-1") is True
    assert gate.try_acquire("article-1") is False

    gate.release("article-1")

    assert gate.try_acquire("article-1") is True


def test_inflight_gate_keys_are_isolated():
    gate = InFlightGate()

    assert gate.try_acquire("article-1") is True
    assert gate.try_acquire("article-2") is True
