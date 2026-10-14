import copy
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from dashboard import server


GRAPH = {
    "version": 3,
    "nodes": {
        "root": {"id": "root", "summary": "开始", "type": "normal", "custom": 42},
        "node1": {"id": "node1", "summary": "结束", "type": "normal"},
    },
    "edges": [{"from": "root", "to": "node1", "choice_text": None, "custom": True}],
}


class DashboardGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "demo"
        self.root.mkdir()
        server.write_json_atomic(self.root / "story_graph.json", GRAPH)
        server.write_json_atomic(self.root / "game_design.json", {"title": "保留", "story_graph": GRAPH})
        (self.root / "story.txt").write_text("=== Node: node1 ===\n保留原剧本", encoding="utf-8")
        self.revision = server.graph_revision(self.root)

    def test_save_syncs_design_preserves_metadata_and_backs_up(self):
        graph = copy.deepcopy(GRAPH)
        graph["nodes"]["node1"]["summary"] = "改写计划"
        result = server.save_story_graph(self.root, graph, self.revision)
        self.assertNotEqual(result["graph_revision"], self.revision)
        design = server.read_json(self.root / "game_design.json")
        self.assertEqual(design, {"title": "保留", "story_graph": graph})
        self.assertEqual(server.read_json(self.root / "story_graph.json"), graph)
        self.assertEqual(server.read_json(self.root / result["backup"] / "story_graph.json"), GRAPH)
        self.assertIn("保留原剧本", server.read_text(self.root / "story.txt"))

    def test_delete_keeps_script(self):
        graph = copy.deepcopy(GRAPH)
        del graph["nodes"]["node1"]
        graph["edges"] = []
        before = (self.root / "story.txt").read_bytes()
        server.save_story_graph(self.root, graph, self.revision)
        self.assertEqual(before, (self.root / "story.txt").read_bytes())

    def test_rejects_stale_or_missing_revision(self):
        for revision in (None, "old"):
            with self.assertRaises(RuntimeError):
                server.save_story_graph(self.root, GRAPH, revision)
        server.write_json_atomic(self.root / "game_design.json", {"title": "外部更新"})
        with self.assertRaises(RuntimeError):
            server.save_story_graph(self.root, GRAPH, self.revision)
        self.assertFalse((self.root / ".ai4vn").exists())

    def test_invalid_graphs_do_not_write(self):
        invalid = []
        def variant():
            graph = copy.deepcopy(GRAPH)
            invalid.append(graph)
            return graph
        variant()["nodes"].pop("root")
        variant()["nodes"]["root"]["id"] = "other"
        variant()["nodes"]["root"]["type"] = "bad"
        variant()["nodes"]["root"]["summary"] = " "
        variant()["edges"][0]["to"] = "missing"
        variant()["edges"][0]["to"] = "root"
        variant()["edges"].append(copy.deepcopy(GRAPH["edges"][0]))
        variant()["edges"].append({"from": "node1", "to": "root"})
        variant()["edges"] = []
        graph = variant()
        graph["nodes"]["node2"] = {"id": "node2", "summary": "分支", "type": "normal"}
        graph["edges"].append({"from": "root", "to": "node2", "choice_text": "新选项"})
        for graph in invalid:
            with self.subTest(graph=graph), self.assertRaises(ValueError):
                server.save_story_graph(self.root, graph, self.revision)
            self.assertEqual(server.graph_revision(self.root), self.revision)
        self.assertFalse((self.root / ".ai4vn").exists())

    def test_write_failure_rolls_back(self):
        original_write = server.write_json_atomic
        def fail_design(path, data):
            if path.name == "game_design.json":
                raise OSError("test failure")
            original_write(path, data)
        graph = copy.deepcopy(GRAPH)
        graph["nodes"]["root"]["summary"] = "新"
        with patch.object(server, "write_json_atomic", side_effect=fail_design), self.assertRaises(OSError):
            server.save_story_graph(self.root, graph, self.revision)
        self.assertEqual(server.graph_revision(self.root), self.revision)

    def test_busy_project_rejected(self):
        with patch.object(server, "JOBS", {"job": {"name": "demo", "status": "running"}}), self.assertRaises(RuntimeError):
            server.save_story_graph(self.root, GRAPH, self.revision)

    def test_empty_project_does_not_create_design(self):
        root = self.root / "empty"
        root.mkdir()
        server.save_story_graph(root, GRAPH, server.graph_revision(root))
        self.assertTrue((root / "story_graph.json").exists())
        self.assertFalse((root / "game_design.json").exists())

    def test_http_get_and_post_conflict(self):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.DashboardHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        with patch.object(server, "PROJECTS_ROOT", self.root.parent), patch.object(server, "INCLUDE_LEGACY", False):
            thread.start()
            try:
                url = f"http://127.0.0.1:{httpd.server_port}"
                with urlopen(url + "/api/project?project=demo") as response:
                    data = json.load(response)
                graph = copy.deepcopy(GRAPH)
                graph["nodes"]["root"]["summary"] = "HTTP 修改"
                payload = json.dumps({"project": "demo", "graph": graph, "revision": data["graph_revision"]}).encode()
                request = Request(url + "/api/graph", data=payload, headers={"Content-Type": "application/json"})
                with urlopen(request) as response:
                    self.assertTrue(json.load(response)["ok"])
                with self.assertRaises(HTTPError) as error:
                    urlopen(request)
                self.assertEqual(error.exception.code, 409)
            finally:
                httpd.shutdown()
                thread.join()
                httpd.server_close()
