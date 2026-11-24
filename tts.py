# Turns translated text into speech audio using local Piper voices.
# TTS(text, language) returns raw 16-bit mono PCM at output_rate (no WAV header).

import wave
from pathlib import Path

from piper import PiperVoice

from voice_list import VOICES

VOICE_DIR = Path(__file__).resolve().parent / "voices"
output_rate = 22050


def _load_voices():
    missing = [name for name in VOICES.values() if not (VOICE_DIR / f"{name}.onnx").exists()]
    if missing:
        raise SystemExit(
            f"Missing voice files in {VOICE_DIR}: {', '.join(missing)}\n"
            "Run:  python download_voices.py"
        )
    return {lang: PiperVoice.load(str(VOICE_DIR / f"{name}.onnx")) for lang, name in VOICES.items()}


Voices = _load_voices()


def TTS(text, language):
    text = text.strip()
    if text == "":
        print("No text provided")
        return None

    if language not in Voices:
        print(f"No voice for language '{language}'")
        return None

    audio = b""
    for block in Voices[language].synthesize(text):
        audio += block.audio_int16_bytes
    return audio


if __name__ == "__main__":
    audio = TTS(" hola, cómo estás ", "es")
    print(f"Got {len(audio)} bytes = {len(audio) / 2 / output_rate:.2f} seconds")

    with wave.open("tts_test.wav", "wb") as a:
        a.setnchannels(1)
        a.setsampwidth(2)
        a.setframerate(output_rate)
        a.writeframes(audio)

    print("Saved tts_test.wav file")
