"""Bounded callback delivery with retries only before submission; never log text, tokens or URLs."""

import asyncio
import random
from collections import Counter
from dataclasses import dataclass
from functools import partial
from typing import Any

import httpx

from .config import Settings
from .native import SerialWorker


@dataclass(frozen=True)
class Delivery:
    status: str
    http_status: int | None = None
    console_status: str = "disabled"
    attempts: int = 0


@dataclass
class PendingDelivery:
    event: dict[str, Any]
    future: asyncio.Future[Delivery]
    attempts: int = 0
    may_have_sent: bool = False


class CallbackDispatcher:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.queue: asyncio.Queue[PendingDelivery] = asyncio.Queue(settings.callback_queue_size)
        self.tasks: list[asyncio.Task[None]] = []
        self.console_lock = asyncio.Lock()
        self.console: SerialWorker | None = None
        self.counts: Counter[str] = Counter()
        self.client = httpx.AsyncClient(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(settings.callback_timeout_seconds),
            limits=httpx.Limits(
                max_connections=settings.callback_workers,
                max_keepalive_connections=settings.callback_workers,
            ),
        )

    def start(self) -> None:
        if self.settings.console_output:
            self.console = SerialWorker("audio-console")
        if self.settings.callback_url or self.settings.console_output:
            self.tasks = [
                asyncio.create_task(self._worker(), name=f"callback-{index}")
                for index in range(self.settings.callback_workers)
            ]

    def submit(self, event: dict[str, Any]) -> asyncio.Future[Delivery]:
        future: asyncio.Future[Delivery] = asyncio.get_running_loop().create_future()
        if not self.settings.callback_url and not self.settings.console_output:
            self._resolve(future, Delivery("not_configured"))
        else:
            try:
                self.queue.put_nowait(PendingDelivery(event, future))
            except asyncio.QueueFull:
                self._resolve(future, Delivery("queue_full"))
        return future

    def _resolve(self, future: asyncio.Future[Delivery], result: Delivery) -> None:
        self.counts[result.status] += 1
        if not future.done():
            future.set_result(result)

    async def _worker(self) -> None:
        while True:
            pending = await self.queue.get()
            console_status = "disabled"
            try:
                if self.settings.console_output:
                    console_status = "unknown"
                    try:
                        async with self.console_lock:
                            assert self.console is not None
                            await asyncio.wait_for(
                                self.console.call(partial(print, pending.event["text"], flush=True)),
                                self.settings.callback_timeout_seconds,
                            )
                        console_status = "printed"
                    except TimeoutError:
                        # A blocked print may finish later. Never replay it or queue
                        # further console writes behind the uncertain operation.
                        assert self.console is not None
                        self.console.stop()
                        console_status = "unknown"
                    except Exception:
                        console_status = "failed"
                if not self.settings.callback_url:
                    self._resolve(pending.future, Delivery("not_configured", console_status=console_status))
                    continue
                result = await self._post(pending, console_status)
                self._resolve(pending.future, result)
            except asyncio.CancelledError:
                self._resolve(
                    pending.future,
                    Delivery(
                        "unknown" if pending.may_have_sent else "not_sent",
                        console_status=console_status,
                        attempts=pending.attempts,
                    ),
                )
                raise
            except Exception:
                # A transport timeout cannot prove the receiver did not accept the POST.
                self._resolve(
                    pending.future,
                    Delivery(
                        "unknown" if pending.may_have_sent else "not_sent",
                        console_status=console_status,
                        attempts=pending.attempts,
                    ),
                )
            finally:
                self.queue.task_done()
                del pending

    async def _post(self, pending: PendingDelivery, console_status: str) -> Delivery:
        assert self.settings.callback_url is not None
        headers = {"Idempotency-Key": pending.event["event_id"]}
        if self.settings.callback_token:
            headers["Authorization"] = "Bearer " + self.settings.callback_token.get_secret_value()
        # The whole delivery, including backoff, shares one deadline.
        async with asyncio.timeout(self.settings.callback_timeout_seconds):
            for attempt in range(self.settings.callback_retry_attempts):
                if attempt:
                    self.counts["retries"] += 1
                pending.attempts += 1
                pending.may_have_sent = True
                response_received = False
                try:
                    # The response body is deliberately not read or logged.
                    async with self.client.stream(
                        "POST",
                        self.settings.callback_url.get_secret_value(),
                        json=pending.event,
                        headers=headers,
                    ) as response:
                        response_received = True
                        return Delivery(
                            "delivered" if 200 <= response.status_code < 300 else "rejected",
                            response.status_code,
                            console_status,
                            pending.attempts,
                        )
                except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
                    if response_received:
                        raise  # Response cleanup errors cannot make an accepted request retryable.
                    # These failures precede sending the POST. Other transport errors are unknown.
                    pending.may_have_sent = False
                    if attempt + 1 == self.settings.callback_retry_attempts:
                        return Delivery("not_sent", console_status=console_status, attempts=pending.attempts)
                    await asyncio.sleep(
                        self.settings.callback_retry_delay_seconds * 2**attempt * random.uniform(0.8, 1.2)
                    )
        raise AssertionError("invalid retry attempts")

    async def stop(self) -> None:
        try:
            async with asyncio.timeout(self.settings.callback_timeout_seconds + 1):
                await self.queue.join()
        except TimeoutError:
            pass
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        while not self.queue.empty():
            pending = self.queue.get_nowait()
            self._resolve(pending.future, Delivery("not_sent"))
            self.queue.task_done()
        if self.console:
            self.console.stop()
        await self.client.aclose()
