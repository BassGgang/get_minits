"""Japanese Streamlit UI for private, local MP3 transcription."""

from __future__ import annotations

import time
from importlib.util import find_spec
from pathlib import Path

import streamlit as st

from transcription import (
    MAX_FILE_BYTES,
    InvalidAudioError,
    load_model,
    save_upload,
    to_srt,
    to_txt,
    transcribe_file,
)

st.set_page_config(page_title="MP3文字起こし", page_icon="🎙️", layout="centered")


@st.cache_resource(max_entries=1, show_spinner=False)
def cached_model(size: str):
    return load_model(size)


def clear_result() -> None:
    st.session_state.pop("result", None)


def safe_stem(filename: str) -> str:
    name = filename.replace("\\", "/").split("/")[-1]
    stem = Path(name).stem
    return "".join(c if c.isalnum() or c in "-_. " else "_" for c in stem).strip() or "audio"


st.title("🎙️ MP3文字起こし")
st.caption("MP3を選ぶだけで、PC内で文字起こしします。音声は外部APIへ送信しません。")

uploaded = st.file_uploader(
    "MP3ファイルを選択",
    type=["mp3"],
    accept_multiple_files=False,
    on_change=clear_result,
    help="1ファイル、最大1 GB（1,024 MB）まで",
)

if uploaded is not None:
    st.write(f"**{uploaded.name}** · {uploaded.size / (1024 * 1024):,.1f} MB")
    if st.toggle("音声をプレビューする（大きなファイルではメモリを使います）"):
        st.audio(uploaded, format="audio/mpeg")

left, right = st.columns(2)
with left:
    language_label = st.selectbox(
        "音声の言語", ["自動判定", "日本語"], on_change=clear_result
    )
with right:
    default_speed = 0
    if find_spec("faster_whisper") is None and not (Path.home() / ".cache/whisper/small.pt").exists() and (Path.home() / ".cache/whisper/base.pt").exists():
        default_speed = 1
    speed_label = st.selectbox(
        "精度・速度", ["標準", "高速"], index=default_speed, on_change=clear_result
    )

if uploaded is None:
    st.info("MP3ファイルを選択してください。")
elif uploaded.size > MAX_FILE_BYTES:
    st.error("ファイルの上限は1 GBです。")

can_start = uploaded is not None and 0 < uploaded.size <= MAX_FILE_BYTES
if st.button("文字起こし開始", type="primary", disabled=not can_start):
    clear_result()
    model_size = "small" if speed_label == "標準" else "base"
    language = "ja" if language_label == "日本語" else None
    started = time.monotonic()
    temporary_path = None
    status = st.status("MP3を準備しています…", expanded=True)
    progress = st.progress(0, text="準備中")
    try:
        temporary_path = save_upload(uploaded)
        status.update(label="音声認識モデルを準備しています…")
        st.write("初回はモデルのダウンロードが必要です。")
        model = cached_model(model_size)
        status.update(label="文字起こししています…")

        def update_progress(processed: float, duration: float | None) -> None:
            if duration and duration > 0:
                percent = min(99, int(100 * processed / duration))
                progress.progress(percent, text=f"音声の {processed / 60:,.1f} / {duration / 60:,.1f} 分を処理")
            else:
                progress.progress(0, text=f"音声の {processed / 60:,.1f} 分を処理")

        transcript = transcribe_file(temporary_path, model, language, update_progress)
        st.session_state["result"] = {
            "transcript": transcript,
            "filename": uploaded.name,
            "elapsed": time.monotonic() - started,
        }
        progress.progress(100, text="完了")
        status.update(label="文字起こしが完了しました", state="complete", expanded=False)
    except InvalidAudioError as exc:
        status.update(label="MP3を読み取れませんでした", state="error")
        st.error(str(exc))
    except ValueError as exc:
        status.update(label="処理できませんでした", state="error")
        st.error(str(exc))
    except MemoryError:
        status.update(label="メモリが不足しました", state="error")
        st.error("メモリが不足しました。『高速』で再試行してください。")
    except Exception as exc:
        status.update(label="処理できませんでした", state="error")
        st.error("モデルの取得または文字起こしに失敗しました。通信状態を確認し、再試行してください。")
        with st.expander("エラーの詳細"):
            st.code(f"{type(exc).__name__}: {exc}")
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

result = st.session_state.get("result")
if result is not None:
    transcript = result["transcript"]
    st.divider()
    st.subheader("文字起こし結果")
    language_name = {"ja": "日本語", "en": "英語"}.get(transcript.language, transcript.language)
    st.caption(f"使用言語: {language_name}　|　処理時間: {result['elapsed']:.1f} 秒")

    if not transcript.segments:
        st.warning("発話を検出できませんでした。")
    else:
        st.text_area("本文（選択してコピーできます）", to_txt(transcript), height=260)
        with st.expander("時刻付きの区間を表示"):
            lines = []
            for segment in transcript.segments:
                minutes, seconds = divmod(int(segment.start), 60)
                hours, minutes = divmod(minutes, 60)
                lines.append(f"{hours:02}:{minutes:02}:{seconds:02}  {segment.text}")
            st.text_area("区間", "\n".join(lines), height=300)

        stem = safe_stem(result["filename"])
        first, second = st.columns(2)
        with first:
            st.download_button(
                "TXTを保存", to_txt(transcript).encode("utf-8"),
                file_name=f"{stem}.txt", mime="text/plain; charset=utf-8",
                on_click="ignore", use_container_width=True,
            )
        with second:
            st.download_button(
                "SRTを保存", to_srt(transcript).encode("utf-8"),
                file_name=f"{stem}.srt", mime="application/x-subrip",
                on_click="ignore", use_container_width=True,
            )
