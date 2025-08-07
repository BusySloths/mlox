import os
import logging
import traceback
import multiprocessing as mp
from multiprocessing.managers import DictProxy

from datetime import datetime
from threading import Timer, current_thread
from threading import enumerate as threading_enumerate
from typing import Dict, Callable, cast

from dataclasses import dataclass


@dataclass
class QueueEntry:
    state: str
    process: Callable
    callback: Callable
    params_process: dict
    params_callback: dict


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
        disable_garbage_collection: bool = False,
    ) -> None:
        self.max_processes: int = max_processes
        self.watchdog_wakeup_sec: int = watchdog_wakeup_sec
        self.watchdog_timeout_sec: int = watchdog_timeout_sec
        self.watchdog_cleanup_iter: int = 10
        self.watchdog_cleanup_cntr: int = 0
        self.gc: bool = not disable_garbage_collection
        self.queue_lock = mp.Lock()
        try:
            mp.set_start_method("fork")
        except RuntimeError:
            pass

        self.queue: Dict[int, QueueEntry] = dict()
        self.queue_key_counter = 0

        manager = mp.Manager()
        self.processes_results: DictProxy[int, object] = manager.dict()
        self.processes: list[tuple[datetime, mp.Process, int]] = [
            (datetime.now(), mp.Process(target=_process_init), -1)
            for _ in range(self.max_processes)
        ]

        self.parent_pid = mp.current_process().pid

        self.watchdog_name = "mlox-scheduler-watchdog"
        self.watchdog_name_shutdown_postfix = "-shutdown"
        for t in threading_enumerate():
            if t.name == self.watchdog_name:
                t.name += self.watchdog_name_shutdown_postfix

        self.watchdog_shutdown = False
        self.watchdog_timer: Timer | None = None
        self._watchdog()

    def shutdown(self) -> None:
        self.watchdog_shutdown = True

    def _watchdog(self) -> None:
        self.watchdog_cleanup_cntr += 1
        if self.gc and self.watchdog_cleanup_cntr >= self.watchdog_cleanup_iter:
            self.watchdog_cleanup_cntr = 0
            self.remove_entries_by_state()

        for p_ind, (start_time, proc, key) in enumerate(self.processes):
            # Collect results
            if not proc.is_alive() and key >= 0:
                if isinstance(self.processes_results.get(p_ind), ProcessSchedulerError):
                    self.queue[key].state = self.STATE_ERROR
                    error = cast(ProcessSchedulerError, self.processes_results[p_ind])
                    logging.error(f"Scheduler error in process {p_ind}:\n{error.tb}")
                else:
                    self.queue[key].state = self.STATE_FINISHED
                    self.queue[key].callback(
                        self.processes_results.get(p_ind),
                        **self.queue[key].params_callback,
                    )
                self.processes[p_ind] = (
                    start_time,
                    mp.Process(target=_process_init),
                    -1,
                )

            # Start new process if possible
            if not proc.is_alive():
                next_key = self.get_next()
                if next_key >= 0:
                    self.queue[next_key].state = self.STATE_RUNNING
                    new_proc = mp.Process(
                        target=_process_run,
                        args=(
                            p_ind,
                            self.processes_results,
                            self.queue[next_key].process,
                            self.queue[next_key].params_process,
                        ),
                    )
                    new_proc.daemon = True
                    new_proc.start()
                    self.processes[p_ind] = (datetime.now(), new_proc, next_key)

            # Timeout check
            if (
                key >= 0
                and (datetime.now() - start_time).seconds > self.watchdog_timeout_sec
            ):
                logging.info(f"Watchdog: Process {key} takes too long. Killing.")
                if proc.pid is not None:
                    os.kill(proc.pid, 9)
                self.queue[key].state = self.STATE_TIMEOUT
                self.processes[p_ind] = (
                    start_time,
                    mp.Process(target=_process_init),
                    -1,
                )

        # Restart watchdog
        logging.debug(f"Watchdog: {current_thread().name}")
        logging.debug([t.name for t in threading_enumerate()])
        if not self.watchdog_shutdown:
            if not self.parent_process_exists():
                logging.warning(
                    f"Watchdog thread name mismatch, skipping restart. {self.parent_pid}"
                )
                mp.current_process().close()
                return
            if current_thread().name.endswith(self.watchdog_name_shutdown_postfix):
                logging.info(
                    f"Watchdog thread {current_thread().name} is shutting down, skipping restart."
                )
                mp.current_process().close()
                return
            self.watchdog_timer = Timer(self.watchdog_wakeup_sec, self._watchdog)
            self.watchdog_timer.name = self.watchdog_name
            self.watchdog_timer.daemon = True
            self.watchdog_timer.start()

    def parent_process_exists(self) -> bool:
        """Return True if process with pid exists, False otherwise."""
        try:
            if not self.parent_pid:
                return False
            # Signal 0 does not kill the process, just checks for existence
            os.kill(self.parent_pid, 0)
        except OSError:
            return False
        else:
            return True

    def get_next(self) -> int:
        """
        Generator that yields indices of idle processes asynchronously.
        Usage: for idx in scheduler.get_next(): ...
        """
        with self.queue_lock:
            for k, v in self.queue.items():
                if v.state == self.STATE_IDLE:
                    return k
        return -1

    def remove_entries_by_state(self, state: str | None = None) -> None:
        """
        Remove all entries in the queues with the given state (default: FINISHED).
        Blocks add and get_next while running.
        """
        with self.queue_lock:
            if state is None:
                state = self.STATE_FINISHED
            keys_to_remove = [k for k, v in self.queue.items() if v.state == state]
            for k in keys_to_remove:
                self.queue.pop(k, None)
                logging.info(f"Cleanup entry {k}")

    def add(
        self,
        process: Callable,
        callback: Callable,
        params_process: dict,
        params_callback: dict,
    ) -> None:
        with self.queue_lock:
            self.queue_key_counter += 1
            self.queue[self.queue_key_counter] = QueueEntry(
                state=self.STATE_IDLE,
                process=process,
                callback=callback,
                params_process=params_process,
                params_callback=params_callback,
            )
