"""
Centralized Phone Number Validation and Normalization Utility for MathriSurakshaAI.
Handles strict E.164 formatting for Twilio SMS & Voice, and privacy masking for logs.
"""

import re
from typing import Optional


def clean_phone_number(phone: Optional[str]) -> str:
    """
    Strip all non-numeric characters, spaces, hyphens, brackets,
    and common Indian prefixes (+91, 0091, 0) to produce a clean 10-digit mobile number.
    """
    if not phone:
        return ""
    
    # Remove all non-digits (spaces, dashes, parens, symbols)
    digits = re.sub(r'\D', '', str(phone).strip())

    # Handle international prefix 91 (if 12 digits starting with 91)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    # Handle leading 0091 prefix (if 14 digits)
    elif len(digits) == 14 and digits.startswith("0091"):
        digits = digits[4:]
    # Handle leading 0 prefix (if 11 digits starting with 0)
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]

    return digits


def validate_phone_number(phone: Optional[str]) -> bool:
    """
    Validate that the phone number is a valid 10-digit Indian mobile number (starts with 6, 7, 8, or 9)
    or a valid E.164 international phone number.
    """
    if not phone:
        return False
    
    raw = str(phone).strip()
    # Check if standard Indian 10-digit mobile
    cleaned = clean_phone_number(raw)
    if len(cleaned) == 10 and cleaned[0] in ['6', '7', '8', '9']:
        return True
    
    # Check if already E.164 international (e.g. +17372508034)
    digits = re.sub(r'\D', '', raw)
    if raw.startswith('+') and 10 <= len(digits) <= 15:
        return True

    return False


def format_for_twilio(phone: Optional[str], default_country_code: str = "+91") -> Optional[str]:
    """
    Format phone number to strict E.164 standard (e.g. '+917075287040' or '+17372508034').
    Returns None if phone is invalid.
    """
    if not phone:
        return None
    
    raw = str(phone).strip()
    
    # If already starts with '+', validate digit length
    if raw.startswith('+'):
        digits = re.sub(r'\D', '', raw)
        if 10 <= len(digits) <= 15:
            return f"+{digits}"
        return None
    
    # If standard 10-digit Indian mobile number
    cleaned = clean_phone_number(raw)
    if len(cleaned) == 10 and cleaned[0] in ['6', '7', '8', '9']:
        prefix = default_country_code if default_country_code.startswith('+') else f"+{default_country_code}"
        return f"{prefix}{cleaned}"
    
    # If 12 digits starting with 91
    digits = re.sub(r'\D', '', raw)
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
    
    # If 11 digits starting with 1 (US number)
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"

    return None


def mask_phone(phone: Optional[str]) -> str:
    """
    Mask phone number for safe logging without exposing personal data (e.g., '+91XXXXXX7040').
    """
    if not phone:
        return "[UNCONFIGURED]"
    
    formatted = format_for_twilio(phone)
    if formatted:
        if formatted.startswith("+91") and len(formatted) == 13:
            return f"+91{'X' * 6}{formatted[-4:]}"
        elif len(formatted) > 5:
            return f"{formatted[:3]}{'X' * (len(formatted) - 7)}{formatted[-4:]}"
        return f"+{'X' * (len(formatted) - 1)}"
    
    cleaned = clean_phone_number(phone)
    if len(cleaned) >= 4:
        return f"+91{'X' * (len(cleaned) - 4)}{cleaned[-4:]}"
    return "+91XXXX"
