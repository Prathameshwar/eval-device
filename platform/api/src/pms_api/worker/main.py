import argparse
import asyncio
import logging

from pms_api.core.config import Settings
from pms_api.database.session import check_schema, engine_for, sessions_for
from pms_api.worker.service import Worker, retain


async def run(settings, once=False, retention=False):
    engine = engine_for(settings, "retention" if retention else "worker")
    sessions = sessions_for(engine)
    try:
        async with sessions() as session:
            if not await check_schema(session):
                raise RuntimeError("Apply migrations before starting workers")
        worker = Worker(settings, sessions)

        async def loop():
            while True:
                try:
                    if retention:
                        await retain(sessions)
                    else:
                        await worker.tick()
                except Exception as error:
                    logging.getLogger(__name__).error(
                        "worker_tick_failed", extra={"error_type": type(error).__name__}
                    )
                    if once:
                        raise
                if once:
                    return
                await asyncio.sleep(60 if retention else settings.worker_poll_seconds)

        await asyncio.gather(*(loop() for _ in range(1 if retention else settings.worker_concurrency)))
    finally:
        if "worker" in locals():
            await worker.storage.close()
        await engine.dispose()


def main():
    from pms_api.cli import configure_event_loop

    configure_event_loop()
    parser = argparse.ArgumentParser(description="Durable PMS processing/retention worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--retention", action="store_true")
    args = parser.parse_args()
    from pms_api.core.logging import configure_logging

    configure_logging()
    asyncio.run(run(Settings(), args.once, args.retention))


if __name__ == "__main__":
    main()
