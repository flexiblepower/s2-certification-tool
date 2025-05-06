import asyncio

import logging
from typing import Coroutine, Set

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

    _tasks: Set[asyncio.Task] = set()

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
        task_name = getattr(task, '__name__', str(task))
        try:
            await task
            if stop_on_complete:
                logger.debug("Task execution complete. Stopping. %s", task_name)
                await self.stop()
        except asyncio.CancelledError:
            logger.info("Task %s was cancelled.", task_name)
        except:
            logger.exception("Exception in task %s!", task_name)
            await self.stop()

    def create_task(self, task: Coroutine, stop_on_complete=False):
        self._tasks.add(asyncio.create_task(self.task_wrapper(task, stop_on_complete)))

    async def setup(self, *args, **kwargs):
        self._stop_event = asyncio.Event()

    async def cleanup(self, *args, **kwargs):
        logger.info("Cleanup of %s", self.__class__.__name__)
        for task in self._tasks:
            task.cancel()

        await asyncio.gather(*self._tasks)

        self._tasks.clear()

    async def stop(self):
        logger.debug("Stop Called in class %s", self.__class__.__name__)
        self._stop_event.set()

    def is_running(self):
        return self.running
