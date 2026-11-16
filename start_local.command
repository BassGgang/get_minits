#!/bin/bash
set -e

cd "$(dirname "$0")"

if [[ -x .venv/bin/python ]] && .venv/bin/python -c 'import streamlit, faster_whisper, av, numpy' >/dev/null 2>&1; then
    app_python=.venv/bin/python
elif command -v python3.10 >/dev/null 2>&1 && python3.10 -c 'import streamlit, whisper, numpy' >/dev/null 2>&1 && command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
    app_python="$(command -v python3.10)"
else
    echo "起動に必要なパッケージが見つかりません。README.md の『Windows・ほかのMac・Linuxで起動する』を参照してください。"
    exit 1
fi

echo "ブラウザで http://localhost:8501 を開いてください。終了は Ctrl+C です。"
exec "$app_python" -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
