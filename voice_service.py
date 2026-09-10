"""
Voice Service for MathriSurakshaAI.
Handles Speech-to-Text (STT) transcription with multi-language support
and structured UI state reporting.
"""

import io
import wave
from typing import Dict, Any, Union, BinaryIO, Optional

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except ImportError:
    sr = None
    SR_AVAILABLE = False

try:
    import soundfile as sf
    SOUNDFILE_AVAILABLE = True
except ImportError:
    sf = None
    SOUNDFILE_AVAILABLE = False

from config import STT_LANGUAGE_MAP


class VoiceService:
    """Service for transcribing audio data into text across Indian regional languages."""

    def __init__(self):
        if SR_AVAILABLE and sr is not None:
            self.recognizer = sr.Recognizer()
            self.recognizer.energy_threshold = 300
            self.recognizer.dynamic_energy_threshold = True
        else:
            self.recognizer = None

    def get_stt_language_code(self, language_name: str) -> str:
        """Map human language name to BCP-47 Google Speech Recognition code."""
        return STT_LANGUAGE_MAP.get(language_name, "en-IN")

    def _prepare_wav_bytes(self, raw_audio: Union[BinaryIO, bytes, Any]) -> Optional[io.BytesIO]:
        """Convert any incoming audio stream or bytes into clean 16-bit PCM WAV in memory."""
        # 1. Extract raw byte content
        if isinstance(raw_audio, bytes):
            raw_bytes = raw_audio
        elif hasattr(raw_audio, "getvalue"):
            raw_bytes = raw_audio.getvalue()
        elif hasattr(raw_audio, "read"):
            try:
                raw_audio.seek(0)
            except Exception:
                pass
            raw_bytes = raw_audio.read()
        else:
            return None

        if not raw_bytes or len(raw_bytes) < 100:
            return None

        # 2. Try direct read using soundfile if available
        if SOUNDFILE_AVAILABLE and sf is not None:
            try:
                data, sample_rate = sf.read(io.BytesIO(raw_bytes))
                out_buf = io.BytesIO()
                sf.write(out_buf, data, sample_rate, format='WAV', subtype='PCM_16')
                out_buf.seek(0)
                return out_buf
            except Exception:
                pass

        # 3. Fallback to raw BytesIO (in case it is already valid WAV)
        out_buf = io.BytesIO(raw_bytes)
        out_buf.seek(0)
        return out_buf

    def transcribe_audio_data(
        self,
        audio_data: Union[BinaryIO, bytes, Any],
        language_name: str = "English",
    ) -> Dict[str, Any]:
        """
        Transcribes recorded audio data into text.
        
        Args:
            audio_data: Audio file stream (from st.audio_input), bytes, or file object.
            language_name: Selected display language (e.g. 'Telugu', 'Hindi', 'Tamil', 'English').
            
        Returns:
            dict: {
                "status": "success" | "not_understood" | "error",
                "text": str,
                "message": str
            }
        """
        if not SR_AVAILABLE or self.recognizer is None:
            return {
                "status": "error",
                "text": "",
                "message": "Speech recognition engine is unavailable. Please check system dependencies.",
            }

        if not audio_data:
            return {
                "status": "error",
                "text": "",
                "message": "No audio data recorded. Please record your voice and try again.",
            }

        wav_source = self._prepare_wav_bytes(audio_data)
        if not wav_source:
            return {
                "status": "error",
                "text": "",
                "message": "Could not read recorded audio stream. Please record again.",
            }

        stt_lang_code = self.get_stt_language_code(language_name)

        try:
            with sr.AudioFile(wav_source) as source:
                audio = self.recognizer.record(source)

            # Recognize using Google Speech Recognition
            recognized_text = self.recognizer.recognize_google(audio, language=stt_lang_code)
            return {
                "status": "success",
                "text": recognized_text.strip(),
                "message": f"Speech recognized successfully in {language_name}.",
            }
        except sr.UnknownValueError:
            # If regional language was missed, try fallback to en-IN or hi-IN before giving up
            if stt_lang_code not in ["en-IN", "hi-IN"]:
                try:
                    wav_source.seek(0)
                    with sr.AudioFile(wav_source) as source:
                        audio = self.recognizer.record(source)
                    fallback_text = self.recognizer.recognize_google(audio, language="en-IN")
                    if fallback_text.strip():
                        return {
                            "status": "success",
                            "text": fallback_text.strip(),
                            "message": "Speech recognized using English fallback.",
                        }
                except Exception:
                    pass

            return {
                "status": "not_understood",
                "text": "",
                "message": "Speech not understood. Please speak clearly into your microphone and try again.",
            }
        except sr.RequestError as e:
            return {
                "status": "error",
                "text": "",
                "message": f"Speech recognition network service error: {str(e)}",
            }
        except Exception as e:
            return {
                "status": "error",
                "text": "",
                "message": f"Audio processing error: {str(e)}",
            }
