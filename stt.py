
from faster_whisper import WhisperModel



model = WhisperModel(model_size_or_path="base", device="cpu", compute_type="int8")

def transcribe(path, language):
    segs, info = model.transcribe(path, language=language, task="transcribe")

    transcribed_text = ""
    for i in segs:
        print(i.start, i.end, i.text)
        transcribed_text += i.text
    print(info.language, info.language_probability)
    return transcribed_text.strip()

if __name__ == "__main__":
    result = transcribe("audio.wav", "es")
    print(f"Transcribed result is : {result}")