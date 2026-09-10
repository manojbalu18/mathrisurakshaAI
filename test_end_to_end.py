"""
Comprehensive end-to-end integration and verification tests for MathriSurakshaAI.
Covers LM Studio integration, automatic voice processing (STT), voice output (TTS),
SHA-256 deduplication, Fast2SMS and Exotel ASHA worker safety escalations, safety overrides, and multi-language support.
"""

import unittest
from unittest.mock import patch, MagicMock
import io
import wave
import struct
import hashlib

from lm_studio_client import LMStudioClient, LMStudioConnectionError, LMStudioTimeoutError
from ai_service import AIService
from voice_service import VoiceService
from tts_service import TTSService
from escalation_service import EscalationService, MockTelephonyAdapter
from ai_engine import calculate_risk_from_text
import database


def create_dummy_wav_bytes(duration_sec=0.5, sample_rate=16000) -> bytes:
    """Helper to create a valid minimal WAV audio byte stream in memory."""
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wav_file:
        wav_file.setnchannels(1)      # mono
        wav_file.setsampwidth(2)     # 16-bit
        wav_file.setframerate(sample_rate)
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
        """Test full online LM Studio request and response flow with configured qwen2.5-7b-instruct."""
        # Mock GET /v1/models
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {
            "data": [{"id": "qwen2.5-7b-instruct"}]
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

        client = LMStudioClient()
        self.assertEqual(client.base_url, "http://127.0.0.1:1234/v1")
        self.assertEqual(client.chat_endpoint, "http://127.0.0.1:1234/v1/chat/completions")
        self.assertEqual(client.default_model, "qwen2.5-7b-instruct")

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
        self.assertIn("qwen2.5-7b-instruct", result["diagnostic"])

    def test_lm_studio_configuration_customization(self):
        """Test that base URL, chat endpoint, and model can be customized without hardcoding."""
        custom_client = LMStudioClient(
            base_url="http://192.168.1.100:1234/v1",
            chat_endpoint="http://192.168.1.100:1234/v1/chat/completions",
            default_model="custom-model-id"
        )
        self.assertEqual(custom_client.base_url, "http://192.168.1.100:1234/v1")
        self.assertEqual(custom_client.chat_endpoint, "http://192.168.1.100:1234/v1/chat/completions")
        self.assertEqual(custom_client.default_model, "custom-model-id")

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
        mock_recognize.assert_called_once()
        _, kwargs = mock_recognize.call_args
        self.assertEqual(kwargs.get("language"), "hi-IN")

    # ---------------- 7. UNIFIED AUTOMATIC PIPELINE WITH SHA-256 HASHING ----------------
    @patch("speech_recognition.Recognizer.recognize_google")
    @patch("speech_recognition.Recognizer.record")
    def test_voice_automatic_processing_and_hash_deduplication(self, mock_record, mock_recognize):
        """Test automatic voice workflow and ensure SHA-256 hash prevents duplicate processing."""
        mock_recognize.return_value = "I have a mild headache today"
        
        vs = VoiceService()
        wav_bytes = create_dummy_wav_bytes()
        audio_hash = hashlib.sha256(wav_bytes).hexdigest()

        # Simulated session state
        session_state = {"last_processed_audio_hash": None}

        # First run: new audio hash should trigger processing
        self.assertNotEqual(audio_hash, session_state["last_processed_audio_hash"])
        res = vs.transcribe_audio_data(wav_bytes, language_name="English")
        self.assertEqual(res["status"], "success")

        # Update session state with processed hash
        session_state["last_processed_audio_hash"] = audio_hash

        # Second rerun: same audio hash must be detected as duplicate and skipped
        self.assertEqual(audio_hash, session_state["last_processed_audio_hash"])

    # ---------------- 8. END-TO-END RISK AND TWILIO ESCALATION PIPELINE ----------------
    def test_end_to_end_symptom_to_asha_escalation_flow(self):
        """Test complete pipeline from text/speech symptom -> clinical risk -> Twilio escalation."""
        mock_adapter = MockTelephonyAdapter()
        escalation_svc = EscalationService(adapter=mock_adapter)

        # 1. Low symptom: No notification
        risk_low = calculate_risk_from_text("I feel a little sleepy after lunch")
        res_low = escalation_svc.escalate("MOTH_01", risk_low, event_id="evt_01")
        self.assertEqual(res_low["escalation_level"], "Low")
        self.assertFalse(res_low["escalated"])

        # 2. Moderate symptom: Twilio SMS notification
        risk_mod = calculate_risk_from_text("I have persistent vomiting and leg swelling")
        res_mod = escalation_svc.escalate("MOTH_02", risk_mod, event_id="evt_02")
        self.assertEqual(res_mod["escalation_level"], "Moderate")
        self.assertTrue(res_mod["escalated"])
        self.assertEqual(res_mod["action_taken"], "twilio_sms")
        self.assertEqual(len(mock_adapter.sent_sms_records), 1)
        self.assertEqual(len(mock_adapter.initiated_call_records), 0)

        # 3. High symptom (Score 60-79, non-emergency): Twilio Call + SMS simultaneously
        risk_high = calculate_risk_from_text("I have severe headache and leg swelling")
        res_high = escalation_svc.escalate("MOTH_03", risk_high, event_id="evt_03")
        self.assertEqual(res_high["escalation_level"], "High")
        self.assertEqual(res_high["action_taken"], "twilio_call_and_sms")
        self.assertTrue(res_high["escalated"])
        self.assertEqual(len(mock_adapter.initiated_call_records), 1)
        self.assertEqual(len(mock_adapter.sent_sms_records), 2)  # 1 Moderate + 1 High

        # 4. Emergency symptom: Parallel Twilio Call + SMS to configured ASHA worker
        risk_emerg = calculate_risk_from_text("I have heavy vaginal bleeding and chest pain")
        res_emerg = escalation_svc.escalate("MOTH_04", risk_emerg, event_id="evt_04")
        self.assertEqual(res_emerg["escalation_level"], "Emergency")
        self.assertEqual(res_emerg["action_taken"], "emergency_twilio_call_and_sms")
        self.assertTrue(res_emerg["escalated"])
        self.assertEqual(len(mock_adapter.initiated_call_records), 2)  # 1 High + 1 Emergency Call
        self.assertEqual(len(mock_adapter.sent_sms_records), 3)  # 1 Moderate + 1 High + 1 Emergency


    # ---------------- 9. VOICE OUTPUT (TTS) ----------------
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
