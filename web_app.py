# Web version of speak.py: open http://localhost:8000 in a browser, pick languages,
# record from the mic, and play back the translated speech.
#
# Run from the project folder:
#   python web_app.py
#
# Only the most recent recording and translation are kept in output/
# (latest_input.* and latest_translation.wav); each new run overwrites them.

import base64
import io
import os
import sys
import threading
import wave
from pathlib import Path

from flask import Flask, jsonify, render_template, request

# Windows consoles default to a code page that can't print e.g. Chinese; avoid crashing on print()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
os.chdir(HERE)  # run from the project folder no matter where it was started

from faster_whisper.audio import decode_audio  # noqa: E402
from stt import transcribe          # noqa: E402
from translate import DailyLimitReached, translate  # noqa: E402
from tts import TTS, Voices, output_rate  # noqa: E402

OUTPUT_DIR = HERE / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
OUTPUT_PATH = OUTPUT_DIR / "latest_translation.wav"

LANGUAGE_NAMES = {
    "en": "English", "es": "Spanish", "fr": "French", "pt": "Portuguese",
    "de": "German", "it": "Italian", "zh": "Chinese", "ja": "Japanese",
    "ko": "Korean", "ru": "Russian", "ar": "Arabic", "hi": "Hindi", "nl": "Dutch",
}
# Whisper + Google Translate handle all of these as input; output is limited to Piper voices
INPUT_LANGS = {code: LANGUAGE_NAMES[code] for code in LANGUAGE_NAMES}
OUTPUT_LANGS = {code: LANGUAGE_NAMES.get(code, code) for code in Voices}

ON_SPACE = bool(os.getenv("SPACE_ID"))  # set automatically when running on Hugging Face Spaces
MAX_SECONDS = 60                        # longest recording accepted (the page also auto-stops here)
MAX_UPLOAD_MB = 5                       # 60 s of browser audio is ~1 MB; anything far bigger is rejected

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024
pipeline_lock = threading.Lock()  # one translation at a time keeps the models happy


@app.errorhandler(413)
def too_large(_error):
    return jsonify(error=f"Recording is too large. Please keep it under {MAX_SECONDS} seconds."), 413


def file_extension(mimetype):
    """Browsers record in different formats: Chrome/Edge webm, Firefox ogg, Safari/iPhone mp4."""
    mimetype = mimetype or ""
    if "ogg" in mimetype:
        return ".ogg"
    if "mp4" in mimetype or "aac" in mimetype or "m4a" in mimetype:
        return ".m4a"
    return ".webm"


def clear_output_dir():
    """Remove everything in output/ (old recordings from earlier runs)."""
    for f in OUTPUT_DIR.iterdir():
        try:
            if f.is_file():
                f.unlink()
        except OSError:
            pass


def pcm_to_wav(pcm, rate):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


@app.route("/")
def index():
    return render_template(
        "index.html",
        input_langs=INPUT_LANGS,
        output_langs=OUTPUT_LANGS,
        max_seconds=MAX_SECONDS,
        on_space=ON_SPACE,
    )


@app.route("/translate", methods=["POST"])
def translate_speech():
    src = request.form.get("src")
    tgt = request.form.get("tgt")
    audio_file = request.files.get("audio")

    if src not in INPUT_LANGS or tgt not in OUTPUT_LANGS:
        return jsonify(error="Unsupported language choice."), 400
    if audio_file is None:
        return jsonify(error="No audio was received."), 400

    ext = file_extension(audio_file.mimetype)

    with pipeline_lock:
        # replace the previous recording (its extension may differ by browser)
        for old in OUTPUT_DIR.glob("latest_input.*"):
            old.unlink(missing_ok=True)
        input_path = OUTPUT_DIR / f"latest_input{ext}"
        audio_file.save(input_path)

        try:
            seconds = len(decode_audio(str(input_path))) / 16000
        except Exception as error:
            return jsonify(error=f"Could not read the recording: {error}"), 400
        if seconds > MAX_SECONDS + 2:  # small allowance for timing differences
            return jsonify(error=f"Recording is too long. Please keep it under {MAX_SECONDS} seconds."), 400

        try:
            text = transcribe(str(input_path), src)
        except Exception as error:
            return jsonify(error=f"Could not read the recording: {error}"), 500
        if not text:
            return jsonify(error="No speech was detected. Try speaking a bit louder or longer."), 400

        # Google rejects same-language requests, so just repeat the text
        try:
            translated = text if src == tgt else translate(text, tgt, src)
        except DailyLimitReached:
            return jsonify(error="The daily translation limit has been reached. Please try again tomorrow."), 429
        if translated is None:
            return jsonify(error="Translation failed (check key.env and your internet connection)."), 502

        speech = TTS(translated, tgt)
        if not speech:
            return jsonify(error="Text-to-speech failed."), 500

        wav_bytes = pcm_to_wav(speech, output_rate)
        OUTPUT_PATH.write_bytes(wav_bytes)

    print(f"[{src} -> {tgt}] {text!r} -> {translated!r}")

    return jsonify(
        heard=text,
        translation=translated,
        audio=base64.b64encode(wav_bytes).decode("ascii"),
    )


if __name__ == "__main__":
    clear_output_dir()
    port = int(os.getenv("PORT", "8000"))
    # On Hugging Face the server must accept outside connections; locally, only this computer
    host = "0.0.0.0" if ON_SPACE else "127.0.0.1"
    print(f"Open http://localhost:{port} in your browser")
    app.run(host=host, port=port, threaded=True)
