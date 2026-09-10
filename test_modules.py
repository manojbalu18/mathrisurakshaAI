"""
Validation script for LM Studio Client, AI Service, Voice Service, TTS Service,
negation detection, Phone Utils, and ASHA Safety Escalation System with Twilio provider.
"""

import unittest
from unittest.mock import patch, MagicMock
from lm_studio_client import LMStudioClient
from ai_service import AIService
from voice_service import VoiceService
from tts_service import TTSService
from phone_utils import (
    clean_phone_number,
    validate_phone_number,
    format_for_twilio,
    mask_phone
)
from escalation_service import (
    EscalationService,
    MockTelephonyAdapter,
    TwilioProvider,
    BaseTelephonyAdapter,
    build_escalation_sms_message,
    build_escalation_call_message
)


class TestIntegrationModules(unittest.TestCase):

    def test_lm_studio_client_offline_behavior(self):
        client = LMStudioClient(base_url="http://127.0.0.1:54321/v1", timeout=1)
        status = client.check_connection(timeout=0.5)
        self.assertFalse(status["online"])
        self.assertTrue("Cannot connect" in status["message"] or "timed out" in status["message"])

    def test_emergency_override(self):
        service = AIService()
        self.assertTrue(service.check_emergency("I have severe bleeding and chest pain"))
        self.assertFalse(service.check_emergency("Can I drink milk with almonds?"))

        result = service.process_message("I am experiencing bleeding and feeling dizzy", language_name="English")
        self.assertTrue(result["is_emergency"])
        self.assertEqual(result["source"], "emergency_override")
        self.assertIn("CRITICAL ALERT", result["response"])

    def test_fallback_knowledge_base(self):
        service = AIService()
        resp = service.get_fallback_response("Can I eat papaya?")
        self.assertIn("papaya", resp.lower())

        resp_diet = service.get_fallback_response("What food should I eat for iron?")
        self.assertIn("iron", resp_diet.lower())

    def test_tts_service(self):
        tts = TTSService()
        cleaned = tts.clean_text_for_speech("### Hello **World**! 👶 [Link](http://example.com)")
        self.assertEqual(cleaned, "Hello World! Link")

        # Test synthesis of simple sentence
        audio = tts.synthesize("Drink plenty of clean water every day.", "English")
        self.assertIsNotNone(audio)
        self.assertGreater(len(audio), 100)

    def test_voice_service_language_mapping(self):
        vs = VoiceService()
        self.assertEqual(vs.get_stt_language_code("Hindi"), "hi-IN")
        self.assertEqual(vs.get_stt_language_code("Telugu"), "te-IN")
        self.assertEqual(vs.get_stt_language_code("English"), "en-IN")

    def test_service_with_context(self):
        service = AIService()
        result = service.process_message(
            "What can I eat today?",
            user_context={"risk_level": "High", "mother_name": "Pooja"},
            language_name="English"
        )
        self.assertIn("High Risk", result["response"])

    def test_translation_integration(self):
        service = AIService()
        translated = service.translate_text("Hello mother", "Hindi")
        self.assertTrue(len(translated) > 0)

    def test_heart_attack_emergency_override(self):
        service = AIService()
        self.assertTrue(service.check_emergency("I am having a heart attack"))
        self.assertTrue(service.check_emergency("Severe chest pain and can't breathe"))
        
        result = service.process_message("I am having a heart attack", language_name="English")
        self.assertTrue(result["is_emergency"])
        self.assertEqual(result["source"], "emergency_override")
        self.assertIn("CRITICAL ALERT", result["response"])

    def test_language_detection(self):
        service = AIService()
        self.assertEqual(service.detect_language("Hello, how are you?", "English"), "English")
        self.assertEqual(service.detect_language("నమస్కారం, మీరు ఎలా ఉన్నారు?", "English"), "Telugu")
        self.assertEqual(service.detect_language("नमस्ते, आप कैसे हैं?", "English"), "Hindi")
        self.assertEqual(service.detect_language("வணக்கம், எப்படி இருக்கிறீர்கள்?", "English"), "Tamil")

    def test_clinical_risk_heart_attack_and_symptoms(self):
        from ai_engine import calculate_risk_from_text
        
        # Test 1: Heart attack must trigger High Risk & Emergency
        res_ha = calculate_risk_from_text("I am having a heart attack")
        self.assertGreaterEqual(res_ha["risk_score"], 80)
        self.assertEqual(res_ha["risk_level"], "High")
        self.assertTrue(res_ha["is_emergency"])
        self.assertTrue(res_ha["escalation"])

        # Test 2: Low risk symptom
        res_low = calculate_risk_from_text("I feel a little tired today")
        self.assertLess(res_low["risk_score"], 30)
        self.assertEqual(res_low["risk_level"], "Low")
        self.assertFalse(res_low["escalation"])

        # Test 3: Moderate symptoms produce moderate score
        res_mod = calculate_risk_from_text("I have a headache and swelling in legs")
        self.assertGreaterEqual(res_mod["risk_score"], 30)
        self.assertLess(res_mod["risk_score"], 60)
        self.assertEqual(res_mod["risk_level"], "Medium")

        # Test 4: Multilingual symptom extraction (Telugu)
        res_te = calculate_risk_from_text("నాకు విపరీతమైన రక్తస్రావం అవుతోంది")
        self.assertGreaterEqual(res_te["risk_score"], 60)
        self.assertEqual(res_te["risk_level"], "High")

    # ---------------- PHONE UTILITIES TESTS ----------------
    def test_phone_utils(self):
        self.assertEqual(clean_phone_number("+91 7075287040"), "7075287040")
        self.assertEqual(clean_phone_number("07075287040"), "7075287040")
        self.assertTrue(validate_phone_number("7075287040"))
        self.assertFalse(validate_phone_number("12345"))
        self.assertEqual(format_for_twilio("7075287040"), "+917075287040")
        self.assertEqual(format_for_twilio("+17372508034"), "+17372508034")
        self.assertEqual(mask_phone("+917075287040"), "+91XXXXXX7040")

    # ---------------- NEGATION DETECTION TESTS ----------------
    def test_negation_handling_in_clinical_risk(self):
        """Negated symptoms like 'I do not have chest pain' must NOT be extracted as emergency symptoms."""
        from ai_engine import calculate_risk_from_text

        # Negated emergency symptom
        res_neg = calculate_risk_from_text("I do not have chest pain and no bleeding")
        self.assertLess(res_neg["risk_score"], 30)
        self.assertEqual(res_neg["risk_level"], "Low")
        self.assertFalse(res_neg["is_emergency"])

        # Actual emergency symptom
        res_pos = calculate_risk_from_text("I have severe chest pain and heavy bleeding")
        self.assertGreaterEqual(res_pos["risk_score"], 80)
        self.assertTrue(res_pos["is_emergency"])

        # Negated moderate symptom
        res_neg_mod = calculate_risk_from_text("I do not have fever or vomiting")
        self.assertLess(res_neg_mod["risk_score"], 30)

    # ---------------- TWILIO PROVIDER TESTS (MOCKED SDK) ----------------
    @patch("escalation_service.Client")
    def test_twilio_sms_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_msg = MagicMock()
        mock_msg.sid = "SM_test_12345"
        mock_msg.status = "queued"
        mock_client.messages.create.return_value = mock_msg
        mock_client_cls.return_value = mock_client

        provider = TwilioProvider(
            account_sid="AC_test_account",
            auth_token="auth_token_test",
            phone_number="+17372508034"
        )
        res = provider.send_sms("+917075287040", "Test Emergency Alert")
        self.assertTrue(res["success"])
        self.assertEqual(res["provider"], "twilio")
        self.assertEqual(res["message_id"], "SM_test_12345")
        self.assertEqual(res["status"], "queued")
        self.assertIsNone(res["error"])

    @patch("escalation_service.Client")
    def test_twilio_call_success(self, mock_client_cls):
        mock_client = MagicMock()
        mock_call = MagicMock()
        mock_call.sid = "CA_test_98765"
        mock_call.status = "queued"
        mock_client.calls.create.return_value = mock_call
        mock_client_cls.return_value = mock_client

        provider = TwilioProvider(
            account_sid="AC_test_account",
            auth_token="auth_token_test",
            phone_number="+17372508034"
        )
        res = provider.initiate_call("+917075287040", "Emergency voice alert test")
        self.assertTrue(res["success"])
        self.assertEqual(res["provider"], "twilio")
        self.assertEqual(res["call_id"], "CA_test_98765")
        self.assertEqual(res["status"], "queued")
        self.assertIsNone(res["error"])

    # ---------------- ASHA WORKER ESCALATION POLICY TESTS ----------------
    def test_asha_escalation_low_risk_no_notification(self):
        """LOW RISK: No automatic SMS and no automatic Call."""
        mock_adapter = MockTelephonyAdapter()
        svc = EscalationService(adapter=mock_adapter)

        risk_res = {
            "risk_score": 15,
            "risk_level": "Low",
            "is_emergency": False,
            "extracted_symptoms": ["mild fatigue"]
        }
        res = svc.escalate("MOTH001", risk_res, event_id="evt_low_01")
        self.assertFalse(res["escalated"])
        self.assertEqual(res["action_taken"], "none")
        self.assertEqual(len(mock_adapter.sent_sms_records), 0)
        self.assertEqual(len(mock_adapter.initiated_call_records), 0)

    def test_asha_escalation_moderate_risk_twilio_sms(self):
        """MODERATE RISK: Automatically send SMS to configured ASHA worker."""
        mock_adapter = MockTelephonyAdapter()
        svc = EscalationService(adapter=mock_adapter)

        risk_res = {
            "risk_score": 35,
            "risk_level": "Medium",
            "is_emergency": False,
            "extracted_symptoms": ["headache", "swelling"]
        }
        res = svc.escalate("MOTH002", risk_res, event_id="evt_mod_01")
        self.assertTrue(res["escalated"])
        self.assertEqual(res["action_taken"], "twilio_sms")
        self.assertEqual(res["escalation_level"], "Moderate")
        self.assertEqual(len(mock_adapter.sent_sms_records), 1)
        self.assertEqual(len(mock_adapter.initiated_call_records), 0)
        self.assertIn("MEDIUM", mock_adapter.sent_sms_records[0]["message"])

    def test_asha_escalation_high_risk_call_and_sms(self):
        """HIGH RISK: Must execute BOTH voice call AND SMS simultaneously."""
        mock_adapter = MockTelephonyAdapter()
        svc = EscalationService(adapter=mock_adapter)

        risk_res = {
            "risk_score": 65,
            "risk_level": "High",
            "is_emergency": False,
            "extracted_symptoms": ["severe headache", "swelling"]
        }
        res = svc.escalate("MOTH003", risk_res, event_id="evt_high_01")
        self.assertTrue(res["escalated"])
        self.assertEqual(res["action_taken"], "twilio_call_and_sms")
        self.assertEqual(res["escalation_level"], "High")
        self.assertEqual(len(mock_adapter.initiated_call_records), 1)
        self.assertEqual(len(mock_adapter.sent_sms_records), 1)
        self.assertIn("EMERGENCY ALERT", mock_adapter.sent_sms_records[0]["message"])

    def test_asha_escalation_emergency_priority_and_parallel_notifications(self):
        """EMERGENCY: Triggers parallel voice call + SMS to configured ASHA worker."""
        mock_adapter = MockTelephonyAdapter()
        svc = EscalationService(adapter=mock_adapter)

        risk_res = {
            "risk_score": 85,
            "risk_level": "High",
            "is_emergency": True,
            "extracted_symptoms": ["heavy bleeding", "unconscious"]
        }
        res = svc.escalate("MOTH004", risk_res, event_id="evt_emerg_01")
        self.assertTrue(res["escalated"])
        self.assertEqual(res["escalation_level"], "Emergency")
        self.assertEqual(res["action_taken"], "emergency_twilio_call_and_sms")
        self.assertEqual(len(mock_adapter.initiated_call_records), 1)
        self.assertEqual(len(mock_adapter.sent_sms_records), 1)
        self.assertIn("EMERGENCY ALERT", mock_adapter.sent_sms_records[0]["message"])

    def test_asha_escalation_duplicate_prevention(self):
        """Streamlit reruns with the same event ID must NOT trigger repeated SMS or calls."""
        mock_adapter = MockTelephonyAdapter()
        svc = EscalationService(adapter=mock_adapter)

        risk_res = {
            "risk_score": 40,
            "risk_level": "Medium",
            "is_emergency": False,
            "extracted_symptoms": ["vomiting"]
        }
        # First execution: should escalate
        res1 = svc.escalate("MOTH005", risk_res, event_id="evt_dup_test")
        self.assertTrue(res1["escalated"])
        self.assertEqual(len(mock_adapter.sent_sms_records), 1)

        # Second execution (Streamlit rerun): must be ignored
        res2 = svc.escalate("MOTH005", risk_res, event_id="evt_dup_test")
        self.assertFalse(res2["escalated"])
        self.assertEqual(res2["reason"], "already_escalated")
        self.assertEqual(len(mock_adapter.sent_sms_records), 1)

    def test_telephony_provider_failure_resilience(self):
        """Telephony failure must not crash the application or modify the clinical risk classification."""
        failing_adapter = MockTelephonyAdapter(should_fail_call=True, should_fail_sms=True)
        svc = EscalationService(adapter=failing_adapter)

        risk_res = {
            "risk_score": 75,
            "risk_level": "High",
            "is_emergency": False,
            "extracted_symptoms": ["severe abdominal pain"]
        }
        res = svc.escalate("MOTH006", risk_res, event_id="evt_fail_test")
        self.assertIsNotNone(res)
        self.assertEqual(res["escalation_level"], "High")
        self.assertEqual(risk_res["risk_level"], "High")

    def test_missing_credentials_handling_no_fake_success(self):
        """When credentials are missing, real providers must return config_error and NOT fake success."""
        twilio_unconfigured = TwilioProvider(account_sid="", auth_token="", phone_number="")
        sms_res = twilio_unconfigured.send_sms("+917075287040", "Test alert")
        self.assertFalse(sms_res["success"])
        self.assertEqual(sms_res["status"], "config_error")

        call_res = twilio_unconfigured.initiate_call("+917075287040", "Test call")
        self.assertFalse(call_res["success"])
        self.assertEqual(call_res["status"], "config_error")


if __name__ == "__main__":
    unittest.main()
