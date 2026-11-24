import json
import os
import threading
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
KEY_FILE = HERE / "key.env"
load_dotenv(KEY_FILE)

api_key = os.getenv("GOOGLE_TRANSLATE_API_KEY")
if api_key is None:
    print(f"Warning: key not found")

URL = "https://translation.googleapis.com/language/translate/v2"

# Daily cap on characters sent to Google, so usage stays inside the free
# 500,000 characters/month (10,000 x 31 days = 310,000). Resets at midnight.
DAILY_CHAR_LIMIT = 10_000
USAGE_FILE = HERE / "translate_usage.json"   # remembers today's count across restarts
_usage_lock = threading.Lock()


class DailyLimitReached(Exception):
    """Raised when a translation would go over DAILY_CHAR_LIMIT for today."""


def _load_usage():
    today = date.today().isoformat()
    try:
        data = json.loads(USAGE_FILE.read_text())
        if data.get("date") == today:
            return today, int(data.get("chars", 0))
    except (OSError, ValueError):
        pass
    return today, 0  # new day, or no/broken file


def _save_usage(day, chars):
    USAGE_FILE.write_text(json.dumps({"date": day, "chars": chars}))


def _reserve(n):
    """Count n characters toward today's limit, or raise if it would go over."""
    with _usage_lock:
        day, used = _load_usage()
        if used + n > DAILY_CHAR_LIMIT:
            raise DailyLimitReached(
                f"Daily translation limit reached ({used:,} of {DAILY_CHAR_LIMIT:,} characters used today)."
            )
        _save_usage(day, used + n)


def _refund(n):
    """Give characters back if the request to Google failed (nothing was billed)."""
    with _usage_lock:
        day, used = _load_usage()
        _save_usage(day, max(0, used - n))


def chars_used_today():
    with _usage_lock:
        return _load_usage()[1]


def translate(text, target, source=None):
    """Translate text. Returns the translation, None on error, or raises DailyLimitReached."""
    text = text.strip()

    if text == "":
        print("No text was provided")
        return None

    query = {
        "q": text,
        "target": target,
        "format": "text"
    }

    if source is not None:
        query["source"] = source

    chars = len(text)
    _reserve(chars)

    try:
        response = requests.post(URL, params={"key": api_key}, json=query, timeout=10)
    except requests.RequestException as error:      # no internet, timeout, etc.
        _refund(chars)
        print(f"Translate: request failed: {error}")
        return None

    if response.status_code != 200:
        _refund(chars)
        print(f"Google returned {response.status_code}: {response.text}")
        return None

    return response.json()["data"]["translations"][0]["translatedText"]


if __name__ == "__main__":

    print(translate("Hola, ¿cómo estás?", "fr", "es"))
    print(f"Characters used today: {chars_used_today():,} / {DAILY_CHAR_LIMIT:,}")
