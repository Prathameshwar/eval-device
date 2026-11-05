"""Exercise evidence hooks against HTTP mocks without opening the desktop or cloud."""

import unittest
from types import SimpleNamespace

import httpx
from human_test.config import Settings
from run_interview import Interview, turn_timeout_seconds


class ObserverTests(unittest.IsolatedAsyncioTestCase):
    def test_turn_deadline_allows_all_speech_rounds_and_response_retries(self):
        settings = Settings(_env_file=None)
        minimum = 51 * settings.timeout_seconds + 177
        minimum += 6 * settings.timeout_seconds + 15
        minimum += settings.max_question_seconds
        self.assertGreater(turn_timeout_seconds(settings), minimum)
        settings.speech_retry_rounds = 1
        self.assertLess(turn_timeout_seconds(settings), minimum)

    async def test_admission_error_keeps_code_and_success_stream_is_not_consumed(self):
        def handler(request):
            return httpx.Response(
                429,
                json={
                    "error": {
                        "code": "llm_daily_limit",
                        "message": "do not save this body",
                    }
                },
            )

        async with httpx.AsyncClient(
            base_url="http://test.invalid", transport=httpx.MockTransport(handler)
        ) as client:
            interview = Interview.__new__(Interview)
            interview.current = {"attempts": []}
            interview.window = SimpleNamespace(
                controller=SimpleNamespace(pms=SimpleNamespace(http=client))
            )
            await interview.install_http_observers()
            response = await client.post(
                "/llm/completions", json={"request_key": "fixture"}
            )
            self.assertEqual(response.json()["error"]["code"], "llm_daily_limit")
            attempt = interview.current["attempts"][0]
            self.assertEqual(attempt["error_code"], "llm_daily_limit")
            self.assertNotIn("do not save this body", str(attempt))

        class Stream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'data: {"type":"done"}\n\n'

        async with httpx.AsyncClient(
            base_url="http://test.invalid",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, stream=Stream())
            ),
        ) as client:
            interview.window.controller.pms.http = client
            await interview.install_http_observers()
            async with client.stream(
                "POST", "/llm/completions", json={"request_key": "stream"}
            ) as response:
                self.assertFalse(response.is_stream_consumed)


if __name__ == "__main__":
    unittest.main()
