"""Text to speech for toolbox talks (Azure Speech REST). Optional.

Untested until an AZURE_SPEECH_KEY exists. Without a key, enabled() is False
and the app shows the text for the foreman to read aloud.
"""
import urllib.error
import urllib.request
from xml.sax.saxutils import escape

from . import config, library

LOCALES = {"en": "en-ZA", "af": "af-ZA", "zu": "zu-ZA"}


def enabled(language: str) -> bool:
    return bool(config.AZURE_SPEECH_KEY) and language in library.TTS_VOICES


def speak(text: str, language: str) -> bytes:
    voice = library.TTS_VOICES[language]
    ssml = (f"<speak version='1.0' xml:lang='{LOCALES[language]}'>"
            f"<voice name='{voice}'><prosody rate='-8%'>{escape(text[:6000])}</prosody></voice></speak>")
    req = urllib.request.Request(
        f"https://{config.AZURE_SPEECH_REGION}.tts.speech.microsoft.com/cognitiveservices/v1",
        data=ssml.encode(), method="POST",
        headers={"Ocp-Apim-Subscription-Key": config.AZURE_SPEECH_KEY,
                 "Content-Type": "application/ssml+xml",
                 "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3",
                 "User-Agent": config.APP_NAME})
    try:
        return urllib.request.urlopen(req, timeout=60).read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Azure TTS {e.code}: {e.read()[:200]!r}") from None
