import pytest
import logging
from unittest.mock import patch

from mlox.scheduler import ProcessScheduler


class DummyProcess:
    def __init__(self, alive=True):
        self._alive = alive
        self.pid = 1234
        self.daemon = False

    def is_alive(self):
        return self._alive

    def start(self):
        self._alive = False


class DummyManager:
    def dict(self):
        return {}


@pytest.fixture
def scheduler():
    with (
        patch("multiprocessing.Manager", return_value=DummyManager()),
        patch("multiprocessing.Process", side_effect=lambda *a, **kw: DummyProcess()),
    ):
        sched = ProcessScheduler(
            max_processes=2, watchdog_wakeup_sec=0.1, watchdog_timeout_sec=1
        )
        return sched


def test_add_and_run_function(scheduler):
    def dummy_process(a_param):
        return a_param * 2

    def dummy_callback(result, name):
        return f"Callback-{name}-{result}"

    scheduler.add(
        process=dummy_process,
        callback=dummy_callback,
        params_process={"a_param": 5},
        params_callback={"name": "test1"},
    )
    # Simulate process completion
    for k in scheduler.queue:
        scheduler.queue[k].state = scheduler.STATE_FINISHED
    scheduler.remove_entries_by_state()
    assert not scheduler.queue  # Should be empty after cleanup


def test_error_handling(scheduler):
    def error_process():
        raise ValueError("Test error")

    def dummy_callback(result, name):
        return f"Callback-{name}-{result}"

    scheduler.add(
        process=error_process,
        callback=dummy_callback,
        params_process={},
        params_callback={"name": "err"},
    )
    # Simulate error
    for k in scheduler.queue:
        scheduler.queue[k].state = scheduler.STATE_ERROR
    errored = [v for v in scheduler.queue.values() if v.state == scheduler.STATE_ERROR]
    assert len(errored) == 1


def test_timeout_handling(scheduler):
    def slow_process():
        return 42

    def dummy_callback(result, name):
        return f"Callback-{name}-{result}"

    scheduler.add(
        process=slow_process,
        callback=dummy_callback,
        params_process={},
        params_callback={"name": "timeout"},
    )
    # Simulate timeout
    for k in scheduler.queue:
        scheduler.queue[k].state = scheduler.STATE_TIMEOUT
    timed_out = [
        v for v in scheduler.queue.values() if v.state == scheduler.STATE_TIMEOUT
    ]
    assert len(timed_out) == 1


def test_multiple_entries(scheduler):
    def dummy_process(a_param):
        return a_param

    def dummy_callback(result, name):
        return f"Callback-{name}-{result}"

    for i in range(3):
        scheduler.add(
            process=dummy_process,
            callback=dummy_callback,
            params_process={"a_param": i},
            params_callback={"name": f"multi{i}"},
        )
    assert len(scheduler.queue) == 3
    for k in scheduler.queue:
        scheduler.queue[k].state = scheduler.STATE_FINISHED
    scheduler.remove_entries_by_state()
    assert not scheduler.queue
