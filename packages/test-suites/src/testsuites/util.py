import asyncio
from datetime import datetime, timezone
import logging
from typing import Dict, Optional
from pydantic import ValidationError
from s2python.common import EnergyManagementRole

logger = logging.getLogger(__name__)

TIMEOUT = 1


async def wait_for_event_or_stop(
    event: asyncio.Event,
    stop_event: asyncio.Event,
    stop_check_timout: float = TIMEOUT,
    timeout: Optional[int] = None,
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
    time_waited = 0
    while not (event.is_set() or stop_event.is_set()):
        try:
            await asyncio.wait_for(
                asyncio.shield(event.wait()), timeout=stop_check_timout
            )

            if stop_event.is_set():
                logger.debug(f"Stop event set while waiting for {description}.")
                return False  # Indicate stop event was triggered
            logger.debug(f"{description} occurred.")
            return True  # Indicate event was triggered

        except asyncio.TimeoutError:
            if stop_event.is_set():
                logger.info(f"Stop event set while waiting for {description}.")
                return False  # Indicate stop event was triggered

            if timeout is not None and time_waited > timeout:
                logger.info(f"Total timeout reached while waiting for {description}")
                return False  # Indicate stop event was triggered

        except asyncio.CancelledError:
            logger.info(f"Task cancelled while waiting for {description}.")
            return False

        time_waited += stop_check_timout

from zoneinfo import ZoneInfo
# TIMEZONE = timezone.utc
TIMEZONE = ZoneInfo("Europe/Amsterdam")
def current_timezone_time():
    return datetime.now(tz=TIMEZONE)

def pretty_print_pydantic_validation_error(exc : ValidationError):
    pretty = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"])
        msg = err["msg"]
        typ = err["type"]
        pretty.append(f" • {loc} [{typ}]: {msg!r}")
    return "\n".join(pretty)
