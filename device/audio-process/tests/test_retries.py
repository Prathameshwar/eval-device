import asyncio
import errno
import json
import time

import httpx
import pytest
from conftest import SPEECH
from pydantic import SecretStr
from test_recording import finalized, make_record, read_audio, recording_settings

from device_audio.delivery import CallbackDispatcher
from device_audio.recording import Recorder
from device_audio.retries import RetryingFile

# Reuse the isolated recording fixture; each test has a distinct private directory.
__all__ = ["recording_settings"]


async def test_partial_raw_write_is_replayed_at_same_offset_without_duplicates(
    recording_settings, monkeypatch
):
    original = RetryingFile._write_once
    faults = []

    def partial_then_error(target, data):
        if str(target.name).endswith("audio.wav") and len(data) > 100 and not faults:
            faults.append(True)
            original(target, data[:37])
            raise BlockingIOError(errno.EAGAIN, "temporary disk busy")
        # Exercise short successful writes too.
        return original(target, data[:211])

    monkeypatch.setattr(RetryingFile, "_write_once", partial_then_error)
    recorder = Recorder(recording_settings)
    await recorder.start()
    record = make_record(recorder)
    pcm = SPEECH * 20
    recorder.audio(record, pcm)
    recorder.transcript(record, {"text": "\u0928\u092e\u0938\u094d\u0924\u0947 hello"})
    recorder.finish(record)
    try:
        receipt = await finalized(record)
        assert receipt["status"] == "saved"
        assert receipt["audio_complete"] and receipt["transcript_complete"]
        assert receipt["fallback"] == "none"
        assert read_audio(recording_settings.recording_dir / receipt["id"] / "audio.wav") == pcm
        assert recorder.status()["retry_count"] == 1
        assert recorder.disk.store.records[receipt["id"]]["audio_bytes"] == len(pcm)
    finally:
        await recorder.stop()


@pytest.mark.parametrize("error,expected_calls", [(errno.EAGAIN, 3), (errno.EACCES, 1), (errno.ENOSPC, 1)])
async def test_failed_audio_falls_back_to_text_and_retry_count_is_bounded(
    recording_settings, monkeypatch, error, expected_calls
):
    original = RetryingFile._write_once
    calls = []

    def fail_audio(target, data):
        if str(target.name).endswith("audio.wav"):
            calls.append(True)
            # A partial write before the failure must not be retried by a later close.
            original(target, data[:17])
            raise OSError(error, "private path must not be logged")
        return original(target, data)

    monkeypatch.setattr(RetryingFile, "_write_once", fail_audio)
    recorder = Recorder(recording_settings)
    await recorder.start()
    record = make_record(recorder)
    recorder.audio(record, SPEECH * 8)
    event = {"text": "\u0928\u092e\u0938\u094d\u0924\u0947 hello"}
    recorder.transcript(record, event)
    recorder.finish(record)
    try:
        receipt = await finalized(record)
        assert receipt["status"] == "incomplete"
        assert receipt["fallback"] == "transcript_only"
        assert not receipt["audio_complete"] and receipt["transcript_complete"]
        assert len(calls) == expected_calls
        assert recorder.status()["retry_count"] == expected_calls - 1
        directory = recording_settings.recording_dir / receipt["id"]
        assert json.loads((directory / "transcript.jsonl").read_text(encoding="utf-8")) == event
        assert (directory / "audio.wav").stat().st_size == 17
    finally:
        await recorder.stop()
    restarted = Recorder(recording_settings)
    await restarted.start()
    try:
        assert restarted.available
        receipt = restarted.lookup(record.data["id"], "pi-1")
        assert receipt["status"] == "incomplete"
        assert receipt["transcript_complete"] and receipt["fallback"] == "transcript_only"
    finally:
        await restarted.stop()


async def test_text_failure_preserves_complete_audio(recording_settings, monkeypatch):
    original = RetryingFile._write_once

    def fail_text(target, data):
        if str(target.name).endswith("transcript.jsonl"):
            raise PermissionError(errno.EACCES, "private")
        return original(target, data)

    monkeypatch.setattr(RetryingFile, "_write_once", fail_text)
    recorder = Recorder(recording_settings)
    await recorder.start()
    record = make_record(recorder)
    pcm = SPEECH * 6
    recorder.audio(record, pcm)
    recorder.transcript(record, {"text": "hello"})
    recorder.finish(record)
    try:
        receipt = await finalized(record)
        assert receipt["status"] == "incomplete" and receipt["fallback"] == "audio_only"
        assert receipt["audio_complete"] and not receipt["transcript_complete"]
        assert read_audio(recording_settings.recording_dir / receipt["id"] / "audio.wav") == pcm
    finally:
        await recorder.stop()


async def test_audio_quota_failure_still_saves_text_when_it_fits(recording_settings):
    recording_settings.recording_max_bytes = 32768
    recorder = Recorder(recording_settings)
    await recorder.start()
    record = make_record(recorder)
    recorder.audio(record, SPEECH * 40)
    await recorder.queue.join()
    recorder.transcript(record, {"text": "keep the transcript"})
    recorder.finish(record)
    try:
        receipt = await finalized(record)
        assert receipt["status"] == "incomplete" and receipt["reason"] == "storage_limit"
        assert receipt["fallback"] == "transcript_only" and receipt["transcripts"] == 1
        assert recorder.status()["retry_count"] == 0
        assert recorder.disk.store.used <= recording_settings.recording_max_bytes
    finally:
        await recorder.stop()


async def test_queue_overflow_still_admits_text_after_capacity_returns(recording_settings):
    recording_settings.recording_queue_items = 4
    recorder = Recorder(recording_settings)
    await recorder.start()
    record = make_record(recorder)
    # Begin plus three audio entries fit; later audio stops but the admitted prefix drains.
    for _ in range(10):
        recorder.audio(record, SPEECH)
    receipt = recorder.lookup(record.data["id"], "pi-1")
    assert receipt["status"] == "incomplete" and not receipt["finalized"]
    await recorder.queue.join()
    recorder.transcript(record, {"text": "kept after audio overload"})
    recorder.finish(record)
    try:
        receipt = await finalized(record)
        assert receipt["reason"] == "recording_queue_full" and receipt["finalized"]
        assert receipt["fallback"] == "transcript_only"
        assert receipt["transcript_complete"] and receipt["transcripts"] == 1
        assert read_audio(recording_settings.recording_dir / receipt["id"] / "audio.wav") == SPEECH * 3
    finally:
        await recorder.stop()


@pytest.mark.parametrize("failure", ["sync", "manifest_after_replace"])
async def test_idempotent_finalization_retries_safely(recording_settings, monkeypatch, failure):
    recorder = Recorder(recording_settings)
    await recorder.start()
    record = make_record(recorder)
    recorder.audio(record, SPEECH * 4)
    recorder.transcript(record, {"text": "exactly once"})
    await recorder.queue.join()
    store = recorder.disk.store
    faults = []
    if failure == "sync":
        import os

        original = os.fsync

        def fail_once(fd):
            if not faults:
                faults.append(True)
                raise BlockingIOError(errno.EAGAIN, "busy")
            return original(fd)

        monkeypatch.setattr("device_audio.recording_store.os.fsync", fail_once)
    else:
        original = store._manifest_once

        def replace_then_error(directory, data):
            original(directory, data)
            if data["status"] == "saved" and not faults:
                faults.append(True)
                raise BlockingIOError(errno.EAGAIN, "completed before transient exception")

        monkeypatch.setattr(store, "_manifest_once", replace_then_error)
    recorder.finish(record)
    try:
        receipt = await finalized(record)
        assert receipt["status"] == "saved" and receipt["transcripts"] == 1
        directory = recording_settings.recording_dir / receipt["id"]
        assert read_audio(directory / "audio.wav") == SPEECH * 4
        assert len((directory / "transcript.jsonl").read_text().splitlines()) == 1
        assert recorder.status()["retry_count"] == 1
    finally:
        await recorder.stop()


@pytest.mark.parametrize("exception", [httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout])
async def test_callback_retries_only_before_send_with_same_id_and_one_console_print(
    settings, exception, capsys
):
    settings.callback_url = SecretStr("http://127.0.0.1/result")
    settings.console_output = True
    settings.callback_retry_delay_seconds = 0.01
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) < 3:
            raise exception("private URL or credential")
        return httpx.Response(204)

    dispatcher = CallbackDispatcher(settings, httpx.MockTransport(handler))
    dispatcher.start()
    event = {"event_id": "same-server-id", "text": "print once"}
    try:
        result = await dispatcher.submit(event)
        assert result.status == "delivered" and result.attempts == 3
        assert dispatcher.counts["retries"] == 2
        assert len({r.headers["Idempotency-Key"] for r in requests}) == 1
        assert all(json.loads(r.content) == event for r in requests)
        assert capsys.readouterr().out.count("print once") == 1
    finally:
        await dispatcher.stop()


@pytest.mark.parametrize(
    "failure",
    [httpx.ReadTimeout, httpx.WriteTimeout, httpx.WriteError, httpx.RemoteProtocolError, 429, 500, 503],
)
async def test_unknown_or_rejected_posts_are_not_replayed(settings, failure):
    settings.callback_url = SecretStr("http://127.0.0.1/result")
    settings.console_output = False
    requests = []

    def handler(request):
        requests.append(request)
        if isinstance(failure, int):
            return httpx.Response(failure)
        raise failure("unknown outcome")

    dispatcher = CallbackDispatcher(settings, httpx.MockTransport(handler))
    dispatcher.start()
    try:
        result = await dispatcher.submit({"event_id": "id", "text": "private"})
        assert result.status == ("rejected" if isinstance(failure, int) else "unknown")
        assert result.attempts == 1 and len(requests) == 1
        assert dispatcher.counts["retries"] == 0
    finally:
        await dispatcher.stop()


@pytest.mark.parametrize("deadline", [False, True])
async def test_callback_retry_exhaustion_and_total_deadline_report_not_sent(settings, deadline):
    settings.callback_url = SecretStr("http://127.0.0.1/result")
    settings.console_output = False
    settings.callback_retry_delay_seconds = 0.2 if deadline else 0.01
    settings.callback_timeout_seconds = 0.1 if deadline else 2
    requests = []

    def handler(request):
        requests.append(request)
        raise httpx.ConnectError("not connected")

    dispatcher = CallbackDispatcher(settings, httpx.MockTransport(handler))
    dispatcher.start()
    started = time.monotonic()
    try:
        result = await dispatcher.submit({"event_id": "id", "text": "private"})
        assert result.status == "not_sent"
        assert result.attempts == len(requests) == (1 if deadline else 3)
        assert time.monotonic() - started < 1
    finally:
        await dispatcher.stop()


async def test_callback_response_cleanup_error_cannot_trigger_duplicate_post(settings):
    settings.callback_url = SecretStr("http://127.0.0.1/result")
    settings.console_output = False
    calls = []

    class ResponseStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b""

        async def aclose(self):
            raise httpx.ConnectError("error after server already accepted the POST")

    def handler(request):
        calls.append(request)
        return httpx.Response(204, stream=ResponseStream())

    dispatcher = CallbackDispatcher(settings, httpx.MockTransport(handler))
    dispatcher.start()
    try:
        result = await dispatcher.submit({"event_id": "id", "text": "private"})
        assert result.status == "unknown" and result.attempts == 1
        assert len(calls) == 1
    finally:
        await dispatcher.stop()


async def test_transient_file_creation_retries_without_overwriting_existing_files(
    recording_settings, monkeypatch
):
    import device_audio.recording_store as module

    original = module.RetryingFile
    calls = []

    def unavailable_once(path, retry):
        if str(path).endswith("audio.wav") and not calls:
            calls.append(True)
            raise BlockingIOError(errno.EAGAIN, "temporary sharing failure")
        return original(path, retry)

    monkeypatch.setattr(module, "RetryingFile", unavailable_once)
    recorder = Recorder(recording_settings)
    await recorder.start()
    record = make_record(recorder)
    recorder.audio(record, SPEECH)
    recorder.finish(record)
    try:
        result = await finalized(record)
        assert result["status"] == "saved"
        assert recorder.status()["retry_count"] == 1
        assert read_audio(recording_settings.recording_dir / result["id"] / "audio.wav") == SPEECH
    finally:
        await recorder.stop()


async def test_periodic_audio_flush_failure_keeps_later_text_recording(recording_settings, monkeypatch):
    recording_settings.recording_flush_seconds = 0.05
    original = RetryingFile._write_once

    def fail_audio(target, data):
        if str(target.name).endswith("audio.wav"):
            raise PermissionError(errno.EACCES, "private")
        return original(target, data)

    monkeypatch.setattr(RetryingFile, "_write_once", fail_audio)
    recorder = Recorder(recording_settings)
    await recorder.start()
    record = make_record(recorder)
    recorder.audio(record, SPEECH * 3)
    try:
        async with asyncio.timeout(3):
            while record.data["fallback"] != "transcript_only":
                await asyncio.sleep(0.01)
        assert not record.snapshot()["finalized"]
        recorder.transcript(record, {"text": "first after audio failure"})
        await recorder.queue.join()
        recorder.transcript(record, {"text": "second after audio failure"})
        recorder.finish(record)
        result = await finalized(record)
        assert result["finalized"] and result["status"] == "incomplete"
        assert result["fallback"] == "transcript_only" and result["transcript_complete"]
        path = recording_settings.recording_dir / result["id"] / "transcript.jsonl"
        assert [json.loads(line)["text"] for line in path.read_text().splitlines()] == [
            "first after audio failure",
            "second after audio failure",
        ]
    finally:
        recorder.finish(record)
        await recorder.stop()


async def test_idle_recorder_shutdown_wakes_worker_before_long_flush_interval(recording_settings):
    recording_settings.recording_flush_seconds = 10
    recording_settings.recording_shutdown_seconds = 2
    recorder = Recorder(recording_settings)
    await recorder.start()
    record = make_record(recorder)
    recorder.finish(record)
    await finalized(record)
    await asyncio.sleep(0.01)
    try:
        await asyncio.wait_for(recorder.stop(), 1)
        assert recorder.disk.closed.is_set()
    finally:
        if not recorder.disk.closed.is_set():
            recorder.disk.stop()
