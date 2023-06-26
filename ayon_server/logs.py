import asyncio
import queue
import time
from typing import Any

from ayon_server.background import BackgroundTask

# Fallback to the default logging module
# This is just used when ayon_server is loaded in order
# to get the version number.

try:
    from nxtools import logging

    has_nxtools = True
except ModuleNotFoundError:
    import logging

    has_nxtools = False

else:
    from ayon_server.events import dispatch_event


def parse_log_message(message):
    """Convert nxtools log message to event system message."""
    topic = {
        0: "log.debug",
        1: "log.info",
        2: "log.warning",
        3: "log.error",
        4: "log.success",
    }[message["message_type"]]

    description = message["message"].splitlines()[0]
    if len(description) > 100:
        description = description[:100] + "..."

    payload = {
        "message": message["message"],
    }

    return {
        "topic": topic,
        "description": description,
        "payload": payload,
    }


class LogCollector(BackgroundTask):
    def initialize(self):
        self.queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.msg_id = 0
        self.start_time = time.time()

    def __call__(self, **kwargs):
        # We need to add messages to the queue even if the
        # collector is not running to catch the messages
        # that are logged during the startup.
        if len(self.queue.queue) > 1000:
            logging.warning("Log collector queue is full", handlers=None)
            return
        self.queue.put(kwargs)

    async def process_message(self, record):
        self.msg_id += 1
        try:
            message = parse_log_message(record)
            await dispatch_event(
                message["topic"],
                # user=None, (TODO: implement this?)
                description=message["description"],
                payload=message["payload"],
            )
        except Exception:
            # This actually should not happen, but if it does,
            # we don't want to crash the whole application and
            # we don't want to log the exception using the logger,
            # since it failed in the first place.
            logging.error(
                "Unable to dispatch log message",
                message["description"],
                handlers=None,
            )

    async def run(self):
        # During the startup, we cannot write to the database
        # so the following loop patiently waits for the database
        # to be ready.
        while True:
            try:
                await dispatch_event("server.log_collector_started")
            except Exception:
                # Do not log the exception using the logger,
                # if you don't like recursion.
                await asyncio.sleep(0.5)
                continue
            break

        while True:
            if self.queue.empty():
                await asyncio.sleep(0.1)
                continue

            record = self.queue.get()
            await self.process_message(record)

    async def finalize(self):
        while not self.queue.empty():
            logging.debug(
                f"Processing {len(self.queue.queue)} remaining log messages",
                handlers=None,
            )
            record = self.queue.get()
            await self.process_message(record)


if has_nxtools:
    log_collector = LogCollector()
    logging.add_handler(log_collector)
    logging.info("Log collector initialized", handlers=None)
