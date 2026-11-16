"""Audio decoding and local transcription for the Streamlit app."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Callable, Iterator

SAMPLE_RATE = 16_000
CHUNK_SECONDS = 5 * 60
CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_SECONDS
MAX_FILE_BYTES = 1_073_741_824


class InvalidAudioError(Exception):
    """The selected file cannot be decoded as audio."""


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Transcript:
    segments: list[TranscriptSegment]
    language: str
    duration: float


def get_audio_duration(path: Path) -> float | None:
    """Read the container duration without decoding the whole MP3."""
    try:
        import av
    except ImportError:
        return _ffprobe_duration(path)

    try:
        with av.open(str(path)) as container:
            if not container.streams.audio:
                raise InvalidAudioError("音声ストリームがありません。")
            if "mp3" not in container.format.name.split(","):
                raise InvalidAudioError("MP3ファイルを選択してください。")
            if container.duration is not None:
                return float(container.duration / av.time_base)
            stream = container.streams.audio[0]
            if stream.duration is not None and stream.time_base is not None:
                return float(stream.duration * stream.time_base)
    except InvalidAudioError:
        raise
    except (av.FFmpegError, OSError) as exc:
        raise InvalidAudioError("MP3を読み取れませんでした。") from exc
    return None


def _ffprobe_duration(path: Path) -> float | None:
    if shutil.which("ffprobe") is None:
        raise RuntimeError("ffprobeが見つかりません。FFmpegをインストールしてください。")
    completed = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=format_name,duration", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        raise InvalidAudioError("MP3を読み取れませんでした。")
    try:
        details = json.loads(completed.stdout)["format"]
        if "mp3" not in details["format_name"].split(","):
            raise InvalidAudioError("MP3ファイルを選択してください。")
        return float(details["duration"]) if "duration" in details else None
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise InvalidAudioError("MP3を読み取れませんでした。") from exc


def save_upload(uploaded_file, max_bytes: int = MAX_FILE_BYTES) -> Path:
    """Copy an upload to a temporary MP3 without duplicating it in memory."""
    fd, filename = tempfile.mkstemp(suffix=".mp3")
    path = Path(filename)
    try:
        with os.fdopen(fd, "wb") as destination:
            uploaded_file.seek(0)
            copied = 0
            while data := uploaded_file.read(1024 * 1024):
                copied += len(data)
                if copied > max_bytes:
                    raise ValueError("ファイルの上限は1 GBです。")
                destination.write(data)
        return path
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def iter_audio_chunks(path: Path) -> Iterator[tuple[float, object]]:
    """Decode MP3 to bounded five-minute mono float32 chunks at 16 kHz."""
    try:
        import av
    except ImportError:
        yield from _iter_ffmpeg_chunks(path)
        return
    import numpy as np

    try:
        with av.open(str(path)) as container:
            if not container.streams.audio:
                raise InvalidAudioError("音声ストリームがありません。")
            resampler = av.AudioResampler(
                format="fltp", layout="mono", rate=SAMPLE_RATE
            )
            pieces = []
            buffered = 0
            emitted = 0

            def append_frame(frame):
                nonlocal pieces, buffered, emitted
                samples = np.asarray(frame.to_ndarray(), dtype=np.float32).reshape(-1)
                position = 0
                while position < samples.size:
                    take = min(CHUNK_SAMPLES - buffered, samples.size - position)
                    pieces.append(samples[position : position + take])
                    buffered += take
                    position += take
                    if buffered == CHUNK_SAMPLES:
                        chunk = np.concatenate(pieces)
                        yield emitted / SAMPLE_RATE, chunk
                        emitted += buffered
                        pieces = []
                        buffered = 0

            for decoded in container.decode(audio=0):
                for converted in resampler.resample(decoded):
                    yield from append_frame(converted)
            for converted in resampler.resample(None):
                yield from append_frame(converted)
            if buffered:
                yield emitted / SAMPLE_RATE, np.concatenate(pieces)
    except InvalidAudioError:
        raise
    except (av.FFmpegError, OSError, ValueError) as exc:
        raise InvalidAudioError("MP3を読み取れませんでした。") from exc


def _iter_ffmpeg_chunks(path: Path) -> Iterator[tuple[float, object]]:
    """Use installed FFmpeg when PyAV is unavailable in an existing environment."""
    import numpy as np

    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpegが見つかりません。FFmpegをインストールしてください。")
    process = subprocess.Popen(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    emitted = 0
    try:
        assert process.stdout is not None
        while data := process.stdout.read(CHUNK_SAMPLES * 4):
            if len(data) % 4:
                raise InvalidAudioError("MP3を読み取れませんでした。")
            samples = np.frombuffer(data, dtype="<f4").copy()
            yield emitted / SAMPLE_RATE, samples
            emitted += len(samples)
        if process.wait() != 0 or emitted == 0:
            raise InvalidAudioError("MP3を読み取れませんでした。")
    finally:
        if process.stdout:
            process.stdout.close()
        if process.poll() is None:
            process.kill()
            process.wait()


class _OpenAIWhisperAdapter:
    def __init__(self, model):
        self.model = model

    def transcribe(self, chunk, **kwargs):
        from types import SimpleNamespace

        result = self.model.transcribe(
            chunk,
            language=kwargs["language"],
            task="transcribe",
            fp16=False,
            verbose=False,
            condition_on_previous_text=False,
        )
        segments = [SimpleNamespace(**item) for item in result["segments"]]
        return segments, SimpleNamespace(language=result.get("language"))


def load_model(size: str):
    """Use a cached model offline when available, downloading it once otherwise."""
    try:
        from faster_whisper import WhisperModel, download_model
    except ImportError:
        import whisper

        return _OpenAIWhisperAdapter(whisper.load_model(size, device="cpu"))

    try:
        model_path = download_model(size, local_files_only=True)
    except Exception:
        model_path = download_model(size)
    return WhisperModel(model_path, device="cpu", compute_type="int8")


def transcribe_file(
    path: Path,
    model,
    language: str | None,
    on_progress: Callable[[float, float | None], None] | None = None,
) -> Transcript:
    """Transcribe bounded chunks and restore timestamps to the full recording."""
    duration = get_audio_duration(path)
    segments: list[TranscriptSegment] = []
    detected_language = language or "unknown"
    processed = 0.0

    for offset, chunk in iter_audio_chunks(path):
        chunk_duration = len(chunk) / SAMPLE_RATE
        candidates, info = model.transcribe(
            chunk,
            language=language,
            task="transcribe",
            beam_size=5,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        if language is None and detected_language == "unknown":
            detected_language = info.language or "unknown"
        for candidate in candidates:
            text = candidate.text.strip()
            if not text:
                continue
            start = offset + max(0.0, candidate.start)
            end = offset + min(chunk_duration, max(candidate.end, candidate.start))
            segments.append(TranscriptSegment(start, max(start + 0.001, end), text))
        processed = offset + chunk_duration
        if on_progress:
            on_progress(processed, duration)

    return Transcript(segments, detected_language, processed)


def to_txt(transcript: Transcript) -> str:
    return "\n".join(segment.text for segment in transcript.segments) + (
        "\n" if transcript.segments else ""
    )


def _srt_time(seconds: float) -> str:
    milliseconds = round(max(0.0, seconds) * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def to_srt(transcript: Transcript) -> str:
    blocks = [
        f"{index}\n{_srt_time(segment.start)} --> {_srt_time(segment.end)}\n{segment.text}"
        for index, segment in enumerate(transcript.segments, start=1)
    ]
    return "\n\n".join(blocks) + ("\n" if blocks else "")
