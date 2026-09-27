"""
Universal Translation Service for Maatri Suraksha AI
Supports 100% full-app translation across all Indian and international languages.
Combines pre-compiled dictionaries, dynamic on-the-fly AI translation with fast disk/memory caching,
and DOM Google Translate Bridge for client-side Streamlit UI elements.
"""

import os
import json
import threading
from typing import Dict, Any, Optional
import streamlit as st
import streamlit.components.v1 as components

# Import pre-compiled translations dictionary
try:
    from translations import TRANSLATIONS
except ImportError:
    TRANSLATIONS = {"English": {}}

# Language Configuration with ISO codes and Native Scripts
LANGUAGE_CONFIG = {
    "English": {"code": "en", "native": "English", "flag": "🇬🇧"},
    "Telugu": {"code": "te", "native": "తెలుగు", "flag": "🇮🇳"},
    "Hindi": {"code": "hi", "native": "हिन्दी", "flag": "🇮🇳"},
    "Tamil": {"code": "ta", "native": "தமிழ்", "flag": "🇮🇳"},
    "Kannada": {"code": "kn", "native": "ಕನ್ನಡ", "flag": "🇮🇳"},
    "Malayalam": {"code": "ml", "native": "മലയാളം", "flag": "🇮🇳"},
    "Bengali": {"code": "bn", "native": "বাংলা", "flag": "🇮🇳"},
    "Marathi": {"code": "mr", "native": "मराठी", "flag": "🇮🇳"},
    "Gujarati": {"code": "gu", "native": "ગુજરાતી", "flag": "🇮🇳"},
    "Odia": {"code": "or", "native": "ଓଡ଼ିଆ", "flag": "🇮🇳"},
    "Punjabi": {"code": "pa", "native": "ਪੰਜਾਬੀ", "flag": "🇮🇳"},
    "Urdu": {"code": "ur", "native": "اردو", "flag": "🇮🇳"},
    "Assamese": {"code": "as", "native": "অসমীয়া", "flag": "🇮🇳"},
    "Nepali": {"code": "ne", "native": "नेपाली", "flag": "🇳🇵"},
    "Sanskrit": {"code": "sa", "native": "संस्कृतम्", "flag": "🇮🇳"},
    "Spanish": {"code": "es", "native": "Español", "flag": "🇪🇸"},
    "French": {"code": "fr", "native": "Français", "flag": "🇫🇷"},
    "Arabic": {"code": "ar", "native": "العربية", "flag": "🇸🇦"},
    "German": {"code": "de", "native": "Deutsch", "flag": "🇩🇪"},
    "Russian": {"code": "ru", "native": "Русский", "flag": "🇷🇺"},
    "Portuguese": {"code": "pt", "native": "Português", "flag": "🇵🇹"},
    "Japanese": {"code": "ja", "native": "日本語", "flag": "🇯🇵"},
    "Chinese": {"code": "zh-CN", "native": "中文 (简体)", "flag": "🇨🇳"},
}

SUPPORTED_LANGUAGES = list(LANGUAGE_CONFIG.keys())

# Cache file path
CACHE_FILE = os.path.join(os.path.dirname(__file__), "dynamic_translation_cache.json")
_CACHE_LOCK = threading.Lock()
_CACHE: Dict[str, Dict[str, str]] = {}

def _load_cache():
    global _CACHE
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                _CACHE = json.load(f)
        except Exception:
            _CACHE = {}
    else:
        _CACHE = {}

_load_cache()

def _save_cache():
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_CACHE, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def get_lang_code(lang_name: str) -> str:
    """Get the ISO 639-1 language code for a language name."""
    if lang_name in LANGUAGE_CONFIG:
        return LANGUAGE_CONFIG[lang_name]["code"]
    # Fallback search
    for name, data in LANGUAGE_CONFIG.items():
        if lang_name.lower() in name.lower() or data["native"].lower() in lang_name.lower():
            return data["code"]
    return "en"

def get_language_display_labels():
    """Return formatted list of language options with flags and native names."""
    return [f"{cfg['flag']} {name} ({cfg['native']})" for name, cfg in LANGUAGE_CONFIG.items()]

def get_clean_language_name(formatted_label: str) -> str:
    """Extract standard language name from formatted label."""
    for name in LANGUAGE_CONFIG.keys():
        if name in formatted_label:
            return name
    return "English"

def translate_text(text: str, target_lang_name: str, src: str = "en") -> str:
    """
    Translate dynamic text or sentence on the fly using mtranslate with in-memory & disk caching.
    """
    if not text or not isinstance(text, str):
        return text
    
    target_code = get_lang_code(target_lang_name)
    if target_code == "en" or target_lang_name == "English":
        return text

    # Check in-memory cache
    with _CACHE_LOCK:
        if target_lang_name in _CACHE and text in _CACHE[target_lang_name]:
            return _CACHE[target_lang_name][text]

    # Translate with mtranslate
    try:
        from mtranslate import translate as m_trans
        translated = m_trans(text, target_code, src)
        if translated:
            with _CACHE_LOCK:
                if target_lang_name not in _CACHE:
                    _CACHE[target_lang_name] = {}
                _CACHE[target_lang_name][text] = translated
                _save_cache()
            return translated
    except Exception as e:
        # If network error or offline, fallback to English text
        pass

    return text

def _t(key_or_text: str, default: Optional[str] = None) -> str:
    """
    Universal translation helper function.
    1. Looks up key in pre-compiled TRANSLATIONS dictionary.
    2. If not found or raw string, dynamically translates and caches.
    """
    if not key_or_text or not isinstance(key_or_text, str):
        return key_or_text or ""
        
    lang = st.session_state.get("language", "English")
    
    # 1. English returns immediately
    if lang == "English":
        eng_dict = TRANSLATIONS.get("English", {})
        if key_or_text in eng_dict:
            return eng_dict[key_or_text]
        return default if default is not None else key_or_text

    # 2. Check pre-compiled dictionary for target language
    lang_dict = TRANSLATIONS.get(lang, {})
    if key_or_text in lang_dict:
        return lang_dict[key_or_text]

    # 3. Check if key is in English dictionary, translate its English value
    eng_dict = TRANSLATIONS.get("English", {})
    if key_or_text in eng_dict:
        base_english = eng_dict[key_or_text]
        return translate_text(base_english, lang)

    # 4. Raw text dynamic translation
    base_text = default if default is not None else key_or_text
    return translate_text(base_text, lang)

def render_translator_bridge():
    """
    Injects Google Website Translator and a live DOM auto-sync engine
    into the Streamlit app to translate all DOM elements (buttons, inputs, tables,
    sidebars, tabs, metrics, headers, modals) seamlessly.
    """
    current_lang = st.session_state.get("language", "English")
    if current_lang == "English" or not current_lang:
        return
        
    lang_code = get_lang_code(current_lang)
    
    bridge_html = f"""
    <script>
    (function() {{
        const targetLang = "{lang_code}";
        const topWin = window.top || window.parent;
        const doc = topWin.document;

        // Hide ugly Google Translate banner elements
        let style = doc.getElementById('custom-gt-style');
        if (!style) {{
            style = doc.createElement('style');
            style.id = 'custom-gt-style';
            style.innerHTML = `
                .goog-te-banner-frame.skiptranslate, .goog-te-banner-frame, iframe.goog-te-banner-frame {{{{ display: none !important; }}}}
                body {{{{ top: 0px !important; position: static !important; }}}}
                .goog-tooltip, .goog-tooltip:hover, #goog-gt-tt, .goog-te-balloon-frame {{{{ display: none !important; }}}}
                .goog-text-highlight {{{{ background-color: transparent !important; border: none !important; box-shadow: none !important; }}}}
                #google_translate_element {{{{ display: none !important; }}}}
                .skiptranslate iframe {{{{ display: none !important; }}}}
            `;
            doc.head.appendChild(style);
        }}

        // Inject Google Translate script if not already present
        if (!doc.getElementById('google-translate-script')) {{
            let elem = doc.getElementById('google_translate_element');
            if (!elem) {{
                elem = doc.createElement('div');
                elem.id = 'google_translate_element';
                elem.style.display = 'none';
                doc.body.appendChild(elem);
            }}

            const script = doc.createElement('script');
            script.id = 'google-translate-script';
            script.type = 'text/javascript';
            script.src = 'https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit';
            doc.head.appendChild(script);

            topWin.googleTranslateElementInit = function() {{
                try {{
                    new topWin.google.translate.TranslateElement({{
                        pageLanguage: 'en',
                        autoDisplay: false
                    }}, 'google_translate_element');
                }} catch(e) {{}}
            }};
        }}

        // Function to apply DOM translation
        function applyDomLanguage(code) {{
            try {{
                if (code === 'en') {{
                    doc.cookie = "googtrans=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
                    doc.cookie = "googtrans=; expires=Thu, 01 Jan 1970 00:00:00 UTC; domain=" + window.location.hostname + "; path=/;";
                }} else {{
                    doc.cookie = "googtrans=/en/" + code + "; path=/;";
                    doc.cookie = "googtrans=/en/" + code + "; domain=" + window.location.hostname + "; path=/;";
                }}

                const combo = doc.querySelector('.goog-te-combo');
                if (combo) {{
                    if (combo.value !== code) {{
                        combo.value = code;
                        combo.dispatchEvent(new Event('change'));
                    }}
                }}
            }} catch(err) {{}}
        }}

        // Trigger translation switch
        setTimeout(function() {{
            applyDomLanguage(targetLang);
        }}, 300);

    }})();
    </script>
    """
    components.html(bridge_html, height=0, width=0)
