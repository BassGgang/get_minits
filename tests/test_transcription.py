import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from transcription import Transcript, TranscriptSegment, save_upload, to_srt, to_txt, transcribe_file


class ExportTests(unittest.TestCase):
    def test_txt_and_srt_preserve_text_and_long_timestamps(self):
        transcript = Transcript(
            [
                TranscriptSegment(0.0, 1.234, "最初の発話"),
                TranscriptSegment(3661.5, 3664.0, "次の発話"),
            ],
            "ja",
            3664.0,
        )
        self.assertEqual(to_txt(transcript), "最初の発話\n次の発話\n")
        self.assertIn("01:01:01,500 --> 01:01:04,000", to_srt(transcript))
        self.assertIn("2\n01:01:01,500", to_srt(transcript))


class TranscribeTests(unittest.TestCase):
    def test_chunk_timestamps_are_relative_to_full_audio(self):
        class FakeModel:
            def transcribe(self, chunk, **kwargs):
                return (
                    [SimpleNamespace(start=1.0, end=2.0, text=" 発話 ")],
                    SimpleNamespace(language="ja"),
                )

        chunks = [(0.0, [0] * 16_000), (300.0, [0] * 16_000)]
        progress = []
        with patch("transcription.get_audio_duration", return_value=301.0), patch(
            "transcription.iter_audio_chunks", return_value=iter(chunks)
        ):
            result = transcribe_file(Path("unused.mp3"), FakeModel(), None, lambda p, d: progress.append((p, d)))
        self.assertEqual([segment.start for segment in result.segments], [1.0, 301.0])
        self.assertEqual(result.language, "ja")
        self.assertEqual(progress[-1], (301.0, 301.0))


class UploadTests(unittest.TestCase):
    def test_upload_accepts_limit_and_cleans_rejected_file(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            original_mkstemp = tempfile.mkstemp

            def make_temp_file(*args, **kwargs):
                return original_mkstemp(*args, dir=temporary_dir, **kwargs)

            with patch("transcription.tempfile.mkstemp", side_effect=make_temp_file):
                path = save_upload(io.BytesIO(b"abc"), max_bytes=3)
                self.assertEqual(path.read_bytes(), b"abc")
                path.unlink()
                with self.assertRaises(ValueError):
                    save_upload(io.BytesIO(b"abcd"), max_bytes=3)
            self.assertEqual(list(Path(temporary_dir).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
