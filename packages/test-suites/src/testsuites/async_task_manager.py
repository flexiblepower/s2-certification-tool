import asyncio

import logging
from typing import Coroutine

logger = logging.getLogger(__name__)


class AsyncTaskManager:
    """Manages a collection of asyncio tasks, providing methods for task creation, cleanup, and stopping.

    This class helps to manage the lifecycle of asynchronous tasks, ensuring
    exceptions are caught and logged, and providing a mechanism to stop all
    running tasks.

    Attributes:
        _tasks (set): A set containing the asyncio task objects being managed.
        _stop_event (asyncio.Event): An event used to signal that tasks should stop.
        running (bool): Indicates whether the task manager is currently considered
                        to be running.

    """

    _tasks = set()

    _stop_event: asyncio.Event

    running = False

    def __init__(
        self,
    ):
        self._stop_event = asyncio.Event()

    async def task_wrapper(self, task: Coroutine, stop_on_complete):
        """Uncaught exceptions don't get logged reliably in tasks. This catches all exceptions to log them and kill the controller.

        TODO: Maybe handle the exceptions in a better way...
        """
        try:
            await task
            if stop_on_complete:
                logger.debug("Task execution complete. Stopping.")
                await self.stop()
        except:
            logger.exception("Exception in task!")
            await self.stop()

    def create_task(self, task: Coroutine, stop_on_complete=False):
        self._tasks.add(asyncio.create_task(self.task_wrapper(task, stop_on_complete)))

    async def setup(self):
        self._stop_event = asyncio.Event()

    async def cleanup(self):
        for task in self._tasks:
            task.cancel()

        await asyncio.gather(*self._tasks)

        self._tasks.clear()

    async def stop(self):
        self._stop_event.set()

    def is_running(self):
        return self.running
