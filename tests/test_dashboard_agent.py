import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dashboard.server as server


class FakeProcess:
    def __init__(self, command, **kwargs):
        self.command = command
        self.pid = 12345
        self.stdout = iter(
            [
                json.dumps({"type": "thread.started", "thread_id": "thread-123"}) + "\n",
                json.dumps({"type": "turn.started"}) + "\n",
                json.dumps(
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "已完成项目检查。"},
                    }
                )
                + "\n",
            ]
        )

    def wait(self):
        return 0

    def poll(self):
        return None


class DashboardAgentTests(unittest.TestCase):
    def tearDown(self):
        server.AGENT_ACTIVE.clear()
        server.AGENT_PROCESSES.clear()

    def test_agent_event_extracts_session_and_reply(self):
        thread_id, message, activity = server.agent_event(
            {"type": "thread.started", "thread_id": "abc"}
        )
        self.assertEqual(thread_id, "abc")
        self.assertIsNone(message)
        self.assertIsNone(activity)

        _, message, _ = server.agent_event(
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "完成"},
            }
        )
        self.assertEqual(message, "完成")

    def test_agent_state_is_persisted_under_ai4vn(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state = server.default_agent_state()
            state["messages"].append({"role": "user", "text": "生成故事"})
            server.save_agent_state(root, state)

            path = root / ".ai4vn" / "agent" / "session.json"
            self.assertTrue(path.exists())
            self.assertEqual(server.load_agent_state(root)["messages"][0]["text"], "生成故事")

    def test_run_agent_captures_thread_and_assistant_reply(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            state = server.default_agent_state()
            state["status"] = "running"
            state["messages"] = [{"role": "user", "text": "检查项目"}]
            server.save_agent_state(root, state)
            server.AGENT_ACTIVE.add(str(root.resolve()))

            with patch.object(server, "codex_command", return_value="/usr/bin/codex"), patch.object(
                server.subprocess, "Popen", side_effect=FakeProcess
            ) as popen:
                server.run_agent("demo", root, "检查项目", "job-1")

            command = popen.call_args.args[0]
            self.assertIn("--sandbox", command)
            self.assertIn("workspace-write", command)
            self.assertIn("sandbox_workspace_write.network_access=true", command)
            saved = server.load_agent_state(root)
            self.assertEqual(saved["thread_id"], "thread-123")
            self.assertEqual(saved["status"], "completed")
            self.assertEqual(saved["messages"][-1]["text"], "已完成项目检查。")

    def test_follow_up_resumes_the_same_thread(self):
        command = server.codex_agent_command(
            "/usr/bin/codex", Path("/tmp/project"), "thread-123", "继续修改"
        )
        self.assertEqual(command[:3], ["/usr/bin/codex", "exec", "resume"])
        self.assertIn("thread-123", command)
        self.assertNotIn("-C", command)


if __name__ == "__main__":
    unittest.main()
