"""
Twilio Telephony and Safety Escalation Service for MAATRI SURAKSHA AI.
Provides emergency SMS alerts and outbound voice calls using the official Twilio SDK.

Supports both Twilio Trial Mode (predefined templates & approved voice URLs)
and Full Production Mode (dynamic maternal emergency messages & custom TwiML).
"""

import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Set, List, Union

try:
    from twilio.rest import Client
    from twilio.base.exceptions import TwilioRestException
    from twilio.twiml.voice_response import VoiceResponse, Say
    TWILIO_AVAILABLE = True
except ImportError:
    Client = None
    TwilioRestException = Exception
    VoiceResponse = None
    Say = None
    TWILIO_AVAILABLE = False

import config
from phone_utils import (
    clean_phone_number,
    validate_phone_number,
    format_for_twilio,
    mask_phone
)
from database import log_live_sms, log_live_call

logger = logging.getLogger(__name__)


# ---------------- STANDARDIZED RESULT BUILDER ----------------
def create_telephony_result(
    service: str,
    success: bool,
    status: str,
    error_type: Optional[str] = None,
    message: Optional[str] = None,
    provider_error_code: Optional[Union[int, str]] = None,
    message_id: Optional[str] = None,
    call_id: Optional[str] = None,
    error: Optional[str] = None,
    trial_mode: bool = True,
    provider: str = "twilio",
    timestamp: Optional[str] = None
) -> Dict[str, Any]:
    """Build a consistent, structured communication result dictionary."""
    ts = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ref_id = message_id or call_id
    default_msg = "Communication accepted." if success else str(error or "Communication failed.")
    return {
        "success": bool(success),
        "service": str(service),
        "status": str(status),
        "error_type": str(error_type or ("none" if success else status)),
        "message": str(message or default_msg),
        "provider_error_code": provider_error_code,
        "provider": str(provider),
        "trial_mode": bool(trial_mode),
        "message_id": message_id,
        "call_id": call_id,
        "provider_ref": ref_id,
        "error": error,
        "timestamp": ts
    }


# ---------------- BASE TELEPHONY ADAPTER ----------------
class BaseTelephonyAdapter:
    """Base interface for telephony providers (SMS and Voice Calling)."""

    def send_sms(self, to_phone: str, message: str) -> Dict[str, Any]:
        raise NotImplementedError

    def initiate_call(self, to_phone: str, message: str) -> Dict[str, Any]:
        raise NotImplementedError


# ---------------- MOCK TELEPHONY ADAPTER (FOR TESTING ONLY) ----------------
class MockTelephonyAdapter(BaseTelephonyAdapter):
    """Simulated telephony adapter for testing and test isolation."""

    def __init__(self, should_fail_call: bool = False, should_fail_sms: bool = False):
        self.should_fail_call = should_fail_call
        self.should_fail_sms = should_fail_sms
        self.sent_sms_records = []
        self.initiated_call_records = []

    def send_sms(self, to_phone: str, message: str) -> Dict[str, Any]:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if self.should_fail_sms:
            return create_telephony_result(
                service="sms",
                success=False,
                status="failed",
                error_type="simulated_failure",
                message="Simulated SMS provider rejection",
                error="Simulated SMS provider rejection",
                provider="mock",
                trial_mode=False,
                timestamp=ts
            )

        ref = f"mock-sms-{len(self.sent_sms_records) + 1}"
        record = {
            "to": to_phone,
            "message": message,
            "timestamp": ts,
            "provider_ref": ref
        }
        self.sent_sms_records.append(record)
        return create_telephony_result(
            service="sms",
            success=True,
            status="accepted",
            error_type="none",
            message="Mock SMS delivered successfully.",
            message_id=ref,
            provider="mock",
            trial_mode=False,
            timestamp=ts
        )

    def initiate_call(self, to_phone: str, message: str) -> Dict[str, Any]:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if self.should_fail_call:
            return create_telephony_result(
                service="call",
                success=False,
                status="failed",
                error_type="simulated_failure",
                message="Simulated Voice Call provider failure",
                error="Simulated Voice Call provider failure",
                provider="mock",
                trial_mode=False,
                timestamp=ts
            )

        ref = f"mock-call-{len(self.initiated_call_records) + 1}"
        record = {
            "to": to_phone,
            "message": message,
            "timestamp": ts,
            "provider_ref": ref
        }
        self.initiated_call_records.append(record)
        return create_telephony_result(
            service="call",
            success=True,
            status="initiated",
            error_type="none",
            message="Mock Call initiated successfully.",
            call_id=ref,
            provider="mock",
            trial_mode=False,
            timestamp=ts
        )


# ---------------- REUSABLE MESSAGE BUILDERS ----------------
def build_escalation_sms_message(
    risk_level: str,
    risk_score: int = 0,
    symptoms: Optional[List[str]] = None,
    timestamp: Optional[str] = None
) -> str:
    """Build standardized emergency SMS alert messages for ASHA workers."""
    symptom_str = ", ".join(symptoms) if symptoms else "Maternal health alert"
    ts = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    level_norm = str(risk_level).upper()

    if level_norm in ["EMERGENCY", "CRITICAL", "HIGH"]:
        return (
            f"🚨 MAATRI SURAKSHA AI EMERGENCY ALERT\n\n"
            f"A high-risk medical emergency has been detected.\n\n"
            f"Patient-reported symptoms:\n{symptom_str}\n\n"
            f"Risk Level: {level_norm}\n"
            f"Risk Score: {risk_score}\n"
            f"Time: {ts}\n\n"
            f"Immediate medical attention may be required.\n\n"
            f"Please contact the patient or provide emergency assistance immediately."
        )
    else:  # MEDIUM / MODERATE
        return (
            f"⚠️ MAATRI SURAKSHA AI ALERT\n\n"
            f"A moderate-risk health concern has been detected.\n\n"
            f"Patient-reported symptoms:\n{symptom_str}\n\n"
            f"Risk Level: {level_norm}\n"
            f"Risk Score: {risk_score}\n"
            f"Time: {ts}\n\n"
            f"Please follow up with the patient promptly."
        )


def build_escalation_call_message(
    risk_level: str,
    symptoms: Optional[List[str]] = None,
    timestamp: Optional[str] = None
) -> str:
    """Build emergency voice message spoken during Twilio outbound calls."""
    symptom_str = ", ".join(symptoms) if symptoms else "maternal health symptoms"
    level_norm = str(risk_level).capitalize()
    
    return (
        f"Emergency alert from Maatri Suraksha AI. "
        f"A {level_norm} risk medical condition has been detected. "
        f"Reported symptoms are: {symptom_str}. "
        f"Immediate medical attention may be required. "
        f"Please contact the patient immediately."
    )


# ---------------- TWILIO TELEPHONY PROVIDER ----------------
class TwilioProvider(BaseTelephonyAdapter):
    """
    Production & Trial Twilio Telephony Provider.
    Supports both Twilio Trial Mode (predefined template & sample webhook)
    and Production Mode (dynamic SMS text & custom TwiML voice response).
    """

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        phone_number: Optional[str] = None,
        trial_mode: Optional[bool] = None,
        trial_sms_template: Optional[str] = None,
        trial_voice_url: Optional[str] = None
    ):
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._phone_number = phone_number
        self._trial_mode = trial_mode
        self._trial_sms_template = trial_sms_template
        self._trial_voice_url = trial_voice_url

    @property
    def account_sid(self) -> str:
        if self._account_sid is not None:
            return self._account_sid
        config.load_project_env()
        return getattr(config, "TWILIO_ACCOUNT_SID", os.getenv("TWILIO_ACCOUNT_SID", ""))

    @property
    def auth_token(self) -> str:
        if self._auth_token is not None:
            return self._auth_token
        config.load_project_env()
        return getattr(config, "TWILIO_AUTH_TOKEN", os.getenv("TWILIO_AUTH_TOKEN", ""))

    @property
    def phone_number(self) -> str:
        if self._phone_number is not None:
            return self._phone_number
        config.load_project_env()
        return getattr(config, "TWILIO_PHONE_NUMBER", os.getenv("TWILIO_PHONE_NUMBER", ""))

    @property
    def trial_mode(self) -> bool:
        if self._trial_mode is not None:
            return self._trial_mode
        config.load_project_env()
        val = getattr(config, "TWILIO_TRIAL_MODE", os.getenv("TWILIO_TRIAL_MODE", "true"))
        if isinstance(val, bool):
            return val
        return str(val).lower() in ["true", "1", "yes"]

    @property
    def trial_sms_template(self) -> str:
        if self._trial_sms_template is not None:
            return self._trial_sms_template
        config.load_project_env()
        return getattr(config, "TWILIO_TRIAL_SMS_TEMPLATE", os.getenv("TWILIO_TRIAL_SMS_TEMPLATE", "sms_internal_alerts"))

    @property
    def trial_voice_url(self) -> str:
        if self._trial_voice_url is not None:
            return self._trial_voice_url
        config.load_project_env()
        return getattr(
            config,
            "TWILIO_TRIAL_VOICE_URL",
            os.getenv("TWILIO_TRIAL_VOICE_URL", "https://webhooks.twilio.com/v1/Voice/Template/voice_text_to_speech")
        )

    def validate_configuration(self) -> tuple[bool, str, str]:
        """
        Validate Twilio configuration settings.
        Returns: (is_valid, error_type, description)
        """
        placeholders = ["", "your_twilio_account_sid_here", "your_twilio_auth_token_here", "your_twilio_phone_number_here"]
        sid = (self.account_sid or "").strip()
        token = (self.auth_token or "").strip()
        phone = (self.phone_number or "").strip()

        if not sid or sid in placeholders or not token or token in placeholders:
            return False, "config_missing", "Twilio credentials (TWILIO_ACCOUNT_SID or TWILIO_AUTH_TOKEN) not configured in environment."

        if not phone or phone in placeholders:
            return False, "invalid_sender", "Twilio sender phone number (TWILIO_PHONE_NUMBER) not configured in environment."

        return True, "none", "Twilio configuration valid."

    def is_configured(self) -> bool:
        """Verify that all required Twilio credentials and phone number are present."""
        is_valid, _, _ = self.validate_configuration()
        return is_valid

    def _get_client(self) -> Client:
        """Create authenticated Twilio Client."""
        return Client(self.account_sid.strip(), self.auth_token.strip())

    def send_sms(self, to_phone: str, message: str) -> Dict[str, Any]:
        """
        Send an emergency SMS alert via Twilio Messages API.
        In Trial Mode: uses the trial-approved template (default: 'sms_internal_alerts').
        In Production Mode: sends the full dynamic maternal emergency message.
        """
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        is_trial = self.trial_mode

        # 1. Configuration Check
        is_valid_cfg, cfg_err_type, cfg_err_msg = self.validate_configuration()
        if not is_valid_cfg:
            logger.warning(f"Twilio SMS dispatch aborted: {cfg_err_msg}")
            return create_telephony_result(
                service="sms",
                success=False,
                status="config_error",
                error_type=cfg_err_type,
                message=cfg_err_msg,
                error=cfg_err_msg,
                trial_mode=is_trial,
                timestamp=ts
            )

        # 2. Destination Phone Formatting (E.164)
        dest_e164 = format_for_twilio(to_phone)
        if not dest_e164:
            masked = mask_phone(to_phone)
            logger.warning(f"Twilio SMS aborted: Invalid recipient phone number '{masked}'.")
            return create_telephony_result(
                service="sms",
                success=False,
                status="invalid_phone",
                error_type="invalid_phone",
                message=f"Invalid recipient phone number format: {masked}",
                error=f"Invalid recipient phone number format: {masked}",
                trial_mode=is_trial,
                timestamp=ts
            )

        # 3. Sender Phone Formatting (E.164)
        from_e164 = format_for_twilio(self.phone_number, default_country_code="+1")
        if not from_e164:
            logger.warning("Twilio SMS aborted: Invalid TWILIO_PHONE_NUMBER sender format.")
            return create_telephony_result(
                service="sms",
                success=False,
                status="invalid_sender",
                error_type="invalid_sender",
                message="Invalid Twilio sender phone number format in TWILIO_PHONE_NUMBER.",
                error="Invalid Twilio sender phone number format.",
                trial_mode=is_trial,
                timestamp=ts
            )

        masked_dest = mask_phone(dest_e164)
        masked_from = mask_phone(from_e164)

        # 4. Payload Selection based on Trial Mode
        sms_body = self.trial_sms_template if is_trial else message

        # 5. Twilio Messages API Execution
        try:
            mode_desc = f"Trial Template '{sms_body}'" if is_trial else "Production Dynamic Body"
            logger.info(f"Dispatching Twilio SMS ({mode_desc}) from {masked_from} to {masked_dest}...")
            client = self._get_client()
            msg = client.messages.create(
                body=sms_body,
                from_=from_e164,
                to=dest_e164
            )

            msg_sid = getattr(msg, "sid", "accepted")
            msg_status = getattr(msg, "status", "queued")
            logger.info(f"Twilio SMS accepted for {masked_dest} (SID: {msg_sid}, Status: {msg_status}, TrialMode: {is_trial}).")
            return create_telephony_result(
                service="sms",
                success=True,
                status=str(msg_status),
                error_type="none",
                message=f"Twilio SMS dispatched successfully (SID: {msg_sid}).",
                message_id=str(msg_sid),
                trial_mode=is_trial,
                timestamp=ts
            )

        except TwilioRestException as e:
            logger.error(f"Twilio API error sending SMS to {masked_dest} (Code {e.code}): {e.msg}")
            err_text = str(e.msg)
            code = getattr(e, "code", None)

            # Detect unverified recipient in trial account (Codes 572002, 21608, etc.)
            if code in [572002, 21608] or "verified recipient" in err_text.lower() or "unverified" in err_text.lower():
                user_msg = (
                    f"Destination number {masked_dest} is not verified in Twilio. "
                    f"Trial accounts can only send SMS to Verified Caller IDs. "
                    f"Please verify {masked_dest} in your Twilio Console (Phone Numbers -> Verified Caller IDs)."
                )
                return create_telephony_result(
                    service="sms",
                    success=False,
                    status="unverified_recipient",
                    error_type="unverified_recipient",
                    message=user_msg,
                    provider_error_code=code,
                    error=f"Twilio Error ({code}): {err_text}",
                    trial_mode=is_trial,
                    timestamp=ts
                )

            # Detect general trial account restrictions
            if code in [21215, 572006] or "trial account" in err_text.lower() or "disallowed parameters" in err_text.lower() or "template" in err_text.lower():
                user_msg = f"Twilio Trial Restriction: {err_text}. Verify recipient number or upgrade your Twilio account."
                return create_telephony_result(
                    service="sms",
                    success=False,
                    status="trial_restriction",
                    error_type="trial_restriction",
                    message=user_msg,
                    provider_error_code=code,
                    error=f"Twilio Trial Notice ({code}): {err_text}",
                    trial_mode=is_trial,
                    timestamp=ts
                )

            # Detect geographic permission restriction
            if code in [21408] or "permission" in err_text.lower() and "region" in err_text.lower():
                user_msg = f"Twilio Geo-Permission Restriction: Outbound messaging to {masked_dest} requires enabling Geographic Permissions in Twilio Console."
                return create_telephony_result(
                    service="sms",
                    success=False,
                    status="geo_permission_restriction",
                    error_type="geo_permission_restriction",
                    message=user_msg,
                    provider_error_code=code,
                    error=f"Twilio Error ({code}): {err_text}",
                    trial_mode=is_trial,
                    timestamp=ts
                )

            # General provider API rejection
            return create_telephony_result(
                service="sms",
                success=False,
                status="provider_rejected",
                error_type="provider_rejected",
                message=f"Twilio Error ({code}): {err_text}",
                provider_error_code=code,
                error=f"Twilio Error ({code}): {err_text}",
                trial_mode=is_trial,
                timestamp=ts
            )

        except Exception as e:
            logger.error(f"Twilio SMS dispatch exception: {str(e)}")
            return create_telephony_result(
                service="sms",
                success=False,
                status="error",
                error_type="system_error",
                message=f"SMS dispatch exception: {str(e)}",
                error=str(e),
                trial_mode=is_trial,
                timestamp=ts
            )

    def initiate_call(self, to_phone: str, message: str) -> Dict[str, Any]:
        """
        Initiate an outbound emergency voice call via Twilio Calls API.
        In Trial Mode: uses the approved sample webhook URL (https://webhooks.twilio.com/v1/Voice/Template/voice_text_to_speech).
        In Production Mode: generates custom dynamic TwiML with spoken symptoms and clinical guidance.
        """
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        is_trial = self.trial_mode

        # 1. Configuration Check
        is_valid_cfg, cfg_err_type, cfg_err_msg = self.validate_configuration()
        if not is_valid_cfg:
            logger.warning(f"Twilio voice call aborted: {cfg_err_msg}")
            return create_telephony_result(
                service="call",
                success=False,
                status="config_error",
                error_type=cfg_err_type,
                message=cfg_err_msg,
                error=cfg_err_msg,
                trial_mode=is_trial,
                timestamp=ts
            )

        # 2. Destination Phone Formatting (E.164)
        dest_e164 = format_for_twilio(to_phone)
        if not dest_e164:
            masked = mask_phone(to_phone)
            logger.warning(f"Twilio call aborted: Invalid destination phone number '{masked}'.")
            return create_telephony_result(
                service="call",
                success=False,
                status="invalid_phone",
                error_type="invalid_phone",
                message=f"Invalid recipient phone number format: {masked}",
                error=f"Invalid recipient phone number format: {masked}",
                trial_mode=is_trial,
                timestamp=ts
            )

        # 3. Sender Phone Formatting (E.164)
        from_e164 = format_for_twilio(self.phone_number, default_country_code="+1")
        if not from_e164:
            logger.warning("Twilio call aborted: Invalid TWILIO_PHONE_NUMBER caller format.")
            return create_telephony_result(
                service="call",
                success=False,
                status="invalid_sender",
                error_type="invalid_sender",
                message="Invalid Twilio sender phone number format in TWILIO_PHONE_NUMBER.",
                error="Invalid Twilio caller phone number format.",
                trial_mode=is_trial,
                timestamp=ts
            )

        masked_dest = mask_phone(dest_e164)
        masked_from = mask_phone(from_e164)

        # 4. Twilio Calls API Execution
        try:
            client = self._get_client()
            if is_trial:
                # Trial Mode: use approved sample voice webhook URL
                trial_url = self.trial_voice_url
                logger.info(f"Initiating Twilio call (Trial URL: {trial_url}) from {masked_from} to {masked_dest}...")
                call = client.calls.create(
                    url=trial_url,
                    from_=from_e164,
                    to=dest_e164
                )
            else:
                # Production Mode: generate dynamic custom TwiML
                response = VoiceResponse()
                response.say(message, voice='alice', language='en-IN')
                twiml_payload = str(response)
                logger.info(f"Initiating Twilio call (Production TwiML) from {masked_from} to {masked_dest}...")
                call = client.calls.create(
                    twiml=twiml_payload,
                    from_=from_e164,
                    to=dest_e164
                )

            call_sid = getattr(call, "sid", "accepted")
            call_status = getattr(call, "status", "queued")
            logger.info(f"Twilio call initiated for {masked_dest} (SID: {call_sid}, Status: {call_status}, TrialMode: {is_trial}).")
            return create_telephony_result(
                service="call",
                success=True,
                status=str(call_status),
                error_type="none",
                message=f"Twilio emergency call placed successfully (SID: {call_sid}).",
                call_id=str(call_sid),
                trial_mode=is_trial,
                timestamp=ts
            )

        except TwilioRestException as e:
            logger.error(f"Twilio API error placing call to {masked_dest} (Code {e.code}): {e.msg}")
            err_text = str(e.msg)
            code = getattr(e, "code", None)

            # Detect unverified recipient in trial account
            if code in [572002, 21608] or "verified recipient" in err_text.lower() or "unverified" in err_text.lower():
                user_msg = (
                    f"Destination number {masked_dest} is not verified in Twilio. "
                    f"Trial accounts can only call Verified Caller IDs. "
                    f"Please verify {masked_dest} in your Twilio Console (Phone Numbers -> Verified Caller IDs)."
                )
                return create_telephony_result(
                    service="call",
                    success=False,
                    status="unverified_recipient",
                    error_type="unverified_recipient",
                    message=user_msg,
                    provider_error_code=code,
                    error=f"Twilio Error ({code}): {err_text}",
                    trial_mode=is_trial,
                    timestamp=ts
                )

            # Detect trial account restrictions on outbound voice / custom TwiML (Code 0, 21215, etc.)
            if code in [0, 21215, 21608] or "trial account" in err_text.lower() or "disallowed parameters" in err_text.lower() or "limited parameter access" in err_text.lower():
                user_msg = (
                    f"Twilio Trial Restriction: Trial accounts have parameter and outbound calling limitations ({err_text}). "
                    f"Ensure {masked_dest} is added to Verified Caller IDs or upgrade your Twilio account."
                )
                return create_telephony_result(
                    service="call",
                    success=False,
                    status="trial_restriction",
                    error_type="trial_restriction",
                    message=user_msg,
                    provider_error_code=code,
                    error=f"Twilio Trial Notice ({code}): {err_text}",
                    trial_mode=is_trial,
                    timestamp=ts
                )

            # General provider API rejection
            return create_telephony_result(
                service="call",
                success=False,
                status="provider_rejected",
                error_type="provider_rejected",
                message=f"Twilio Call Error ({code}): {err_text}",
                provider_error_code=code,
                error=f"Twilio Error ({code}): {err_text}",
                trial_mode=is_trial,
                timestamp=ts
            )

        except Exception as e:
            logger.error(f"Twilio call dispatch exception: {str(e)}")
            return create_telephony_result(
                service="call",
                success=False,
                status="error",
                error_type="system_error",
                message=f"Call dispatch exception: {str(e)}",
                error=str(e),
                trial_mode=is_trial,
                timestamp=ts
            )


# ---------------- CENTRAL ESCALATION SERVICE ----------------
class EscalationService:
    """
    Central safety escalation engine for MAATRI SURAKSHA AI.
    Orchestrates deterministic notification routing to ASHA workers using Twilio.
    """

    def __init__(
        self,
        adapter: Optional[BaseTelephonyAdapter] = None,
        sms_adapter: Optional[BaseTelephonyAdapter] = None,
        call_adapter: Optional[BaseTelephonyAdapter] = None
    ):
        if adapter:
            self.sms_adapter = adapter
            self.call_adapter = adapter
        else:
            twilio_provider = TwilioProvider()
            self.sms_adapter = sms_adapter or twilio_provider
            self.call_adapter = call_adapter or twilio_provider

        self._escalated_event_ids: Set[str] = set()

    def is_already_escalated(self, event_id: str) -> bool:
        """Check if a specific clinical event ID has already triggered escalation."""
        if not event_id:
            return False
        return event_id in self._escalated_event_ids

    def mark_escalated(self, event_id: str):
        """Register that a clinical event ID has been escalated to prevent rerun duplicates."""
        if event_id:
            self._escalated_event_ids.add(event_id)

    def escalate(
        self,
        mother_id: str,
        risk_result: Dict[str, Any],
        event_id: Optional[str] = None,
        user_context: Optional[Dict[str, Any]] = None,
        language: str = "English"
    ) -> Dict[str, Any]:
        """
        Execute safety escalation according to strict clinical risk tiers:
        
        LOW RISK:
        - No SMS, no Call. Normal AI voice guidance.

        MEDIUM RISK:
        - Emergency SMS to configured ASHA worker via Twilio. No automated call.

        HIGH RISK:
        - Emergency SMS + Emergency Outbound Call to configured ASHA worker via Twilio.

        EMERGENCY / CRITICAL:
        - Emergency SMS + Emergency Outbound Call to configured ASHA worker via Twilio.
        - Immediate emergency UI guidance directs caregiver to dial 108.
        """
        user_context = user_context or {}
        risk_level = risk_result.get("risk_level", "Low")
        risk_score = risk_result.get("risk_score", 0)
        is_emergency = risk_result.get("is_emergency", False) or risk_score >= 80
        symptoms = risk_result.get("extracted_symptoms", [])
        timestamp = risk_result.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. Deduplication / Idempotency Check
        if event_id and self.is_already_escalated(event_id):
            logger.debug(f"Skipping duplicate escalation for event {event_id}")
            return {
                "escalated": False,
                "action_taken": "none",
                "reason": "already_escalated",
                "escalation_level": "Duplicate",
                "sms_status": None,
                "call_status": None,
                "error": None
            }

        # 2. Check if ASHA escalation is enabled
        escalation_enabled = getattr(config, "ASHA_ESCALATION_ENABLED", True)
        if isinstance(escalation_enabled, str):
            escalation_enabled = escalation_enabled.lower() in ["true", "1", "yes"]

        if not escalation_enabled:
            logger.info("ASHA escalation is disabled in configuration.")
            return {
                "escalated": False,
                "action_taken": "disabled",
                "reason": "escalation_disabled_in_config",
                "escalation_level": "Disabled",
                "sms_status": None,
                "call_status": None,
                "error": None
            }

        asha_phone = getattr(config, "ASHA_WORKER_PHONE", os.getenv("ASHA_WORKER_PHONE", "7075287040"))
        if not asha_phone or not str(asha_phone).strip():
            asha_phone = "7075287040"

        # ---------------- TIER 1: LOW RISK ----------------
        if risk_level == "Low" and risk_score < 30 and not is_emergency:
            return {
                "escalated": False,
                "action_taken": "none",
                "escalation_level": "Low",
                "sms_status": None,
                "call_status": None,
                "error": None
            }

        # ---------------- TIER 2: MEDIUM RISK (SMS ONLY) ----------------
        if (risk_level == "Medium" or (30 <= risk_score < 60)) and not is_emergency:
            sms_message = build_escalation_sms_message("MEDIUM", risk_score, symptoms, timestamp)
            sms_res = self.sms_adapter.send_sms(asha_phone, sms_message)

            try:
                mode_tag = "Trial" if sms_res.get("trial_mode") else "Live"
                if sms_res.get("success"):
                    self.mark_escalated(event_id)
                    log_live_sms(mother_id, asha_phone, sms_message, f"Success ({mode_tag})", timestamp)
                else:
                    log_live_sms(mother_id, asha_phone, sms_message, f"Failed: {sms_res.get('status')} ({mode_tag})", timestamp)
            except Exception:
                pass

            return {
                "escalated": sms_res.get("success", False),
                "action_taken": "twilio_sms",
                "escalation_level": "Moderate",
                "sms_status": sms_res,
                "call_status": None,
                "error": sms_res.get("error")
            }

        # ---------------- TIER 3: HIGH RISK (SMS + VOICE CALL) ----------------
        if risk_level == "High" and not is_emergency:
            sms_message = build_escalation_sms_message("HIGH", risk_score, symptoms, timestamp)
            call_message = build_escalation_call_message("HIGH", symptoms, timestamp)

            # 1. Twilio Outbound Emergency Call
            call_res = self.call_adapter.initiate_call(asha_phone, call_message)
            try:
                mode_tag = "Trial" if call_res.get("trial_mode") else "Live"
                if call_res.get("success"):
                    log_live_call(mother_id, asha_phone, call_res.get("call_id", ""), f"{mode_tag}-Initiated", timestamp)
                else:
                    log_live_call(mother_id, asha_phone, "failed", f"Failed: {call_res.get('status')} ({mode_tag})", timestamp)
            except Exception:
                pass

            # 2. Twilio Emergency SMS
            sms_res = self.sms_adapter.send_sms(asha_phone, sms_message)
            try:
                mode_tag = "Trial" if sms_res.get("trial_mode") else "Live"
                if sms_res.get("success"):
                    log_live_sms(mother_id, asha_phone, sms_message, f"Success ({mode_tag})", timestamp)
                else:
                    log_live_sms(mother_id, asha_phone, sms_message, f"Failed: {sms_res.get('status')} ({mode_tag})", timestamp)
            except Exception:
                pass

            if (call_res and call_res.get("success")) or (sms_res and sms_res.get("success")):
                self.mark_escalated(event_id)

            return {
                "escalated": bool((call_res and call_res.get("success")) or (sms_res and sms_res.get("success"))),
                "action_taken": "twilio_call_and_sms",
                "escalation_level": "High",
                "call_status": call_res,
                "sms_status": sms_res,
                "error": call_res.get("error") or sms_res.get("error") if (call_res and sms_res) else None
            }

        # ---------------- TIER 4: EMERGENCY / CRITICAL (SMS + VOICE CALL) ----------------
        sms_message = build_escalation_sms_message("EMERGENCY", risk_score, symptoms, timestamp)
        call_message = build_escalation_call_message("EMERGENCY", symptoms, timestamp)

        # 1. Twilio Outbound Emergency Call
        call_res = self.call_adapter.initiate_call(asha_phone, call_message)
        try:
            mode_tag = "Trial" if call_res.get("trial_mode") else "Live"
            if call_res.get("success"):
                log_live_call(mother_id, asha_phone, call_res.get("call_id", ""), f"Emergency-{mode_tag}-Initiated", timestamp)
            else:
                log_live_call(mother_id, asha_phone, "failed", f"Emergency-Failed: {call_res.get('status')} ({mode_tag})", timestamp)
        except Exception:
            pass

        # 2. Twilio Emergency SMS
        sms_res = self.sms_adapter.send_sms(asha_phone, sms_message)
        try:
            mode_tag = "Trial" if sms_res.get("trial_mode") else "Live"
            if sms_res.get("success"):
                log_live_sms(mother_id, asha_phone, sms_message, f"Emergency-Success ({mode_tag})", timestamp)
            else:
                log_live_sms(mother_id, asha_phone, sms_message, f"Emergency-Failed: {sms_res.get('status')} ({mode_tag})", timestamp)
        except Exception:
            pass

        if (call_res and call_res.get("success")) or (sms_res and sms_res.get("success")):
            self.mark_escalated(event_id)

        return {
            "escalated": bool((call_res and call_res.get("success")) or (sms_res and sms_res.get("success"))),
            "action_taken": "emergency_twilio_call_and_sms",
            "escalation_level": "Emergency",
            "call_status": call_res,
            "sms_status": sms_res,
            "error": call_res.get("error") or sms_res.get("error") if (call_res and sms_res) else None
        }
