import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agents.config import APIConfig
from agents.llm_client import LLMClient


class FakeCompletions:
    def __init__(self, contents, finish_reasons=None):
        self.contents = iter(contents)
        self.finish_reasons = iter(finish_reasons or ["stop"] * len(contents))
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = SimpleNamespace(content=next(self.contents))
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=message,
                    finish_reason=next(self.finish_reasons),
                )
            ]
        )


class LLMClientTests(unittest.TestCase):
    def make_client(self, contents, finish_reasons=None):
        client = LLMClient.__new__(LLMClient)
        client.provider = "openai"
        client.base_url = "https://api.deepseek.com"
        completions = FakeCompletions(contents, finish_reasons)
        client.client = SimpleNamespace(
            chat=SimpleNamespace(completions=completions),
        )
        return client, completions

    def test_deepseek_v4_disables_thinking_for_structured_output(self):
        client, completions = self.make_client(['{"ok": true}'])

        with patch.object(APIConfig, "MODEL", "deepseek-v4-flash"), patch.dict(
            os.environ,
            {"DEEPSEEK_THINKING": "disabled", "JSON_MAX_TOKENS": "8192"},
        ):
            result = client._chat_openai(
                [{"role": "user", "content": "json"}],
                temperature=0.2,
                json_mode=True,
            )

        self.assertEqual(result, '{"ok": true}')
        self.assertEqual(
            completions.calls[0]["extra_body"],
            {"thinking": {"type": "disabled"}},
        )
        self.assertEqual(completions.calls[0]["max_tokens"], 8192)

    def test_empty_content_is_rejected(self):
        client, _ = self.make_client([""])

        with patch.object(APIConfig, "MODEL", "deepseek-v4-flash"):
            with self.assertRaisesRegex(ValueError, "空正文"):
                client._chat_openai(
                    [{"role": "user", "content": "json"}],
                    temperature=0.2,
                    json_mode=True,
                )

    def test_length_truncated_response_is_rejected(self):
        client, _ = self.make_client(["{\"partial\":"], ["length"])

        with patch.object(APIConfig, "MODEL", "deepseek-v4-flash"):
            with self.assertRaisesRegex(ValueError, "被截断"):
                client._chat_openai(
                    [{"role": "user", "content": "json"}],
                    temperature=0.2,
                    json_mode=True,
                )


if __name__ == "__main__":
    unittest.main()
