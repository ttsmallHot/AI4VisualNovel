import base64
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from agents.artist_agent import ArtistAgent


class ArtistAgentTests(unittest.TestCase):
    def test_multiple_references_are_sent_in_order_and_never_silently_dropped(self):
        artist = ArtistAgent.__new__(ArtistAgent)
        artist.provider = "openai"
        artist.config = SimpleNamespace(IMAGE_SIZE="1024x1024")
        edit = Mock(return_value=SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(b"image").decode())]))
        artist.client = SimpleNamespace(images=SimpleNamespace(edit=edit))
        with tempfile.TemporaryDirectory() as temp_dir:
            original, neutral = Path(temp_dir) / "original.png", Path(temp_dir) / "neutral.png"
            original.write_bytes(b"original bytes")
            neutral.write_bytes(b"neutral bytes")
            refs = [str(original), str(neutral)]
            context = "Input 1: edit target. Input 2: neutral.png identity and framing reference."
            self.assertEqual(artist._call_image_api("fix angle", refs, reference_context=context), b"image")
            self.assertEqual([item[1] for item in edit.call_args.kwargs["image"]], [b"original bytes", b"neutral bytes"])
            self.assertIn(context, edit.call_args.kwargs["prompt"])
            edit.reset_mock()
            edit.side_effect = RuntimeError("gateway rejected request")
            self.assertIsNone(artist._call_image_api("fix angle", refs, reference_context=context))
            self.assertEqual(edit.call_count, 1)

    def test_openai_edit_decodes_data_url_response(self):
        expected = b"edited-image"
        response = SimpleNamespace(
            data=[SimpleNamespace(b64_json=None, url="data:image/png;base64," + base64.b64encode(expected).decode())]
        )
        artist = ArtistAgent.__new__(ArtistAgent)
        artist.provider = "openai"
        artist.config = SimpleNamespace(IMAGE_SIZE="1024x1024")
        artist.client = SimpleNamespace(images=SimpleNamespace(edit=Mock(return_value=response)))

        with tempfile.TemporaryDirectory() as temp_dir:
            reference = Path(temp_dir) / "reference.png"
            reference.write_bytes(b"reference")
            actual = artist._call_image_api("edit", [str(reference)])

        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
