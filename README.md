# MP3文字起こしアプリ

MP3をPC内で文字起こしするStreamlitアプリです。最大1 GBのMP3を1件ずつ処理し、結果をTXTまたはSRTで保存できます。

## このMacで初めて起動する

1. ターミナルを開きます。
2. 次のコマンドを**上から順に**実行します。このMacに入っているStreamlitと音声認識モデルを使います。

```bash
cd /Users/matsunagakenta/Desktop/OCW_getTAG/new_App_get_char
bash start_local.command
```

3. ブラウザで **http://localhost:8501** を開きます。自動で開いた場合は、その画面を使ってください。

このMacでは「高速」の基本モデルが取得済みです。アプリはそれを初期選択するため、オフラインでも文字起こしできます。現在入っているOpenAI WhisperとFFmpegを使用します。「標準」のモデルが未取得なら、初回はインターネット接続が必要です。

## 2回目以降の起動

ターミナルで次の2行を実行し、ブラウザで **http://localhost:8501** を開きます。

```bash
cd /Users/matsunagakenta/Desktop/OCW_getTAG/new_App_get_char
bash start_local.command
```

終了するときは、起動したターミナルで `Ctrl+C` を押します。

## 画面の使い方

1. 「MP3ファイルを選択」でMP3を1件選びます。
2. 「音声の言語」を「自動判定」または「日本語」に設定します。
3. 「精度・速度」は通常「標準」を使います。処理を軽くしたい場合は「高速」を選びます。
4. 「文字起こし開始」を押します。処理が終わるまで画面を開いたまま待ちます。
5. 文章を確認し、「TXTを保存」または「SRTを保存」を押します。

音声プレビューは必要なときだけオンにしてください。大きなMP3を再生表示すると、追加のメモリを使います。

## Windows・ほかのMac・Linuxで起動する

Python 3.10～3.13を用意し、このフォルダを開いてから実行します。以下の `python3.13` / `py -3.13` は、インストール済みの対応バージョンに置き換えられます。初回のパッケージ導入とモデル取得にはインターネット接続が必要です。

macOS / Linux:

```bash
cd /path/to/new_App_get_char
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py
```

Windows（PowerShell）:

```powershell
cd C:\path\to\new_App_get_char
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## 困ったとき

- `No module named streamlit` と出る: 上の `pip install -r requirements.txt` を実行してください。起動時も `.venv` 内のPythonを使います。
- `PermissionError: Operation not permitted` と出る: 起動した環境がローカルのポート使用を制限しています。通常のMacのターミナルで `bash start_local.command` を実行してください。
- モデル取得に失敗する: ネット接続を確認して再実行してください。初回はモデルごとにダウンロードが必要です。
- 動作が遅い・メモリが不足する: 「高速」を選び、ほかの重いアプリを閉じて再試行してください。
- MP3を選べない: 上限は1 GB（1,024 MB）です。音声として読み取れないファイルも使えません。

音声は外部の文字起こしAPIへ送信しません。処理用の一時ファイルは処理後に削除します。詳しい仕様は[仕様書](SPEC.md)を参照してください。
