import os
import time
import logging
import traceback
import multiprocessing as mp

from datetime import datetime
from threading import Timer
from typing import Dict, Callable


class ProcessSchedulerError:
    def __init__(self, e, tb):
        self.e = e
        self.tb = tb


def _process_init() -> None:
    pass


def _process_run(ind, results, func, params) -> None:
    try:
        results[ind] = func(**params)
    except BaseException as e:
        results[ind] = ProcessSchedulerError(e, traceback.format_exc())


class ProcessScheduler:
    STATE_IDLE = "Idle"
    STATE_RUNNING = "Running"
    STATE_FINISHED = "Finished"
    STATE_TIMEOUT = "Failure (timeout)"
    STATE_ERROR = "Failure (unknown)"

    def __init__(
        self,
        max_processes: int = 2,
        watchdog_wakeup_sec: int = 1,
        watchdog_timeout_sec: int = 1500,
    ) -> None:
        self.max_processes: int = max_processes
        self.watchdog_wakeup_sec: int = watchdog_wakeup_sec
        self.watchdog_timeout_sec: int = watchdog_timeout_sec

        try:
            mp.set_start_method("fork")
        except RuntimeError:
            pass

        manager = mp.Manager()
        self.processes_results: Dict[int, object] = manager.dict()
        self.queue_callables: list[tuple[Callable, Callable]] = []
        self.queue_parameters: list[tuple[dict, dict]] = []
        self.queue_states: list[str] = []
        self.processes: list[tuple[datetime, mp.Process, int]] = [
            (datetime.now(), mp.Process(target=_process_init), -1)
            for _ in range(self.max_processes)
        ]
        self.watchdog_timer: Timer | None = None
        self._watchdog()

    def _watchdog(self) -> None:
        next_ind = self.get_next()
        for p_ind, (start_time, proc, queue_ind) in enumerate(self.processes):
            # Collect results
            if not proc.is_alive() and queue_ind >= 0:
                if isinstance(self.processes_results.get(p_ind), ProcessSchedulerError):
                    self.queue_states[queue_ind] = self.STATE_ERROR
                    logging.error(
                        f"Scheduler error in process {p_ind}:\n{self.processes_results[p_ind].tb}"
                    )
                else:
                    self.queue_states[queue_ind] = self.STATE_FINISHED
                    callback = self.queue_callables[queue_ind][1]
                    callback(
                        self.processes_results.get(p_ind),
                        **self.queue_parameters[queue_ind][1],
                    )
                self.processes[p_ind] = (
                    start_time,
                    mp.Process(target=_process_init),
                    -1,
                )

            # Start new process if possible
            if not proc.is_alive() and next_ind >= 0:
                self.queue_states[next_ind] = self.STATE_RUNNING
                new_proc = mp.Process(
                    target=_process_run,
                    args=(
                        p_ind,
                        self.processes_results,
                        self.queue_callables[next_ind][0],
                        self.queue_parameters[next_ind][0],
                    ),
                )
                new_proc.daemon = True
                new_proc.start()
                self.processes[p_ind] = (datetime.now(), new_proc, next_ind)
                next_ind = self.get_next()

            # Timeout check
            if (
                queue_ind >= 0
                and (datetime.now() - start_time).seconds > self.watchdog_timeout_sec
            ):
                logging.info(f"Watchdog: Process {queue_ind} takes too long. Killing.")
                os.kill(proc.pid, 9)
                self.queue_states[queue_ind] = self.STATE_TIMEOUT
                self.processes[p_ind] = (
                    start_time,
                    mp.Process(target=_process_init),
                    -1,
                )

        # Restart watchdog
        self.watchdog_timer = Timer(self.watchdog_wakeup_sec, self._watchdog)
        self.watchdog_timer.daemon = True
        self.watchdog_timer.start()

    def get_next(self) -> int:
        for idx, state in enumerate(self.queue_states):
            if state == self.STATE_IDLE:
                return idx
        return -1

    def add(
        self,
        process: Callable,
        callback: Callable,
        params_process: dict,
        params_callback: dict,
    ) -> None:
        self.queue_callables.append((process, callback))
        self.queue_parameters.append((params_process, params_callback))
        self.queue_states.append(self.STATE_IDLE)

    def get_inds_matching_callback_params(
        self, param_name: str, param_value: object
    ) -> list[int]:
        inds: list[int] = []
        for i, (_, cb_params) in enumerate(self.queue_parameters):
            if param_name in cb_params and cb_params[param_name] == param_value:
                inds.append(i)
        return inds


def my_process(a_param):
    print("my_process", a_param)
    # takes a long time
    time.sleep(10)
    return 1, 2


def my_callback(x, name):
    print("my_callback")
    print(x)
    print(name)


if __name__ == "__main__":
    print("Scheduler Demo")

    ps = ProcessScheduler()
    ps.add(
        process=my_process,
        callback=my_callback,
        params_process={"a_param": "hello"},
        params_callback={"name": "me"},
    )

    print("Wait loop...")
    while True:
        time.sleep(5)
