"""验证本地 Agent 模型会话只接受纯文本或单个工具调用。"""

import tempfile
import unittest
from pathlib import Path

from max_agent.orchestration.model_session import (
    AgentModelError,
    LocalAgentModelSession,
    parse_model_response,
)
from max_agent.orchestration.models import (
    AgentMessage,
    FinalTextResponse,
    ToolUseResponse,
)


class AgentModelTests(unittest.TestCase):
    def test_plain_text_finishes_and_single_json_calls_tool(self) -> None:
        self.assertEqual(parse_model_response("你好").text, "你好")
        response = parse_model_response(
            '{"type":"tool_use","tool_name":"observe_screen","arguments":{"monitor_index":0}}'
        )
        self.assertIsInstance(response, ToolUseResponse)
        self.assertEqual(response.tool_name, "observe_screen")

    def test_multiple_tools_extra_thought_and_invalid_json_are_rejected(self) -> None:
        invalid = (
            '[{"type":"tool_use","tool_name":"a","arguments":{}},'
            '{"type":"tool_use","tool_name":"b","arguments":{}}]',
            '{"type":"tool_use","tool_name":"a","arguments":{},"thought":"secret"}',
            '{"type":"tool_use","tool_name":"a",}',
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(AgentModelError):
                parse_model_response(value)

    def test_session_allows_one_schema_correction(self) -> None:
        responses = iter(
            (
                '{"type":"tool_use","tool_name":"observe_screen",}',
                '{"type":"tool_use","tool_name":"observe_screen","arguments":{}}',
            )
        )
        calls: list[list[AgentMessage]] = []

        def responder(messages, tools, mode, images):
            calls.append(list(messages))
            return next(responses)

        session = LocalAgentModelSession(Path("."), lambda: "unused", responder)
        result = session.respond([AgentMessage(role="user", content="看屏幕")], [])

        self.assertIsInstance(result, ToolUseResponse)
        self.assertEqual(len(calls), 2)
        self.assertIn("不符合协议", str(calls[1][-1].content))

    def test_second_invalid_response_stops_without_guessing(self) -> None:
        session = LocalAgentModelSession(Path("."), lambda: "unused", lambda *_: "[]")
        with self.assertRaises(AgentModelError) as caught:
            session.respond([AgentMessage(role="user", content="test")], [])
        self.assertEqual(caught.exception.code, "INVALID_MODEL_RESPONSE")

    def test_correction_budget_is_consumed_only_after_invalid_response(self) -> None:
        calls = 0

        def responder(*_):
            nonlocal calls
            calls += 1
            return '{"type":"tool_use","tool_name":"observe_screen",}'

        session = LocalAgentModelSession(Path("."), lambda: "unused", responder)
        with self.assertRaises(AgentModelError) as caught:
            session.respond(
                [AgentMessage(role="user", content="test")],
                [],
                consume_correction=lambda: False,
            )
        self.assertEqual(caught.exception.code, "CORRECTION_BUDGET_EXHAUSTED")
        self.assertEqual(calls, 1)

    def test_fast_context_is_trimmed_without_expanding_tools(self) -> None:
        captured: list[tuple[int, int]] = []

        def responder(messages, tools, mode, images):
            captured.append((len(messages), len(tools)))
            return "完成"

        session = LocalAgentModelSession(Path("."), lambda: "unused", responder)
        messages = [
            AgentMessage(role="user", content=f"m{index}") for index in range(30)
        ]
        tools = [{"name": "observe_screen"}]
        result = session.respond(messages, tools, reasoning_mode="fast")

        self.assertIsInstance(result, FinalTextResponse)
        self.assertEqual(captured, [(12, 1)])

    def test_missing_local_model_returns_model_unavailable_without_network(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            session = LocalAgentModelSession(Path(directory), lambda: "missing")
            with self.assertRaises(AgentModelError) as caught:
                session.respond([AgentMessage(role="user", content="hello")], [])
        self.assertEqual(caught.exception.code, "MODEL_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
