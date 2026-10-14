import unittest

from agents.base_agent import BaseAgent


class StubLLM:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def chat_completion(self, **kwargs):
        self.calls += 1
        return next(self.responses)


class BaseAgentTests(unittest.TestCase):
    def test_single_object_schema_accepts_singleton_array(self):
        agent = BaseAgent.__new__(BaseAgent)
        agent.llm_client = StubLLM(['[{"value": "ok"}]'])
        schema = {
            "type": "object",
            "required": ["value"],
            "additionalProperties": False,
            "properties": {"value": {"type": "string"}},
        }

        result = agent.call_json_with_schema(
            messages=[{"role": "user", "content": "return json"}],
            schema=schema,
            object_name="test_object",
        )

        self.assertEqual(result, {"value": "ok"})
        self.assertEqual(agent.llm_client.calls, 1)

    def test_json_parse_failure_uses_schema_retry(self):
        agent = BaseAgent.__new__(BaseAgent)
        agent.llm_client = StubLLM(['{"value": "bad\nvalue"}', '{"value": "ok"}'])
        schema = {
            "type": "object",
            "required": ["value"],
            "additionalProperties": False,
            "properties": {"value": {"type": "string"}},
        }

        result = agent.call_json_with_schema(
            messages=[{"role": "user", "content": "return json"}],
            schema=schema,
            object_name="test_object",
        )

        self.assertEqual(result, {"value": "ok"})
        self.assertEqual(agent.llm_client.calls, 2)


if __name__ == "__main__":
    unittest.main()
