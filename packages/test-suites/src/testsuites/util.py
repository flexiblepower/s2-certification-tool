import asyncio
from datetime import datetime, timezone
import logging
from typing import Dict

logger = logging.getLogger(__name__)

TIMEOUT = 1


async def wait_for_event_or_stop(
    event: asyncio.Event,
    stop_event: asyncio.Event,
    timeout: float = TIMEOUT,
    description: str = "Event",
):
    """Waits for either the event or the stop event to be set.


    Args:
        event (asyncio.Event): Event to wait for.
        stop_event (asyncio.Event): Stop event to wait for.
        timeout (float): Timeout between stop checks
        description (str, optional): Description for logging purposes.

    Returns:
        bool: If event is set then returns True. If return due to exit event then False.
    """
    while not (event.is_set() or stop_event.is_set()):
        try:
            await asyncio.wait_for(asyncio.shield(event.wait()), timeout=timeout)

            if stop_event.is_set():
                logger.debug(f"Stop event set while waiting for {description}.")
                return False  # Indicate stop event was triggered
            logger.debug(f"{description} occurred.")
            return True  # Indicate event was triggered

        except asyncio.TimeoutError:
            if stop_event.is_set():
                logger.info(f"Stop event set while waiting for {description}.")
                return False  # Indicate stop event was triggered

        except asyncio.CancelledError:
            logger.info(f"Task cancelled while waiting for {description}.")
            return False


def current_timezone_time():
    return datetime.now(tz=timezone.utc)
