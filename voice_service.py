"""
Voice Service for MathriSurakshaAI.
Handles Speech-to-Text (STT) transcription with multi-language support
and structured UI state reporting.
"""

import io
from typing import Dict, Any, Union, BinaryIO
import speech_recognition as sr
from config import STT_LANGUAGE_MAP


class VoiceService:
    """Service for transcribing audio data into text across Indian regional languages."""

    def __init__(self):
        self.recognizer = sr.Recognizer()

    def get_stt_language_code(self, language_name: str) -> str:
        """Map human language name to BCP-47 Google Speech Recognition code."""
        return STT_LANGUAGE_MAP.get(language_name, "en-IN")

    def transcribe_audio_data(
        self,
        audio_data: Union[BinaryIO, bytes, str],
        language_name: str = "English",
    ) -> Dict[str, Any]:
        """
        Transcribes recorded audio data into text.
        
        Args:
            audio_data: Audio file stream (from st.audio_input), bytes, or file path.
            language_name: Selected display language (e.g. 'Hindi', 'Tamil', 'English').
            
        Returns:
            dict: {
                "status": "success" | "not_understood" | "error",
                "text": str,
                "message": str
            }
        """
        if not audio_data:
            return {
                "status": "error",
                "text": "",
                "message": "No audio data provided.",
            }

        stt_lang_code = self.get_stt_language_code(language_name)

        # Ensure audio_data is in a format accepted by sr.AudioFile
        if isinstance(audio_data, bytes):
            audio_source = io.BytesIO(audio_data)
        else:
            audio_source = audio_data

        try:
            with sr.AudioFile(audio_source) as source:
                # Adjust for ambient noise and record
                audio = self.recognizer.record(source)

            # Recognize using Google Speech Recognition
            recognized_text = self.recognizer.recognize_google(audio, language=stt_lang_code)
            return {
                "status": "success",
                "text": recognized_text.strip(),
                "message": f"Speech recognized successfully in {language_name}.",
            }
        except sr.UnknownValueError:
            return {
                "status": "not_understood",
                "text": "",
                "message": "Speech not understood. Please speak clearly into your microphone.",
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
