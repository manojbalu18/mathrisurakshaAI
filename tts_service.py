"""
Text-to-Speech (TTS) Service for MathriSurakshaAI.
Converts AI assistant responses into audio output using gTTS
with clean text sanitization and multi-language support.
"""

import io
import re
try:
    from gtts import gTTS
    GTTS_AVAILABLE = True
except ImportError:
    gTTS = None
    GTTS_AVAILABLE = False

from config import TTS_LANGUAGE_MAP


class TTSService:
    """Service for synthesizing spoken audio from response text."""

    def __init__(self):
        pass

    def clean_text_for_speech(self, text: str) -> str:
        """
        Strips markdown tags, formatting characters, URLs, and non-verbal emojis
        so that the text sounds natural when spoken by TTS engines.
        """
        if not text:
            return ""

        # Remove markdown links: [label](url) -> label
        cleaned = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        
        # Remove bold, italics, headers, code formatting
        cleaned = re.sub(r'[*_~`#>]+', ' ', cleaned)
        
        # Remove markdown bullet lines
        cleaned = re.sub(r'^\s*[-+*]\s+', '', cleaned, flags=re.MULTILINE)
        
        # Remove parenthesis notes like (Note: ...) if desired or keep simple
        cleaned = re.sub(r'[\U00010000-\U0010ffff]', '', cleaned)  # Remove 4-byte unicode emojis
        cleaned = re.sub(r'[\u2600-\u27BF]', '', cleaned)          # Remove misc symbols & dingbats
        
        # Normalize whitespace and clean space before punctuation
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        cleaned = re.sub(r'\s+([,.!?])', r'\1', cleaned)
        return cleaned

    def get_tts_language_code(self, language_name: str) -> str:
        """Get the gTTS language code for the selected UI language."""
        return TTS_LANGUAGE_MAP.get(language_name, "en")

    def synthesize(self, text: str, language_name: str = "English") -> Optional[bytes]:
        """
        Synthesizes text into MP3 audio bytes.
        
        Returns:
            bytes: MP3 audio data or None if synthesis failed.
        """
        cleaned_text = self.clean_text_for_speech(text)
        if not cleaned_text or not GTTS_AVAILABLE or gTTS is None:
            return None

        lang_code = self.get_tts_language_code(language_name)

        try:
            fp = io.BytesIO()
            tts = gTTS(text=cleaned_text, lang=lang_code, slow=False)
            tts.write_to_fp(fp)
            fp.seek(0)
            return fp.read()
        except Exception as e:
            # Fallback to English if regional language synthesis encountered an issue
            if lang_code != "en":
                try:
                    fp = io.BytesIO()
                    tts = gTTS(text=cleaned_text, lang="en", slow=False)
                    tts.write_to_fp(fp)
                    fp.seek(0)
                    return fp.read()
                except Exception:
                    pass
            print(f"TTS synthesis error: {e}")
            return None
