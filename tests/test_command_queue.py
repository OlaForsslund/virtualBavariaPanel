import threading

from gateway.command_queue import CommandQueue


def test_drain_runs_pending_commands_in_order():
    q = CommandQueue()
    calls = []
    q.submit(lambda: calls.append(1))
    q.submit(lambda: calls.append(2))

    n = q.drain()

    assert calls == [1, 2]
    assert n == 2


def test_drain_on_empty_queue_is_a_noop():
    q = CommandQueue()
    assert q.drain() == 0


def test_drain_only_runs_commands_submitted_before_it_was_called():
    q = CommandQueue()
    calls = []
    q.submit(lambda: calls.append(1))

    assert q.drain() == 1
    assert q.drain() == 0
    assert calls == [1]


def test_failing_command_does_not_stop_the_drain():
    q = CommandQueue()
    calls = []

    def boom():
        raise RuntimeError("nope")

    q.submit(boom)
    q.submit(lambda: calls.append("still ran"))

    n = q.drain()

    assert n == 2
    assert calls == ["still ran"]


def test_submit_from_another_thread_is_visible_to_drain():
    q = CommandQueue()
    calls = []
    t = threading.Thread(target=lambda: q.submit(lambda: calls.append("from thread")))
    t.start()
    t.join()

    q.drain()

    assert calls == ["from thread"]
