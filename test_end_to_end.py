"""
Comprehensive end-to-end integration and verification tests for MathriSurakshaAI.
Covers LM Studio integration, voice input (STT), voice output (TTS),
offline resilience, safety overrides, and multi-language support.
"""

import unittest
from unittest.mock import patch, MagicMock
import io
import wave
import struct

from lm_studio_client import LMStudioClient, LMStudioConnectionError, LMStudioTimeoutError
from ai_service import AIService
from voice_service import VoiceService
from tts_service import TTSService
import database


def create_dummy_wav_bytes(duration_sec=0.5, sample_rate=16000) -> bytes:
    """Helper to create a valid minimal WAV audio byte stream in memory."""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wav_file:
        wav_file.setnchannels(1)      # mono
        wav_file.setsampwidth(2)     # 16-bit
        wav_file.setframerate(sample_rate)
        # Generate silence / simple tone
        num_samples = int(duration_sec * sample_rate)
        data = struct.pack('<' + 'h' * num_samples, *([0] * num_samples))
        wav_file.writeframes(data)
    buf.seek(0)
    return buf.read()


class TestLMStudioAndVoiceSystem(unittest.TestCase):

    def setUp(self):
        database.init_db()

    # ---------------- 1. LM STUDIO OFFLINE HANDLING ----------------
    def test_lm_studio_server_offline_detection(self):
        """Test detection and friendly error reporting when LM Studio is not running."""
        client = LMStudioClient(base_url="http://127.0.0.1:59999/v1", timeout=1)
        status = client.check_connection(timeout=0.5)
        self.assertFalse(status["online"])
        self.assertIsNone(status["active_model"])
        self.assertTrue(len(status["message"]) > 0)

    def test_lm_studio_offline_fallback_in_ai_service(self):
        """Test that AI Service gracefully falls back to local knowledge base when LM Studio is offline."""
        client = LMStudioClient(base_url="http://127.0.0.1:59999/v1", timeout=1)
        service = AIService(client=client)
        
        result = service.process_message("Can I drink coffee during pregnancy?", language_name="English")
        self.assertFalse(result["server_online"])
        self.assertEqual(result["source"], "fallback")
        self.assertIn("caffeine", result["response"].lower())
        self.assertIn("LM Studio offline", result["diagnostic"])

    # ---------------- 2. LM STUDIO ONLINE RESPONSE MOCK ----------------
    @patch("requests.get")
    @patch("requests.post")
    def test_lm_studio_online_chat_completion(self, mock_post, mock_get):
        """Test full online LM Studio request and response flow."""
        # Mock GET /v1/models
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {
            "data": [{"id": "llama-3-8b-instruct"}]
        }
        mock_get.return_value = mock_get_resp

        # Mock POST /v1/chat/completions
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "For healthy fetal development, include green leafy vegetables, lentils, and dairy in your diet."
                    }
                }
            ]
        }
        mock_post.return_value = mock_post_resp

        client = LMStudioClient(base_url="http://localhost:1234/v1")
        service = AIService(client=client)

        result = service.process_message(
            "What should I eat in the second trimester?",
            chat_history=[],
            user_context={"risk_level": "Low", "mother_name": "Anita"},
            language_name="English"
        )

        self.assertTrue(result["server_online"])
        self.assertEqual(result["source"], "lm_studio")
        self.assertIn("green leafy vegetables", result["response"])
        self.assertIn("llama-3-8b-instruct", result["diagnostic"])

    # ---------------- 3. EMERGENCY SAFETY OVERRIDE ----------------
    def test_emergency_interceptor(self):
        """Test that emergency symptoms trigger immediate escalation regardless of LM Studio status."""
        service = AIService()
        emergencies = [
            "I have heavy vaginal bleeding and dizziness",
            "Severe chest pain and cannot breathe",
            "Suffering from convulsion and faint feeling"
        ]
        for prompt in emergencies:
            result = service.process_message(prompt, language_name="English")
            self.assertTrue(result["is_emergency"])
            self.assertEqual(result["source"], "emergency_override")
            self.assertIn("CRITICAL ALERT", result["response"])

    # ---------------- 4. CONTEXT AWARENESS (HIGH RISK) ----------------
    def test_high_risk_patient_context(self):
        """Test that patients with High Risk level receive continuous monitoring reminders."""
        service = AIService()
        result = service.process_message(
            "How much water should I drink?",
            user_context={"risk_level": "High", "mother_name": "Meena"},
            language_name="English"
        )
        self.assertIn("High Risk", result["response"])

    # ---------------- 5. MULTI-LANGUAGE TRANSLATION ----------------
    def test_multilingual_translation(self):
        """Test that responses are translated into Indian regional languages."""
        service = AIService()
        resp_en = "Calcium is essential for your baby's developing bones."
        # Hindi translation
        resp_hi = service.translate_text(resp_en, "Hindi")
        self.assertNotEqual(resp_en, resp_hi)
        self.assertTrue(len(resp_hi) > 5)

        # Telugu translation
        resp_te = service.translate_text(resp_en, "Telugu")
        self.assertNotEqual(resp_en, resp_te)
        self.assertTrue(len(resp_te) > 5)

    # ---------------- 6. VOICE INPUT (STT) ----------------
    def test_voice_input_empty_or_corrupted(self):
        """Test voice service behavior on empty or invalid audio data."""
        vs = VoiceService()
        res_empty = vs.transcribe_audio_data(None)
        self.assertEqual(res_empty["status"], "error")

        res_corrupt = vs.transcribe_audio_data(b"not a real audio file")
        self.assertEqual(res_corrupt["status"], "error")

    @patch("speech_recognition.Recognizer.recognize_google")
    @patch("speech_recognition.Recognizer.record")
    def test_voice_input_successful_transcription(self, mock_record, mock_recognize):
        """Test successful voice recognition and language code forwarding."""
        mock_recognize.return_value = "What exercises are safe in the third trimester?"
        
        vs = VoiceService()
        wav_bytes = create_dummy_wav_bytes()
        res = vs.transcribe_audio_data(wav_bytes, language_name="Hindi")

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["text"], "What exercises are safe in the third trimester?")
        # Verify it passed hi-IN
        mock_recognize.assert_called_once()
        _, kwargs = mock_recognize.call_args
        self.assertEqual(kwargs.get("language"), "hi-IN")

    # ---------------- 7. UNIFIED PIPELINE (STT -> AI) ----------------
    @patch("speech_recognition.Recognizer.recognize_google")
    @patch("speech_recognition.Recognizer.record")
    def test_voice_to_ai_unified_pipeline(self, mock_record, mock_recognize):
        """Test that speech recognized text seamlessly feeds into the AI processing pipeline."""
        mock_recognize.return_value = "Tell me about folic acid supplements"
        
        vs = VoiceService()
        wav_bytes = create_dummy_wav_bytes()
        voice_res = vs.transcribe_audio_data(wav_bytes, language_name="English")
        self.assertEqual(voice_res["status"], "success")

        ai_svc = AIService()
        ai_res = ai_svc.process_message(voice_res["text"], language_name="English")
        self.assertIn("folic acid", ai_res["response"].lower())

    # ---------------- 8. VOICE OUTPUT (TTS) ----------------
    def test_tts_synthesis_and_text_sanitization(self):
        """Test text-to-speech synthesis and markdown cleaning."""
        tts = TTSService()
        
        # Test cleaning
        raw_text = "### Safe Diet: **Eat** [Spinach](url) & *jaggery*! 🩺"
        clean = tts.clean_text_for_speech(raw_text)
        self.assertEqual(clean, "Safe Diet: Eat Spinach & jaggery!")

        # Test synthesis in English
        audio_en = tts.synthesize("Take your daily IFA tablet with water.", "English")
        self.assertIsNotNone(audio_en)
        self.assertGreater(len(audio_en), 500)

        # Test synthesis in Hindi
        audio_hi = tts.synthesize("प्रतिदिन स्वच्छ पानी पिएं।", "Hindi")
        self.assertIsNotNone(audio_hi)
        self.assertGreater(len(audio_hi), 500)


if __name__ == "__main__":
    unittest.main()
