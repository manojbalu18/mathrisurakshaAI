import streamlit as st
import sqlite3
import pandas as pd
import time
import datetime
import math
import os
import requests
import numpy as np
import folium
from streamlit_folium import st_folium
from geopy.distance import geodesic
from streamlit_geolocation import streamlit_geolocation
import base64

import database
import pandas as pd
import plotly.graph_objects as go
from database import register_mother, verify_mother, get_all_mothers, update_location, get_mothers_with_risk_and_location, save_daily_log, create_alert, log_live_sms, get_active_alerts, get_all_logs, has_recent_high_risk_sms
from ai_engine import calculate_risk
from dotenv import load_dotenv
from translations import TRANSLATIONS
from connectivity import is_online
from lm_studio_client import LMStudioClient
from ai_service import AIService
from voice_service import VoiceService
from tts_service import TTSService
import config

load_dotenv()

# Initialize Database tables
database.init_db()
st.set_page_config(page_title="MAATRI SURAKSHA AI", page_icon="🩺", layout="wide")

# ---------------- OFFLINE SYNC LOGIC ----------------
def process_offline_sync():
    """Check for internet and sync any pending offline records."""
    if is_online():
        from database import get_pending_sync_records, delete_sync_record, save_daily_log
        import json
        
        pending = get_pending_sync_records()
        if pending:
            for record in pending:
                rec_id, user_id, feature, payload_json, timestamp = record
                payload = json.loads(payload_json)
                
                if feature == "daily_log":
                    # Re-run AI risk calculation for the original data
                    from ai_engine import calculate_risk
                    ai_result = calculate_risk(payload['symptoms'], payload['mood'], payload['nutrition'])
                    save_daily_log(user_id, payload['symptoms'], payload['mood'], payload['nutrition'], 
                                   ai_result['risk_score'], ai_result['risk_level'], payload['timestamp'])
                    # If high risk was detected originally, we might want to trigger alerts now
                    if ai_result['escalation']:
                        from database import create_alert
                        create_alert(user_id, ai_result['risk_level'], payload['timestamp'])
                elif feature == "location":
                    from database import update_location
                    update_location(user_id, payload['latitude'], payload['longitude'])
                
                # After successful sync, delete the offline record
                delete_sync_record(rec_id)
            
            st.toast(_t("sync_success_msg"), icon="✅")

def init_session_state():
    """Initialize essential session state variables."""
    # Run offline sync check on init
    process_offline_sync()
    
    if 'splash_shown' not in st.session_state:
        st.session_state['splash_shown'] = False
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
    if 'role' not in st.session_state:
        st.session_state['role'] = None
    if 'otp_sent' not in st.session_state:
        st.session_state['otp_sent'] = False
        
    # Catch navigational query parameters
    query_params = st.query_params
    if 'nav' in query_params:
        target = query_params['nav']
        if target == "Geospatial Heatmap" and st.session_state.get('role') == 'ASHA Worker':
            st.session_state['asha_page'] = "Geospatial Heatmap"
            
            if 'focus' in query_params:
                st.session_state['map_focus_mother'] = query_params['focus']
                
            # Clear it so we don't get stuck in a loop on refresh
            st.query_params.clear()
    if 'temp_phone' not in st.session_state:
        st.session_state['temp_phone'] = ""
    if 'temp_role' not in st.session_state:
        st.session_state['temp_role'] = None
    if 'mother_page' not in st.session_state:
        st.session_state['mother_page'] = "Dashboard Overview"
    if 'language' not in st.session_state:
        st.session_state['language'] = "English"
    if 'transcription' not in st.session_state:
        st.session_state['transcription'] = ""
    if 'audio_processed' not in st.session_state:
        st.session_state['audio_processed'] = False
    if 'asha_page' not in st.session_state:
        st.session_state['asha_page'] = "Dashboard Overview"
    if 'alert_checked' not in st.session_state:
        st.session_state['alert_checked'] = False
    if 'active_audio_idx' not in st.session_state:
        st.session_state['active_audio_idx'] = None
    if 'audio_cache' not in st.session_state:
        st.session_state['audio_cache'] = {}
    if 'lm_studio_url' not in st.session_state:
        st.session_state['lm_studio_url'] = config.LM_STUDIO_BASE_URL
    if 'lm_studio_model' not in st.session_state:
        st.session_state['lm_studio_model'] = config.LM_STUDIO_MODEL
    if 'voice_chat_processed' not in st.session_state:
        st.session_state['voice_chat_processed'] = False

def _t(key):
    """Helper function to get translation."""
    lang = st.session_state.get('language', 'English')
    return TRANSLATIONS.get(lang, TRANSLATIONS['English']).get(key, key)

def apply_custom_css():
    """Apply professional healthcare-themed CSS styles."""
    st.markdown("""
        <style>
        /* Main background - Soft blush and cream feel */
        .stApp {
            background-color: #fcf9f9;
        }
        
        /* Hide main menu and footer for cleaner UI */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        
        /* Emergency Badge */
        .emergency-badge {
            position: absolute;
            top: 15px;
            right: 25px;
            background-color: #dc3545;
            color: #ffffff;
            padding: 10px 18px;
            border-radius: 50px;
            font-weight: 700;
            font-family: 'Inter', sans-serif;
            font-size: 1.1rem;
            box-shadow: 0 4px 8px rgba(220, 53, 69, 0.3);
            z-index: 9999;
            display: flex;
            align-items: center;
            letter-spacing: 0.5px;
        }

        /* Title styling */
        .app-title {
            font-family: 'Inter', sans-serif;
            color: #0b5394;
            font-size: 2.8rem;
            font-weight: 800;
            margin-bottom: 0.2rem;
            padding-bottom: 0px;
            margin-top: 2rem;
        }
        
        .app-subtitle {
            font-family: 'Inter', sans-serif;
            color: #3d85c6;
            font-size: 1.2rem;
            font-weight: 500;
            margin-top: 0px;
            margin-bottom: 2rem;
        }
        
        /* Footer styling */
        .custom-footer {
            position: fixed;
            bottom: 0;
            left: 0;
            width: 100%;
            background-color: #ffffff;
            color: #666666;
            text-align: center;
            padding: 8px 0;
            font-size: 0.8rem;
            border-top: 1px solid #e0e0e0;
            font-family: 'Inter', sans-serif;
            z-index: 999;
        }
        .footer-links {
            margin-top: 4px;
        }
        .footer-links a {
            color: #0b5394;
            text-decoration: none;
            margin: 0 10px;
        }
        .footer-links a:hover {
            text-decoration: underline;
        }
        
        /* Login Card Frame styling */
        div[data-testid="stForm"] {
            background-color: #ffffff;
            padding: 2.5rem 2rem;
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
            border-top: 5px solid #d47e8c;
        }
        
        /* Dashboard Cards */
        .health-card {
            background-color: #ffffff;
            border-radius: 10px;
            padding: 1.5rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
            margin-bottom: 1rem;
            border-left: 4px solid #d47e8c;
        }
        
        .risk-badge-low { background-color: #d4edda; color: #155724; padding: 4px 10px; border-radius: 4px; font-weight: bold; }
        .risk-badge-medium { background-color: #fff3cd; color: #856404; padding: 4px 10px; border-radius: 4px; font-weight: bold; }
        .risk-badge-high { background-color: #f8d7da; color: #721c24; padding: 4px 10px; border-radius: 4px; font-weight: bold; }
        
        /* Button styling */
        div[data-testid="stFormSubmitButton"] > button {
            width: 100%;
            background-color: #d47e8c;
            color: white;
            font-weight: 600;
            font-size: 1.1rem;
            border-radius: 8px;
            padding: 0.6rem;
            border: none;
            transition: all 0.3s ease;
            margin-top: 1rem;
        }
        
        div[data-testid="stFormSubmitButton"] > button:hover {
            background-color: #b5606e;
            color: white;
            box-shadow: 0 4px 8px rgba(212, 126, 140, 0.2);
            border: none;
        }
        
        /* ASHA Dashboard Specific Styles */
        .asha-metric-box {
            background-color: #ffffff;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            border: 1px solid #eaeaea;
        }
        .metric-title { font-size: 1rem; color: #555; text-transform: uppercase; font-weight: 600; margin-bottom: 5px; }
        .metric-value { font-size: 2.5rem; font-weight: 800; margin: 0; }
        .val-red { color: #dc3545; }
        .val-yellow { color: #ffc107; }
        .val-green { color: #28a745; }
        .val-blue { color: #0b5394; }
        
        /* Sidebar styling */
        section[data-testid="stSidebar"] {
            background-color: #ffffff !important;
            border-right: 1px solid #f0f0f0;
        }
        
        /* Input fields */
        .stTextInput input {
            border-radius: 6px;
        }
        
        /* Offline SMS Button */
        .sms-btn {
            display: inline-block;
            background-color: #dc3545;
            color: white;
            padding: 10px 20px;
            text-align: center;
            border-radius: 5px;
            font-weight: bold;
            text-decoration: none;
            margin-top: 10px;
            box-shadow: 0 4px 6px rgba(220,53,69,0.3);
        }
        .sms-btn:hover {
            background-color: #c82333;
            color: white;
        }
        </style>
    """, unsafe_allow_html=True)

def render_offline_sms_button(mother_id):
    import database
    import urllib.parse
    
    conn = sqlite3.connect("maatrisuraksha.db")
    c = conn.cursor()
    c.execute("SELECT name, village FROM users WHERE unique_id = ?", (mother_id,))
    row = c.fetchone()
    conn.close()
    
    village = row[1] if row and len(row)>1 else "Unknown"
    # Using the hardcoded number requested by the user
    asha_phone = "9347798766"
    
    if asha_phone:
        message = f"🚨 *URGENT ALERT*: High Risk Pregnancy\n\n*Mother ID:* {mother_id}\n*Village:* {village}\n\nImmediate visit and medical attention required."
        encoded_message = urllib.parse.quote(message)
        
        sms_link = f"sms:{asha_phone}?body={encoded_message}"
        wa_link = f"https://wa.me/91{asha_phone}?text={encoded_message}"
        
        st.markdown(f"""
        <div style="display: flex; gap: 10px; margin-top: 10px;">
            <a href="{wa_link}" class="sms-btn" target="_blank" style="flex: 1; text-align: center; background-color: #25D366;">💬 Send via WhatsApp</a>
            <a href="{sms_link}" class="sms-btn" target="_blank" style="flex: 1; text-align: center;">📱 Send via SMS App</a>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.warning("⚠️ Cannot generate offline SMS: No ASHA worker mapped to this village.")

def send_sms_alert(mother_id):
    """
    Sends a live High-Risk SMS via Fast2SMS API.
    Retries once on failure. Logs status via database.
    """
    import database
    import requests
    import os
    
    # Get user details for formatting
    conn = sqlite3.connect("maatrisuraksha.db")
    c = conn.cursor()
    c.execute("SELECT name, village FROM users WHERE unique_id = ?", (mother_id,))
    row = c.fetchone()
    conn.close()
    
    name = row[0] if row else "Unknown"
    village = row[1] if row and len(row)>1 else "Unknown"
    
    # Needs to match user spec exactly for single-line format
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    message = f"ALERT: High Risk Pregnancy | ID:{mother_id} | Village:{village} | Immediate visit required."
    
    api_key = os.environ.get("FAST2SMS_API_KEY", "")
    # Using the hardcoded number requested by the user
    asha_phone = "9347798766"
    
    if not asha_phone:
        api_status = "Failed: No ASHA mapped to village"
        database.log_live_sms(mother_id, "Unknown", message, api_status, timestamp)
        st.warning("⚠️ Live SMS skipped: No ASHA worker mapped to this village.")
        return
        
    if not api_key or api_key == "your-fast2sms-api-key-here":
        api_status = "Failed: Missing API Credentials"
        database.log_live_sms(mother_id, asha_phone, message, api_status, timestamp)
        st.warning("⚠️ Live SMS skipped: Missing FAST2SMS_API_KEY. Utilizing offline local SMS fallback.")
        render_offline_sms_button(mother_id)
        return
        
    url = "https://www.fast2sms.com/dev/bulkV2"
    querystring = {
        "authorization": api_key,
        "message": message,
        "language": "english",
        "route": "q",
        "numbers": asha_phone
    }
    headers = {
        'cache-control': "no-cache"
    }

    print("\n" + "="*40)
    print("LIVE SMS INITIATED")
    print("="*40)
    print(message)
    print("="*40 + "\n")

    max_retries = 2
    for attempt in range(max_retries):
        try:
            response = requests.request("GET", url, headers=headers, params=querystring, timeout=5)
            
            if response.status_code == 200:
                resp_json = response.json()
                if resp_json.get('return', True):
                    api_status = "Sent"
                    database.log_live_sms(mother_id, asha_phone, message, api_status, timestamp)
                    st.success(f"📩 Emergency SMS delivered to ASHA Worker ({asha_phone})")
                    return
                else:
                    api_status = f"Failed: API Error {resp_json.get('message')}"
                    print(f"SMS Attempt {attempt+1} API error: {resp_json.get('message')}")
            else:
                api_status = f"Failed: HTTP {response.status_code}"
                print(f"SMS Attempt {attempt+1} failed with status {response.status_code}: {response.text}")
                
        except requests.exceptions.RequestException as e:
            api_status = f"Failed: Exception ({type(e).__name__})"
            print(f"SMS Attempt {attempt+1} exception: {e}")
            
        if attempt < max_retries - 1:
            time.sleep(2)  # Wait before retrying
            
    # If we exhaust retries
    database.log_live_sms(mother_id, asha_phone, message, api_status, timestamp)
    
    # Surface specific Fast2SMS API errors (like the 100 INR requirement)
    if "100 INR" in api_status or "400" in api_status:
        st.warning("⚠️ Live SMS skipped: Fast2SMS requires a minimum wallet balance (100 INR) to unlock the API route in India. Utilizing offline local SMS fallback.")
    else:
        st.warning("⚠️ Could not deliver SMS alert via API. Utilizing offline local SMS fallback.")
        
    render_offline_sms_button(mother_id)

def login_page():
    """Render the centralized professional login page with logo and footer."""
    apply_custom_css()
    
    # Emergency Badge
    st.markdown(f"""
        <div class="emergency-badge">
            {_t('emergency_badge')}
        </div>
    """, unsafe_allow_html=True)
    
    # Header Section with Logo and Title
    header_col1, header_col2 = st.columns([1, 4])
    with header_col1:
        # Load the generated logo
        try:
            st.image("logo.png", width=120)
        except Exception:
            st.markdown("🩺") # Fallback icon
    
    with header_col2:
        st.markdown(f"<h1 class='app-title'>{_t('app_title')}</h1>", unsafe_allow_html=True)
        st.markdown(f"<p class='app-subtitle'>{_t('app_subtitle')}</p>", unsafe_allow_html=True)
    
    st.divider()
    
    # Grid column layout to perfectly center the form
    col1, col2, col3 = st.columns([1, 1.2, 1])
    
    with col2:
        if not st.session_state.get('otp_sent', False):
            st.markdown(f"<h3 style='text-align: center; color: #444; margin-bottom: 1.5rem;'>{_t('secure_portal_heading')}</h3>", unsafe_allow_html=True)
            role = st.selectbox(_t('select_role'), [_t('role_mother'), _t('role_asha'), 'Baby Care'], key="role_selector")
            
            if role == _t('role_mother'):
                with st.form("login_form_mother"):
                    unique_id = st.text_input(_t('unique_id_label'), placeholder=_t('unique_id_placeholder'))
                    name = st.text_input(_t('full_name_label'), placeholder=_t('full_name_placeholder'))
                    submit_button = st.form_submit_button(_t('login_btn'))
                    
                    if submit_button:
                        if not unique_id.strip() or not name.strip():
                            st.error(_t('error_id_name_missing'))
                        else:
                            if verify_mother(unique_id.strip(), name.strip()):
                                st.session_state['logged_in'] = True
                                st.session_state['role'] = "Mother"
                                st.session_state['unique_id'] = unique_id.strip()
                                st.session_state['mother_name'] = name.strip()
                                st.rerun()
                            else:
                                st.error("❌ Invalid ID or Name. Please check and try again.")
            elif role == 'Baby Care':
                with st.form("login_form_baby"):
                    unique_id = st.text_input("Mother ID", placeholder="Enter Mother ID (e.g., M-001)")
                    submit_button = st.form_submit_button(_t('login_btn'))
                    
                    if submit_button:
                        if not unique_id.strip():
                            st.error("⚠️ Please enter Mother ID.")
                        else:
                            # We just reuse verify_mother implicitly by fetching the profile
                            from database import get_baby_profile
                            # If they exist as a mother, we can log them into baby care
                            conn = sqlite3.connect("maatrisuraksha.db")
                            c = conn.cursor()
                            c.execute("SELECT name FROM users WHERE role='Mother' AND unique_id=? COLLATE NOCASE", (unique_id.strip(),))
                            user = c.fetchone()
                            conn.close()
                            
                            if user:
                                st.session_state['logged_in'] = True
                                st.session_state['role'] = "Baby Care"
                                st.session_state['unique_id'] = unique_id.strip()
                                st.session_state['mother_name'] = user[0]
                                st.session_state['baby_page'] = "Baby Profile"
                                st.rerun()
                            else:
                                st.error("❌ Invalid Mother ID. Please check and try again.")
            else:
                with st.form("login_form"):
                    phone = st.text_input("📱 Phone Number", placeholder="Enter your 10-digit mobile number")
                    password = st.text_input("🔒 Password", placeholder="Enter your 4-digit PIN", type="password")
                    submit_button = st.form_submit_button("Login")
                    
                    if submit_button:
                        if phone.strip() != "9347798766":
                            st.error("⚠️ Only the registered demo ASHA number (9347798766) is permitted for login.")
                        elif password != "1111":
                            st.error("❌ Incorrect password.")
                        else:
                            st.session_state['logged_in'] = True
                            st.session_state['role'] = "ASHA Worker"
                            st.rerun()

def mother_dashboard():
    """Render the comprehensive Mother's portal."""
    
    # Render Sidebar Navigation for Mother Dashboard
    with st.sidebar:
        st.header(_t("mother_portal"))
        st.markdown(f"**{_t('lang_toggle')}:** {st.session_state['language']}")
        st.divider()
        
        st.markdown("<p style='color: #888; font-size: 0.8rem; font-weight: bold;'>MAIN MENU</p>", unsafe_allow_html=True)
        
        # Navigation buttons layout
        nav_options = {
            "Dashboard Overview": (_t("nav_overview"), "🏠"),
            "Daily Health Log": (_t("nav_log"), "📝"),
            "Voice Input (Symptoms)": (_t("nav_voice"), "🎤"),
            "Food & Nutrition": (_t("nav_food"), "🍎"),
            "AI Food Planner": (_t("nav_planner"), "🤖"),
            "Mood Tracker": (_t("nav_mood"), "😊"),
            "AI Risk Panel": (_t("nav_risk"), "📊"),
            "Live Location & Map": (_t("nav_map"), "📍"),
            "Health Reminders": (_t("nav_reminders"), "🔔"),
            "Pregnancy Journey": (_t("nav_journey"), "👶"),
            "Exercise Coach": (_t("menu_exercise_coach"), "🧘‍♀️"),
            "AI Health Assistant": ("🤖 AI Health Assistant", "💬"),
            "Emergency Help": (_t("nav_emergency"), "🚨")
        }
        
        for key, (label, icon) in nav_options.items():
            if st.button(f"{icon} {label}", use_container_width=True, type="secondary" if st.session_state['mother_page'] != key else "primary"):
                st.session_state['mother_page'] = key
                st.rerun()
                
        st.divider()
        supported_langs = ["English", "Hindi", "Telugu", "Tamil", "Kannada", "Malayalam", "Bengali", "Marathi", "Urdu", "Gujarati", "Odia", "Punjabi"]
        st.selectbox(_t("lang_toggle"), supported_langs, key="lang_toggle", on_change=lambda: st.session_state.update({"language": st.session_state.lang_toggle}))
        
        if st.button(_t("logout_btn"), use_container_width=True):
            logout()

    # Right Content Area based on selected page
    page = st.session_state['mother_page']
    
    if page == "Dashboard Overview":
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #FF9A9E 0%, #FECFEF 100%); padding: 30px; border-radius: 15px; margin-bottom: 25px; color: #333; box-shadow: 0 4px 15px rgba(255,154,158,0.3);">
            <h1 style="margin:0; font-size: 2.2rem; display: flex; align-items: center; gap: 10px;">👋 {_t('nav_overview')}</h1>
            <p style="margin: 5px 0 0 0; font-size: 1.1rem; opacity: 0.9;">{_t('welcome_back')} Let's make today a healthy day.</p>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
                <div style="background: white; padding: 20px; border-radius: 12px; border-top: 5px solid #28a745; box-shadow: 0 4px 6px rgba(0,0,0,0.05); height: 100%; text-align: center;">
                    <h4 style="color: #666; font-size: 0.9rem; text-transform: uppercase; margin-bottom: 10px;">{_t('current_risk')}</h4>
                    <span style="background: #e8f5e9; color: #2e7d32; padding: 5px 15px; border-radius: 20px; font-weight: bold; font-size: 1.1rem; display: inline-block;">🟢 {_t('risk_low')}</span>
                    <p style="color:#888; font-size:0.85rem; margin-top:15px; margin-bottom: 0;">{_t('normal_today')}</p>
                </div>
            """, unsafe_allow_html=True)
            
        with col2:
            current_time = datetime.datetime.now().strftime("%I:%M %p")
            current_date = datetime.datetime.now().strftime("%b %d")
            st.markdown(f"""
                <div style="background: white; padding: 20px; border-radius: 12px; border-top: 5px solid #007bff; box-shadow: 0 4px 6px rgba(0,0,0,0.05); height: 100%; text-align: center;">
                    <h4 style="color: #666; font-size: 0.9rem; text-transform: uppercase; margin-bottom: 10px;">{_t('last_log')}</h4>
                    <p style="font-size: 1.6rem; font-weight: 800; color: #333; margin:0;">{current_time}</p>
                    <p style="color:#007bff; font-weight: 600; font-size: 1rem; margin: 0;">{current_date}</p>
                    <p style="color:#888; font-size:0.8rem; margin-top:5px; margin-bottom: 0;">{_t('logged_auto')}</p>
                </div>
            """, unsafe_allow_html=True)
            
        with col3:
            # Dynamically calculate trimester based on mother unique_id
            mother_id_str = st.session_state.get('mother_id', '000')
            try:
                m_id = int(mother_id_str)
            except ValueError:
                m_id = 1
                
            if 1 <= m_id <= 40:
                week = 4 + ((m_id * 7) % 36) # Distribute between 4 and 39
            else:
                week = 24
                
            if week <= 13:
                trimester = "1st"
            elif week <= 26:
                trimester = "2nd"
            else:
                trimester = "3rd"
                
            st.markdown(f"""
                <div style="background: white; padding: 20px; border-radius: 12px; border-top: 5px solid #ffc107; box-shadow: 0 4px 6px rgba(0,0,0,0.05); height: 100%; text-align: center;">
                    <div style="font-size: 2rem; margin-bottom: 5px;">🍼</div>
                    <h4 style="color: #666; font-size: 0.9rem; text-transform: uppercase; margin: 0;">Trimester</h4>
                    <p style="font-size: 1.6rem; font-weight: 800; color: #333; margin:0;">{trimester}</p>
                    <p style="color:#888; font-size:0.8rem; margin-top:5px; margin-bottom: 0;">Week {week}</p>
                </div>
            """, unsafe_allow_html=True)
            
        st.markdown("<br>", unsafe_allow_html=True)
            
        st.markdown(f"""
            <div style="background: linear-gradient(to right, #e0c3fc 0%, #8ec5fc 100%); padding: 20px 25px; border-radius: 12px; display: flex; align-items: center; gap: 15px; box-shadow: 0 4px 10px rgba(142,197,252,0.2);">
                <div style="background: white; border-radius: 50%; min-width: 50px; height: 50px; display: flex; align-items: center; justify-content: center; font-size: 1.5rem; box-shadow: 0 2px 5px rgba(0,0,0,0.1);">💡</div>
                <div>
                    <h4 style="margin:0; color: #222; font-size: 1.1rem;">{_t('ai_suggestion')}</h4>
                    <p style="margin: 5px 0 0 0; color: #444; font-size: 0.95rem;">{_t('hydration_tip')} Great job hitting your step goal yesterday, keep going!</p>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<br><h3 style='margin-bottom: 15px;'>⚡ Quick Actions</h3>", unsafe_allow_html=True)
        qa1, qa2, qa3, qa4 = st.columns(4)
        with qa1:
            if st.button("📝 Log Health", use_container_width=True):
                st.session_state['mother_page'] = "Daily Health Log"
                st.rerun()
        with qa2:
            if st.button("🧘‍♀️ Exercise", use_container_width=True):
                st.session_state['mother_page'] = "Exercise Coach"
                st.rerun()
        with qa3:
            if st.button("🍎 Meal Plan", use_container_width=True):
                st.session_state['mother_page'] = "AI Food Planner"
                st.rerun()
        with qa4:
            if st.button("🚨 SOS", type="primary", use_container_width=True):
                st.session_state['mother_page'] = "Emergency Help"
                st.rerun()

    elif page == "Daily Health Log":
        st.title(_t("log_title"))
        st.markdown(_t("log_desc"))
        
        with st.form("health_log_form"):
            st.markdown("<div class='health-card'>", unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            with c1:
                h_headache = st.checkbox(_t("sym_headache"))
                h_swelling = st.checkbox(_t("sym_swelling"))
                h_dizziness = st.checkbox(_t("sym_dizziness"))
            with c2:
                h_fetal = st.checkbox(_t("sym_fetal"))
                h_bleeding = st.checkbox(_t("sym_bleeding"))
                
            other_symptoms = st.text_area(_t("other_symptoms"), placeholder=_t("other_symptoms_placeholder"))
            st.markdown("</div>", unsafe_allow_html=True)
            
            if st.form_submit_button(_t("submit_log")):
                # Aggregate symptoms
                symptom_list = []
                if h_headache: symptom_list.append("headache")
                if h_swelling: symptom_list.append("swelling")
                if h_dizziness: symptom_list.append("dizziness")
                if h_fetal: symptom_list.append("reduced fetal movement")
                if h_bleeding: symptom_list.append("bleeding")
                if other_symptoms: symptom_list.append(other_symptoms)
                
                # Fetch baseline mood/nutrition from session if available (mocked here for now)
                mood = "normal"
                nutrition = "good"
                
                # Call AI Engine
                ai_result = calculate_risk(symptom_list, mood, nutrition)
                mother_id = st.session_state.get('unique_id', 'Unknown')
                
                if is_online():
                    # Save to Database normally
                    save_daily_log(mother_id, symptom_list, mood, nutrition, ai_result['risk_score'], ai_result['risk_level'], ai_result['timestamp'])
                    
                    if ai_result['escalation']:
                        create_alert(mother_id, ai_result['risk_level'], ai_result['timestamp'])
                        st.error(f"🚨 ALERT! Risk Level: {ai_result['risk_level'].upper()}. {ai_result['recommendation']}")
                        
                        # Live SMS verification
                        if ai_result['risk_level'] == "High":
                            if not has_recent_high_risk_sms(mother_id):
                                from app import send_sms_alert
                                send_sms_alert(mother_id)
                    elif ai_result['risk_level'] == "Medium":
                        st.warning(f"⚠️ {_t('current_risk')}: {ai_result['risk_level'].upper()}. {ai_result['recommendation']}")
                    else:
                        st.success(f"{_t('success_analyzed_low')} {ai_result['recommendation']}")
                else:
                    # Save Offline to Local Database
                    save_daily_log(mother_id, symptom_list, mood, nutrition, ai_result['risk_score'], ai_result['risk_level'], ai_result['timestamp'])
                    
                    if ai_result['escalation']:
                        create_alert(mother_id, ai_result['risk_level'], ai_result['timestamp'])
                        if ai_result['risk_level'] == "High":
                            from app import render_offline_sms_button
                            render_offline_sms_button(mother_id)
                        
                    # Still show the AI result UI so the offline experience feels identical
                    if ai_result['escalation']:
                        st.error(f"🚨 ALERT! Risk Level: {ai_result['risk_level'].upper()}. {ai_result['recommendation']}")
                    elif ai_result['risk_level'] == "Medium":
                        st.warning(f"⚠️ {_t('current_risk')}: {ai_result['risk_level'].upper()}. {ai_result['recommendation']}")
                    else:
                        st.success(f"{_t('success_analyzed_low')} {ai_result['recommendation']}")

    elif page == "Voice Input (Symptoms)":
        st.title(_t("voice_input_title"))
        st.markdown(_t("voice_desc"))
        
        st.markdown("<div class='health-card' style='text-align: center; padding: 2rem;'>", unsafe_allow_html=True)
        audio_data = st.audio_input(_t("audio_input_label"))
        st.markdown("</div>", unsafe_allow_html=True)
        
        if audio_data is not None:
            if not st.session_state['audio_processed']:
                with st.spinner(_t("processing_audio")):
                    vs = VoiceService()
                    res = vs.transcribe_audio_data(audio_data, language_name=st.session_state.get('language', 'English'))
                    if res["status"] == "success":
                        st.session_state['transcription'] = res["text"]
                    elif res["status"] == "not_understood":
                        st.warning(f"⚠️ {res['message']}")
                        st.session_state['transcription'] = ""
                    else:
                        st.error(f"❌ {res['message']}")
                        st.session_state['transcription'] = _t("err_audio_fail")
                        
                    st.session_state['audio_processed'] = True
                    st.rerun()
        else:
            if st.session_state['audio_processed']:
                st.session_state['transcription'] = ""
                st.session_state['audio_processed'] = False
                
        transcribed_text = st.text_area(_t("transcription_label"), st.session_state['transcription'], height=100)
        
        if st.button(_t("btn_send_ai")):
            if not transcribed_text.strip():
                st.error(_t("err_record_first"))
            else:
                # Mock NLP extraction of symptoms from transcription
                extracted_symptoms = ["swelling"] if "swelling" in transcribed_text.lower() else []
                ai_result = calculate_risk(extracted_symptoms, "normal", "good")
                mother_id = st.session_state.get('unique_id', 'Unknown')
                
                if is_online():
                    save_daily_log(mother_id, extracted_symptoms, "normal", "good", ai_result['risk_score'], ai_result['risk_level'], ai_result['timestamp'])
                    
                    if ai_result['escalation']:
                        create_alert(mother_id, ai_result['risk_level'], ai_result['timestamp'])
                        st.error(f"🚨 {_t('current_risk')}: {ai_result['risk_level'].upper()}. {ai_result['recommendation']}")
                        
                        # Live SMS verification
                        if ai_result['risk_level'] == "High":
                            if not has_recent_high_risk_sms(mother_id):
                                from app import send_sms_alert
                                send_sms_alert(mother_id)
                    else:
                        st.success(f"{_t('success_analyzed_voice')} Score: {ai_result['risk_score']}. {ai_result['recommendation']}")
                else:
                    # Save Offline to Local Database
                    save_daily_log(mother_id, extracted_symptoms, "normal", "good", ai_result['risk_score'], ai_result['risk_level'], ai_result['timestamp'])
                    
                    if ai_result['escalation']:
                        create_alert(mother_id, ai_result['risk_level'], ai_result['timestamp'])
                        if ai_result['risk_level'] == "High":
                            from app import render_offline_sms_button
                            render_offline_sms_button(mother_id)
                        
                    # Still show the AI result UI so the offline experience feels identical
                    if ai_result['escalation']:
                        st.error(f"🚨 {_t('current_risk')}: {ai_result['risk_level'].upper()}. {ai_result['recommendation']}")
                    else:
                        st.success(f"{_t('success_analyzed_voice')} Score: {ai_result['risk_score']}. {ai_result['recommendation']}")
                
                # Clear transcription after sending
                st.session_state['transcription'] = ""
                st.session_state['audio_processed'] = False

    elif page == "Food & Nutrition":
        st.title(_t("food_title"))
        st.markdown(_t("food_desc"))
        
        st.warning(_t("nutri_reminder"))
        
        with st.form("food_log"):
            st.subheader(_t("water_intake_sub"))
            water_glasses = st.slider(_t("water_slider_label"), 0, 15, 3)
            
            st.subheader(_t("food_intake_sub"))
            st.text_area(_t("food_intake_sub"), placeholder=_t("food_placeholder"))
            
            if st.form_submit_button(_t("btn_save_nutri")):
                if is_online():
                    if water_glasses < 5:
                        st.error(_t("err_low_water").format(water_glasses))
                    else:
                        st.success(_t("success_nutri").format(water_glasses))
                else:
                    # Nutrition data is purely informational in this demo, but we save it offline for consistency
                    mother_id = st.session_state.get('unique_id', 'Unknown')
                    import json
                    payload = {"water": water_glasses, "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                    from database import save_offline_record
                    save_offline_record(mother_id, "nutrition", json.dumps(payload))
                    # Show same visual feedback offline
                    if water_glasses < 5:
                        st.error(_t("err_low_water").format(water_glasses))
                    else:
                        st.success(_t("success_nutri").format(water_glasses))

    elif page == "AI Food Planner":
        st.markdown(f"<h1 style='color: #0b5394; font-size: 2.5rem; font-weight: 800; margin-bottom: 0.2rem;'>{_t('ai_planner_title')}</h1>", unsafe_allow_html=True)
        st.markdown(f"<p style='color: #555; font-size: 1.1rem; margin-bottom: 2rem;'>{_t('ai_planner_desc')}</p>", unsafe_allow_html=True)
        
        # Custom CSS for Food Planner
        st.markdown("""
            <style>
            .meal-card {
                padding: 1.5rem;
                border-radius: 15px;
                color: white;
                height: 100%;
                transition: transform 0.3s ease, box-shadow 0.3s ease;
                margin-bottom: 1rem;
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            }
            .meal-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 8px 25px rgba(0,0,0,0.15);
            }
            .meal-morning {
                background: linear-gradient(135deg, #ff9a9e 0%, #fad0c4 99%, #fad0c4 100%);
            }
            .meal-afternoon {
                background: linear-gradient(135deg, #48c6ef 0%, #6f86d6 100%);
            }
            .meal-night {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            }
            .meal-header {
                font-size: 1.3rem;
                font-weight: 700;
                margin-bottom: 1rem;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            .meal-list {
                list-style-type: none;
                padding: 0;
                margin: 0;
            }
            .meal-item {
                background: rgba(255, 255, 255, 0.2);
                margin: 0.5rem 0;
                padding: 0.6rem 1rem;
                border-radius: 8px;
                font-size: 0.95rem;
                font-weight: 500;
                backdrop-filter: blur(5px);
            }
            .planner-controls {
                background: white;
                padding: 1.5rem;
                border-radius: 12px;
                border: 1px solid #eee;
                margin-bottom: 2rem;
            }
            </style>
        """, unsafe_allow_html=True)

        with st.container():
            st.markdown("<div class='planner-controls'>", unsafe_allow_html=True)
            col_diet, col_day = st.columns(2)
            with col_diet:
                diet_type = st.radio(_t("diet_pref_label"), [_t("veg"), _t("non_veg")], horizontal=True)
                diet_key = "Vegetarian" if diet_type == _t("veg") else "Non-Vegetarian"
            with col_day:
                days_map = {
                    _t("day_monday"): "Monday",
                    _t("day_tuesday"): "Tuesday",
                    _t("day_wednesday"): "Wednesday",
                    _t("day_thursday"): "Thursday",
                    _t("day_friday"): "Friday",
                    _t("day_saturday"): "Saturday",
                    _t("day_sunday"): "Sunday"
                }
                selected_day_t = st.selectbox(_t("day_select_label"), list(days_map.keys()))
                selected_day = days_map[selected_day_t]
            st.markdown("</div>", unsafe_allow_html=True)

        # Unified meal plan data
        meal_plans = {
            "Monday": {"Vegetarian": ("meal_oatmeal_almonds", "meal_dal_roti_spinach", "meal_khichdi_veg"), "Non-Vegetarian": ("meal_boiled_eggs_toast", "meal_chicken_curry_rice", "meal_light_soup_salad")},
            "Tuesday": {"Vegetarian": ("meal_poha_peanut", "meal_rajma_rice", "meal_paneer_sabzi_roti"), "Non-Vegetarian": ("meal_omelette_roti", "meal_fish_curry_quinoa", "meal_grilled_chicken_salad")},
            "Wednesday": {"Vegetarian": ("meal_idli_sambar", "meal_chana_masala_roti", "meal_veg_pulao_raita"), "Non-Vegetarian": ("meal_egg_bhurji", "meal_mutton_stew", "meal_chicken_clear_soup")},
            "Thursday": {"Vegetarian": ("meal_upma_veggies", "meal_kadhi_pakora_rice", "meal_dalia"), "Non-Vegetarian": ("meal_boiled_eggs_fruits", "meal_egg_curry_rice", "meal_grilled_fish")},
            "Friday": {"Vegetarian": ("meal_besan_chilla", "meal_aloo_gobi_roti", "meal_lentil_soup"), "Non-Vegetarian": ("meal_chicken_sausages", "meal_chicken_biryani", "meal_mutton_soup")},
            "Saturday": {"Vegetarian": ("meal_stuffed_paratha", "meal_mushroom_curry", "meal_veg_stew"), "Non-Vegetarian": ("meal_scrambled_eggs", "meal_fish_fry", "meal_chicken_salad")},
            "Sunday": {"Vegetarian": ("meal_smoothie_bowl", "meal_paneer_biryani", "meal_tomato_soup"), "Non-Vegetarian": ("meal_egg_sandwich", "meal_sunday_chicken", "meal_chicken_clear_soup")}
        }
        
        m_key, a_key, e_key = meal_plans[selected_day][diet_key]
        
        col_m, col_a, col_e = st.columns(3)
        
        with col_m:
            st.markdown(f"""
                <div class='meal-card meal-morning'>
                    <div class='meal-header'>🌅 {_t('morning_routine')}</div>
                    <div class='meal-list'>
                        <div class='meal-item'>💧 {_t('warm_water')}</div>
                        <div class='meal-item'>🥣 <b>{_t(m_key)}</b></div>
                        <div class='meal-item'>💊 {_t('prenatal_vits')}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
        with col_a:
            st.markdown(f"""
                <div class='meal-card meal-afternoon'>
                    <div class='meal-header'>☀️ {_t('afternoon_lunch')}</div>
                    <div class='meal-list'>
                        <div class='meal-item'>🥗 <b>{_t(a_key)}</b></div>
                        <div class='meal-item'>🥬 {_t('fresh_greens')}</div>
                        <div class='meal-item'>🥣 {_t('curd')}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
        with col_e:
            st.markdown(f"""
                <div class='meal-card meal-night'>
                    <div class='meal-header'>🌙 {_t('night_dinner')}</div>
                    <div class='meal-list'>
                        <div class='meal-item'>🍲 <b>{_t(e_key)}</b></div>
                        <div class='meal-item'>🍞 {_t('easy_digest')}</div>
                        <div class='meal-item'>🥛 {_t('warm_milk')}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)

    elif page == "Health Reminders":
        st.markdown(f"<h1 style='color: #0b5394; font-size: 2.8rem; font-weight: 800; margin-bottom: 0.2rem;'>{_t('reminders_main_title')}</h1>", unsafe_allow_html=True)
        st.markdown(f"<p style='color: #555; font-size: 1.2rem; margin-bottom: 2rem;'>{_t('reminders_main_desc')}</p>", unsafe_allow_html=True)

        # Custom CSS for Premium Reminder Cards
        st.markdown("""
            <style>
            .rem-card-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .rem-card {
                padding: 1.5rem;
                border-radius: 20px;
                color: white;
                position: relative;
                overflow: hidden;
                transition: all 0.3s ease;
                box-shadow: 0 10px 20px rgba(0,0,0,0.1);
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                min-height: 200px;
            }
            .rem-card:hover {
                transform: translateY(-8px);
                box-shadow: 0 15px 30px rgba(0,0,0,0.15);
            }
            .rem-card::after {
                content: '';
                position: absolute;
                top: -50%;
                left: -50%;
                width: 200%;
                height: 200%;
                background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
                pointer-events: none;
            }
            .rem-icon {
                font-size: 2.5rem;
                margin-bottom: 10px;
            }
            .rem-title {
                font-size: 1.4rem;
                font-weight: 800;
                margin-bottom: 5px;
            }
            .rem-desc {
                font-size: 0.95rem;
                opacity: 0.9;
                line-height: 1.4;
            }
            .rem-btn-container {
                display: flex;
                gap: 10px;
                margin-top: 15px;
            }
            
            /* Specific Gradients */
            .grad-iron { background: linear-gradient(135deg, #FF5F6D 0%, #FFC371 100%); }
            .grad-calcium { background: linear-gradient(135deg, #2193b0 0%, #6dd5ed 100%); }
            .grad-folic { background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%); }
            .grad-vit-d { background: linear-gradient(135deg, #FDC830 0%, #F37335 100%); }
            .grad-water { background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); }
            .grad-exercise { background: linear-gradient(135deg, #8E2DE2 0%, #4A00E0 100%); }
            .grad-rest { background: linear-gradient(135deg, #ee9ca7 0%, #ffdde1 100%); color: #8a3a44 !important; }
            .grad-rest .rem-desc { color: #8a3a44; }
            
            /* Medical Alerts */
            .med-alert {
                background: white;
                border-radius: 15px;
                padding: 1.2rem;
                border-left: 6px solid;
                box-shadow: 0 4px 12px rgba(0,0,0,0.05);
                margin-bottom: 15px;
                transition: scale 0.2s ease;
            }
            .med-alert:hover { scale: 1.02; }
            </style>
        """, unsafe_allow_html=True)

        # 1. Daily Medicine & Habits
        st.markdown(f"<h3 style='color: #2c3e50; margin-top: 1rem; border-bottom: 2px solid #eee; padding-bottom: 10px;'>💊 {_t('daily_reminders_title')}</h3>", unsafe_allow_html=True)
        
        # Medicine Grid
        m_col1, m_col2 = st.columns(2)
        
        with m_col1:
            st.markdown(f"""
                <div class='rem-card grad-iron'>
                    <div>
                        <div class='rem-icon'>💊</div>
                        <div class='rem-title'>{_t('rem_iron')}</div>
                        <div class='rem-desc'>{_t('rem_iron_desc')}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            ic1, ic2 = st.columns(2)
            with ic1:
                if st.button(f"✅ {_t('btn_taken')}", key="p_iron_taken", use_container_width=True):
                    st.toast(_t('rem_completed_msg'), icon="🎉")
            with ic2:
                if st.button(f"⏰ {_t('btn_remind')}", key="p_iron_rem", use_container_width=True):
                    st.info("Reminder set for +1 hour.")

            st.markdown(f"""
                <div class='rem-card grad-folic'>
                    <div>
                        <div class='rem-icon'>🧬</div>
                        <div class='rem-title'>{_t('rem_folic')}</div>
                        <div class='rem-desc'>{_t('rem_folic_desc')}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            if st.button(f"✅ {_t('btn_taken')}", key="p_folic_taken", use_container_width=True):
                st.toast(_t('rem_completed_msg'), icon="🎉")

        with m_col2:
            st.markdown(f"""
                <div class='rem-card grad-calcium'>
                    <div>
                        <div class='rem-icon'>🦴</div>
                        <div class='rem-title'>{_t('rem_calcium')}</div>
                        <div class='rem-desc'>{_t('rem_calcium_desc')}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            if st.button(f"✅ {_t('btn_taken')}", key="p_cal_taken", use_container_width=True):
                st.toast(_t('rem_completed_msg'), icon="🎉")

            st.markdown(f"""
                <div class='rem-card grad-vit-d'>
                    <div>
                        <div class='rem-icon'>☀</div>
                        <div class='rem-title'>{_t('rem_vit_d')}</div>
                        <div class='rem-desc'>{_t('rem_vit_d_desc')}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            if st.button(f"✅ {_t('btn_taken')}", key="p_vit_taken", use_container_width=True):
                st.toast(_t('rem_completed_msg'), icon="🎉")

        # Other Habits
        h_col1, h_col2, h_col3 = st.columns(3)
        with h_col1:
            st.markdown(f"""<div class='rem-card grad-water' style='min-height: 150px;'><div class='rem-icon' style='font-size: 1.5rem;'>💧</div><div class='rem-title' style='font-size: 1.1rem;'>{_t('rem_water')}</div><div class='rem-desc'>{_t('rem_water_desc')}</div></div>""", unsafe_allow_html=True)
        with h_col2:
            st.markdown(f"""<div class='rem-card grad-exercise' style='min-height: 150px;'><div class='rem-icon' style='font-size: 1.5rem;'>🧘</div><div class='rem-title' style='font-size: 1.1rem;'>{_t('rem_exercise')}</div><div class='rem-desc'>{_t('rem_exercise_desc')}</div></div>""", unsafe_allow_html=True)
        with h_col3:
            st.markdown(f"""<div class='rem-card grad-rest' style='min-height: 150px;'><div class='rem-icon' style='font-size: 1.5rem;'>🛌</div><div class='rem-title' style='font-size: 1.1rem;'>{_t('rem_rest')}</div><div class='rem-desc'>{_t('rem_rest_desc')}</div></div>""", unsafe_allow_html=True)

        # 2. Medical Alerts
        st.markdown(f"<h3 style='color: #2c3e50; margin-top: 3rem; border-bottom: 2px solid #eee; padding-bottom: 10px;'>📅 {_t('medical_reminders_title')}</h3>", unsafe_allow_html=True)
        
        m1, m2, m3 = st.columns(3)
        with m1:
            st.markdown(f"<div class='med-alert' style='border-color: #dc3545;'><h4 style='color: #dc3545; margin:0;'>{_t('med_anc')}</h4><p style='margin:5px 0;'><strong>{_t('med_anc_rem')}</strong></p><p style='font-size:0.8rem; color:#666;'>📍 PHC Center | 🕒 10:00 AM</p></div>", unsafe_allow_html=True)
        with m2:
            st.markdown(f"<div class='med-alert' style='border-color: #f39c12;'><h4 style='color: #f39c12; margin:0;'>{_t('med_ultrasound')}</h4><p style='margin:5px 0;'><strong>{_t('med_ultrasound_rem')}</strong></p><p style='font-size:0.8rem; color:#666;'>📍 District Imaging Lab</p></div>", unsafe_allow_html=True)
        with m3:
            st.markdown(f"<div class='med-alert' style='border-color: #3498db;'><h4 style='color: #3498db; margin:0;'>{_t('med_vaccination')}</h4><p style='margin:5px 0;'><strong>{_t('med_vaccination_rem')}</strong></p><p style='font-size:0.8rem; color:#666;'>📍 Local Health Clinic</p></div>", unsafe_allow_html=True)

        # 3. AI Recommendation Panel
        st.markdown(f"<h3 style='color: #2c3e50; margin-top: 3rem; border-bottom: 2px solid #eee; padding-bottom: 10px;'>🤖 {_t('ai_recommendation_title')}</h3>", unsafe_allow_html=True)
        st.info(f"💡 **AI Recommendation:** {_t('ai_rec_panel_msg')}")

    elif page == "Mood Tracker":
        st.title(_t("mood_title"))
        st.markdown(_t("mood_desc"))
        
        mood_options = {
            _t("happy"): "Happy",
            _t("normal"): "Normal",
            _t("stressed"): "Stressed",
            _t("very_sad"): "Very Sad"
        }
        selected_mood_t = st.selectbox(_t("mood_select_label"), list(mood_options.keys()))
        mood = mood_options[selected_mood_t]
        
        if mood == "Happy" or mood == "Normal":
            st.success(_t("msg_happy"))
        elif mood == "Stressed":
            st.info(_t("msg_stressed"))
        else:
            st.error(_t("msg_sad"))
            
            if st.button(_t("submit_log")): # Reusing submit_log or should I use a new one? Let's use it for now.
                mother_id = st.session_state.get('unique_id', 'Unknown')
                if is_online():
                    # We don't have a specific mood-only table, but we can log it in daily_log with empty symptoms
                    save_daily_log(mother_id, [], mood, "good", 0, "Low", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    st.success(_t("rem_completed_msg"))
                else:
                    # Save Offline to Local Database
                    save_daily_log(mother_id, [], mood, "good", 0, "Low", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    
                    st.success(_t("rem_completed_msg"))

    elif page == "AI Risk Panel":
        st.title(_t("risk_panel_title"))
        st.markdown(_t("risk_panel_desc"))
        
        if st.button(_t("btn_start_ai"), type="primary"):
            st.session_state['simulating'] = True
            
        dashboard_placeholder = st.empty()
        
        if st.session_state.get('simulating', False):
            import random
            
            st.info(_t("status_monitoring"))
            st.write(_t("escalation_status"))

            # Simulate real-time streaming data for 15 frames
            for i in range(15):
                bp_level = random.randint(110, 150)
                swelling_level = random.randint(10, 60)
                fetal_level = random.randint(40, 90)
                stress_level = random.randint(30, 90)
                
                # Formula for simulation score logic
                deduction = ((bp_level - 120) * 0.4) + (swelling_level * 0.3) + ((80 - fetal_level) * 0.4) + (stress_level * 0.2)
                score = max(10, min(100, int(100 - deduction)))
                
                if score > 75:
                    status_title = _t("risk_low")
                    status_color = "#28a745"
                    bg_color = "#f4faf6"
                    text_color = "#155724"
                elif score > 50:
                    status_title = _t("risk_medium_alert")
                    status_color = "#ffc107"
                    bg_color = "#fffdf5"
                    text_color = "#856404"
                else:
                    status_title = _t("risk_high_alert")
                    status_color = "#dc3545"
                    bg_color = "#f8d7da"
                    text_color = "#721c24"

                fig = go.Figure(data=[
                    go.Bar(name='Threshold', x=[_t('bp_label'), _t('swelling_label'), _t('fetal_label'), _t('stress_label')], y=[120, 20, 80, 50], marker_color='#e0e0e0'),
                    go.Bar(name='Current Level', x=[_t('bp_label'), _t('swelling_label'), _t('fetal_label'), _t('stress_label')], 
                           y=[bp_level, swelling_level, fetal_level, stress_level], 
                           marker_color=[
                               '#dc3545' if bp_level > 120 else '#28a745',
                               '#dc3545' if swelling_level > 20 else '#28a745',
                               '#dc3545' if fetal_level < 80 else '#28a745',
                               '#dc3545' if stress_level > 50 else '#28a745'
                           ])
                ])
                fig.update_layout(barmode='group', title=_t('realtime_monitoring_title'), template='plotly_white', height=350, margin=dict(l=20, r=20, t=40, b=20))
                
                with dashboard_placeholder.container():
                    c1, c2 = st.columns([1, 1])
                    with c1:
                        st.markdown(f"""
                            <div class='health-card' style='border-left: 6px solid {status_color}; background-color: {bg_color}; height: 100%; transition: all 0.2s ease;'>
                                <h3 style='color: {text_color}; margin-top:0'>{_t('status')}: {status_title}</h3>
                                <h1 style='font-size: 3rem; margin: 0; color: {text_color};'>{_t('score')}: {score}/100</h1>
                                <hr>
                                <p><b>{_t('monitoring')}:</b> {_t('actively_reading_sensors')} 🔄</p>
                                <p><b>{_t('escalation_status')}:</b> {_t('analyzing_condition')}</p>
                            </div>
                        """, unsafe_allow_html=True)
                        
                    with c2:
                        st.plotly_chart(fig, use_container_width=True)
                
                time.sleep(0.3)  # Rapid UI refresh delay
            
            # Final steady state
            with dashboard_placeholder.container():
                fig = go.Figure(data=[
                    go.Bar(name='Threshold', x=[_t('bp_label'), _t('swelling_label'), _t('fetal_label'), _t('stress_label')], y=[120, 20, 80, 50], marker_color='#e0e0e0'),
                    go.Bar(name='Last Recorded Level', x=[_t('bp_label'), _t('swelling_label'), _t('fetal_label'), _t('stress_label')], y=[130, 45, 75, 65], marker_color=['#ffc107', '#dc3545', '#28a745', '#ffc107'])
                ])
                fig.update_layout(barmode='group', title=_t('final_assessment_title'), template='plotly_white', height=350, margin=dict(l=20, r=20, t=40, b=20))
                c1, c2 = st.columns([1, 1])
                with c1:
                    st.markdown(f"""
                        <div class='health-card' style='border-left: 6px solid #ffc107; background-color: #fffdf5; height: 100%;'>
                            <h3 style='color: #856404; margin-top:0'>{_t('final_assessment')}: {_t('risk_medium_alert')}</h3>
                            <h1 style='font-size: 3rem; margin: 0;'>{_t('score')}: 65/100</h1>
                            <hr>
                            <p><b>{_t('recommendation')}:</b> {_t('monitor_swelling_tip')}</p>
                            <p><b>{_t('escalation_status')}:</b> <span style='color:green;'>{_t('not_escalated')}</span> - {_t('notified_asha_worker')}.</p>
                        </div>
                    """, unsafe_allow_html=True)
                    
                with c2:
                    st.plotly_chart(fig, use_container_width=True)
                    
        else:
            # Default state before clicking button
            with dashboard_placeholder.container():
                st.info(_t("click_start_ai_info"))

    elif page == "Live Location & Map":
        st.title(_t("map_title_page"))
        st.markdown(_t("map_desc_page"))
        
        online_status = is_online()
            
        # Capture GPS
        loc = streamlit_geolocation()
        
        if loc and loc.get('latitude') and loc.get('longitude'):
            lat = loc['latitude']
            lon = loc['longitude']
            
            st.success(_t("success_loc_captured"))
            
            mother_id = st.session_state.get('unique_id', 'Unknown')
            
            if online_status:
                # Save to Database
                if mother_id != 'Unknown':
                    update_location(mother_id, lat, lon)
            else:
                # Save Offline for later central sync (but local DB can still be updated if needed)
                if mother_id != 'Unknown':
                    update_location(mother_id, lat, lon)
                import json
                payload = {"latitude": lat, "longitude": lon, "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                from database import save_offline_record
                save_offline_record(mother_id, "location", json.dumps(payload))
                
            # Database of Nearest PHCs (Mock for demonstration)
            phcs = [
                {"name": "Rampur Rural Health Center", "lat": lat + 0.015, "lon": lon + 0.020},
                {"name": "Sitapur PHC", "lat": lat - 0.025, "lon": lon + 0.010},
                {"name": "Kondapur CHC", "lat": lat + 0.005, "lon": lon - 0.018}
            ]
            
            # Calculate nearest
            nearest_phc = None
            min_dist = float('inf')
            for phc in phcs:
                dist = geodesic((lat, lon), (phc["lat"], phc["lon"])).km
                if dist < min_dist:
                    min_dist = dist
                    nearest_phc = phc
                    
            st.info(_t("nearest_phc_info").format(nearest_phc['name'], min_dist))
            
            # Check latest log to see if high risk

            conn = sqlite3.connect("maatrisuraksha.db")
            c = conn.cursor()
            c.execute("SELECT risk_level FROM daily_logs WHERE user_id=? ORDER BY date DESC LIMIT 1", (mother_id,))
            risk_row = c.fetchone()
            conn.close()
            
            is_high_risk = risk_row and risk_row[0] == "High"
            
            if is_high_risk:
                st.error(_t("high_risk_alert_map"))
                phc_color = "red"
                phc_icon = "plus"
            else:
                phc_color = "green"
                phc_icon = "medkit"
            
            # Draw Map
            m = folium.Map(location=[lat, lon], zoom_start=13)
            
            # Mother's location
            folium.Marker(
                [lat, lon], 
                popup=_t("your_location"), 
                icon=folium.Icon(color="blue", icon="user")
            ).add_to(m)
            
            # Nearest PHC
            folium.Marker(
                [nearest_phc["lat"], nearest_phc["lon"]], 
                popup=nearest_phc["name"], 
                icon=folium.Icon(color=phc_color, icon=phc_icon)
            ).add_to(m)
            
            if is_high_risk:
                # Add red overlay to visualize urgency zone
                folium.Circle(
                    radius=500,
                    location=[lat, lon],
                    color="red",
                    fill=True,
                ).add_to(m)
                
            st_folium(m, width=700, height=450)

        else:
            st.warning(_t("allow_location_warning"))

    elif page == "Pregnancy Journey":
        st.markdown(f"<h1 style='color: #0b5394; font-size: 2.8rem; font-weight: 800; margin-bottom: 0.2rem;'>{_t('journey_title')}</h1>", unsafe_allow_html=True)
        st.markdown(f"<p style='color: #555; font-size: 1.2rem; margin-bottom: 2rem;'>{_t('journey_desc')}</p>", unsafe_allow_html=True)

        # Custom CSS for Animated Visuals
        st.markdown("""
            <style>
            @keyframes breathe {
                0% { transform: scale(1); opacity: 0.9; }
                50% { transform: scale(1.05); opacity: 1; }
                100% { transform: scale(1); opacity: 0.9; }
            }
            .baby-vignette {
                width: 100%;
                border-radius: 20px;
                overflow: hidden;
                position: relative;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                background: black;
                animation: breathe 4s ease-in-out infinite;
            }
            .baby-img {
                width: 100%;
                display: block;
                border-radius: 20px;
            }
            </style>
        """, unsafe_allow_html=True)

        # Weekly Data Dictionary
        journey_data = {
            4: {"seed": "Poppy Seed", "emoji": "🌱", "img": "fetus_early_stage_8_weeks_1772968782224.png", "dev": "Your baby is currently a tiny ball of cells. Major organs are beginning to form.", "tip": "Start taking Folic Acid and stay away from smoke."},
            8: {"seed": "Raspberry", "emoji": "🍓", "img": "fetus_early_stage_8_weeks_1772968782224.png", "dev": "Baby has tiny arms and legs! The heart is beating very fast.", "tip": "Nausea is common; eat small portions of dry food like biscuits."},
            12: {"seed": "Lime", "emoji": "🍋", "img": "fetus_early_stage_8_weeks_1772968782224.png", "dev": "All organs are present. Baby is starting to move their fingers and toes!", "tip": "Time for your first major checkup. Stay hydrated."},
            16: {"seed": "Avocado", "emoji": "🥑", "img": "fetus_mid_stage_24_weeks_1772968804989.png", "dev": "Baby's nervous system is starting to work. They can make funny faces now!", "tip": "Sleep on your side for better blood flow to the baby."},
            20: {"seed": "Banana", "emoji": "🍌", "img": "fetus_mid_stage_24_weeks_1772968804989.png", "dev": "You are halfway there! Baby can hear your heartbeat and voice.", "tip": "Talk to your baby - they can hear you now! Eat iron-rich foods."},
            24: {"seed": "Corn", "emoji": "🌽", "img": "fetus_mid_stage_24_weeks_1772968804989.png", "dev": "Your baby can now hear sounds outside and your voice clearly.", "tip": "Maintain good posture to avoid back pain. Do light walking."},
            28: {"seed": "Eggplant", "emoji": "🍆", "img": "fetus_mid_stage_24_weeks_1772968804989.png", "dev": "Baby's eyes are opening and closing. They may start to kick more.", "tip": "Count your baby's kicks. If they move less, visit the doctor."},
            32: {"seed": "Squash", "emoji": "🎃", "img": "fetus_late_stage_36_weeks_1772968821884.png", "dev": "Baby is gaining weight fast and preparing for life outside.", "tip": "Eat smaller, more frequent meals to avoid heartburn."},
            36: {"seed": "Papaya", "emoji": "🍈", "img": "fetus_late_stage_36_weeks_1772968821884.png", "dev": "Baby is almost fully developed and 'dropping' into position for birth.", "tip": "Pack your hospital bag and keep emergency numbers ready."},
            40: {"seed": "Watermelon", "emoji": "🍉", "img": "fetus_late_stage_36_weeks_1772968821884.png", "dev": "Your baby is full term and ready to meet you! Any day now!", "tip": "Stay calm and keep your ASHA worker's number handy."}
        }

        # Week Selection
        selected_week = st.slider(_t("select_week_label"), 1, 40, 24)
        
        # Progress Bar
        progress = selected_week / 40.0
        st.markdown(f"**{_t('week_label')} {selected_week} / 40**")
        st.progress(progress)
        
        # Determine current milestone (nearest)
        milestones = sorted(journey_data.keys())
        current_milestone = 4
        for m in milestones:
            if selected_week >= m:
                current_milestone = m
        
        data = journey_data[current_milestone]

        # UI Layout
        col1, col2 = st.columns([1, 1.5])
        
        with col1:
             # Animated Visual
             import os
             # Use the correct absolute path for the artifacts directory
             artifacts_dir = r"C:\Users\Vishw\.gemini\antigravity\brain\a2e699c7-ae99-484d-8e2c-e57b8b2d965e"
             img_path = os.path.join(artifacts_dir, data['img'])
             
             # Convert path to a displayable format for Streamlit if needed, or just use st.image
             st.markdown(f"""
                <div class='baby-vignette'>
                    <img src="data:image/png;base64,{base64.b64encode(open(img_path, "rb").read()).decode()}" class="baby-img">
                </div>
                <div style='text-align: center; margin-top: 15px;'>
                    <span style='font-size: 1.5rem; font-weight: bold; color: #0b5394;'>{_t('baby_size_label')}: {data['seed']} {data['emoji']}</span>
                </div>
            """, unsafe_allow_html=True)

        with col2:
            st.markdown(f"""
                <div class='health-card' style='border-left: 6px solid #0b5394; background: white; border-radius: 15px; padding: 1.5rem; margin-bottom: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.05);'>
                    <h3 style='color: #0b5394; margin-top: 0;'>👶 {_t('baby_dev_label')}</h3>
                    <p style='font-size: 1.2rem; line-height: 1.6; color: #444;'>{data['dev']}</p>
                </div>
                
                <div class='health-card' style='border-left: 6px solid #28a745; background: #f8fff9; border-radius: 15px; padding: 1.5rem; box-shadow: 0 4px 12px rgba(0,0,0,0.05);'>
                    <h3 style='color: #28a745; margin-top: 0;'>🌟 {_t('mother_tip_label')}</h3>
                    <p style='font-size: 1.2rem; font-style: italic; color: #333;'>{data['tip']}</p>
                </div>
            """, unsafe_allow_html=True)
            
        st.info("💡 Pro Tip: Your baby's development is unique. Always follow the advice of your doctor and ASHA worker.")

    elif page == "Exercise Coach":
        st.title(_t("prog_7_day_title"))
        st.markdown(_t("prog_7_day_desc"))
        st.warning(_t("exercise_safety_warning"))
        
        from database import log_exercise, get_mother_exercise_logs
        
        mother_id = st.session_state.get('unique_id', 'Unknown')
        
        # Helper inner function to handle logging
        def handle_log_exercise(ex_type):
            if mother_id != 'Unknown':
                log_exercise(mother_id, ex_type)
                st.success(_t("success_ex_logged"))
                
        # Get AI Risk Recommendation
        conn = sqlite3.connect("maatrisuraksha.db")
        c = conn.cursor()
        c.execute("SELECT risk_level FROM daily_logs WHERE user_id=? ORDER BY date DESC LIMIT 1", (mother_id,))
        risk_row = c.fetchone()
        conn.close()
        
        is_high_risk = risk_row and risk_row[0] == "High"
        

        # Simple logic: Day of year modulo 7 + 1 to simulate a rolling 7-day schedule
        current_day_num = (datetime.datetime.now().timetuple().tm_yday % 7) + 1
        
        st.markdown("---")
        
        if is_high_risk:
            st.error(_t("ai_rec_high"))
        else:
            st.success(_t("ai_rec_low").format(f"{_t('day_' + str(current_day_num))}"))
            
        # Exercise Schedule Data Structure
        schedule = {
            1: {"title": _t("title_day_1"), "exercises": [_t("ex_butterfly"), _t("ex_hip_rotation"), _t("ex_deep_breathing")], "benefit": _t("ben_day_1")},
            2: {"title": _t("title_day_2"), "exercises": [_t("ex_duck_walk"), _t("ex_side_lunges"), _t("ex_butterfly")], "benefit": _t("ben_day_2")},
            3: {"title": _t("title_day_3"), "exercises": [_t("ex_hip_rotation"), _t("ex_squats"), _t("ex_butterfly")], "benefit": _t("ben_day_3")},
            4: {"title": _t("title_day_4"), "exercises": [_t("ex_side_lunges"), _t("ex_duck_walk"), _t("ex_hip_rotation")], "benefit": _t("ben_day_4")},
            5: {"title": _t("title_day_5"), "exercises": [_t("ex_squats"), _t("ex_butterfly"), _t("ex_hip_rotation")], "benefit": _t("ben_day_5")},
            6: {"title": _t("title_day_6"), "exercises": [_t("ex_duck_walk"), _t("ex_side_lunges"), _t("ex_deep_breathing")], "benefit": _t("ben_day_6")},
            7: {"title": _t("title_day_7"), "exercises": [_t("ex_butterfly"), _t("ex_hip_rotation"), _t("ex_deep_breathing")], "benefit": _t("ben_day_7")}
        }
        
        today_data = schedule[current_day_num]
        
        # Display Today's Routine
        st.markdown(f"### 📅 {_t('day_' + str(current_day_num))} – {today_data['title']}")
        st.markdown(f"**Benefits:** {today_data['benefit']}")
        
        for ex in today_data['exercises']:
            st.markdown(f"- {ex}")
            
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button(f"✅ " + _t("btn_mark_day_comp").format(_t('day_' + str(current_day_num))), type="primary", use_container_width=True):
            handle_log_exercise(f"Day {current_day_num} Routine")
            time.sleep(1) # simulate delay and allow UI to catch up for tracker
            st.rerun()
            
        st.markdown("---")
        
        # Exercise Library Expander
        with st.expander(_t("ex_lib_title")):
            lib_col1, lib_col2 = st.columns(2)
            with lib_col1:
                st.image("assets/ex_butterfly.png", use_container_width=True)
                st.markdown(f"**{_t('ex_butterfly')}**\n{_t('expl_butterfly')}")
                st.markdown("<br>", unsafe_allow_html=True)
                
                st.image("assets/ex_duck_walk.png", use_container_width=True)
                st.markdown(f"**{_t('ex_duck_walk')}**\n{_t('expl_duck_walk')}")
                st.markdown("<br>", unsafe_allow_html=True)
                
                st.image("assets/ex_squats.png", use_container_width=True)
                st.markdown(f"**{_t('ex_squats')}**\n{_t('expl_squats')}")
            with lib_col2:
                st.image("assets/ex_hip_rotation.png", use_container_width=True)
                st.markdown(f"**{_t('ex_hip_rotation')}**\n{_t('expl_hip_rotation')}")
                st.markdown("<br>", unsafe_allow_html=True)
                
                st.image("assets/ex_side_lunges.png", use_container_width=True)
                st.markdown(f"**{_t('ex_side_lunges')}**\n{_t('expl_side_lunges')}")
        
        # Progress Tracker
        st.markdown("---")
        st.subheader(_t("track_title"))
        
        if mother_id != 'Unknown':
            recent_logs = get_mother_exercise_logs(mother_id)
            # Find which days were completed in the last 7 days
            completed_days = set()
            now = datetime.datetime.now()
            
            if recent_logs:
                for log in recent_logs:
                    ex_type = log[0]
                    log_time = datetime.datetime.strptime(log[1], "%Y-%m-%d %H:%M:%S")
                    
                    if (now - log_time).days <= 7:
                        # Extract day number if it matches "Day X Routine"
                        if ex_type.startswith("Day ") and "Routine" in ex_type:
                            try:
                                d_num = int(ex_type.split(" ")[1])
                                completed_days.add(d_num)
                            except:
                                pass
            
            # Display tracking UI
            track_cols = st.columns(7)
            for i in range(1, 8):
                with track_cols[i-1]:
                    st.markdown(f"**{_t('day_' + str(i))}**<br><span style='font-size:0.8rem; color:#555;'>{schedule[i]['title']}</span>", unsafe_allow_html=True)
                    if i in completed_days:
                        st.markdown(f"<span style='color:green; font-weight:bold;'>{_t('track_completed')}</span>", unsafe_allow_html=True)
            
            # Calculate Percentage
            completion_pct = int((len(completed_days) / 7.0) * 100)
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f"**{_t('track_overall')}:** {completion_pct}%")
            st.progress(completion_pct / 100.0)

    elif page == "Emergency Help":
        st.title(_t("emergency_title"))
        st.error(_t("emergency_desc"))
        
        st.markdown("<br><br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            if st.button(_t("btn_trigger_emergency"), type="primary", use_container_width=True):
                mother_id = st.session_state.get('unique_id', 'Unknown')
                if mother_id != 'Unknown':
                    create_alert(mother_id, "High", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    
                    if is_online():
                        from app import send_sms_alert
                        send_sms_alert(mother_id)
                        st.error(_t("emergency_initiated_sms"))
                    else:
                        from app import render_offline_sms_button
                        render_offline_sms_button(mother_id)
                        st.info(_t("offline_save_msg"))
                else:
                    st.warning(_t("emergency_profile_missing"))

    elif page == "AI Health Assistant":
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #e0c3fc 0%, #8ec5fc 100%); padding: 25px; border-radius: 15px; margin-bottom: 25px; color: #333; box-shadow: 0 4px 15px rgba(142,197,252,0.3);">
            <h1 style="margin:0; font-size: 2rem; display: flex; align-items: center; gap: 10px;">🤖 AI Health Assistant</h1>
            <p style="margin: 5px 0 0 0; font-size: 1.1rem; opacity: 0.9;">Your 24/7 personal pregnancy guide with Local LM Studio & Voice Interaction.</p>
        </div>
        """, unsafe_allow_html=True)

        # Initialize LM Studio Client and AI Services
        lm_client = LMStudioClient(
            base_url=st.session_state.get('lm_studio_url', config.LM_STUDIO_BASE_URL),
            default_model=st.session_state.get('lm_studio_model', config.LM_STUDIO_MODEL)
        )
        ai_svc = AIService(client=lm_client)
        voice_svc = VoiceService()
        tts_svc = TTSService()

        # Check LM Studio connectivity
        conn_status = lm_client.check_connection(timeout=1.5)
        is_lm_online = conn_status.get("online", False)

        # Render status banner
        if is_lm_online:
            st.markdown(f"""
            <div style="background: #e8f5e9; border: 1px solid #a5d6a7; color: #1b5e20; padding: 12px 18px; border-radius: 10px; margin-bottom: 20px; display: flex; align-items: center; justify-content: space-between;">
                <div>
                    <strong>🟢 LM Studio Active</strong> — Model: <code>{conn_status.get('active_model', 'local-model')}</code> &nbsp;|&nbsp; Server: <code>{lm_client.base_url}</code>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background: #fff8e1; border: 1px solid #ffe082; color: #b78103; padding: 14px 18px; border-radius: 10px; margin-bottom: 20px;">
                <div style="font-weight: bold; font-size: 1rem; margin-bottom: 4px;">🟡 LM Studio Offline — Using Local Rule-Based Engine</div>
                <div style="font-size: 0.9rem; color: #5d4037; line-height: 1.5;">
                    The assistant is currently operating in offline fallback mode. To enable your local LLM:
                    <ol style="margin: 6px 0 0 18px; padding: 0;">
                        <li>Open <strong>LM Studio</strong>.</li>
                        <li>Load your desired LLM model (e.g. <i>Llama 3, Mistral, Gemma, Phi-3</i>).</li>
                        <li>Click the <strong>Local Server</strong> tab on the left and click <strong>Start Server</strong> (default port 1234).</li>
                    </ol>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Expandable LM Studio Settings
        with st.expander("⚙️ LM Studio Connection Settings", expanded=False):
            cfg_col1, cfg_col2, cfg_col3 = st.columns([2, 2, 1])
            with cfg_col1:
                new_url = st.text_input("LM Studio Base URL", value=st.session_state.get('lm_studio_url', config.LM_STUDIO_BASE_URL))
            with cfg_col2:
                new_model = st.text_input("Model ID (Optional)", value=st.session_state.get('lm_studio_model', config.LM_STUDIO_MODEL), placeholder="Auto-detect if blank")
            with cfg_col3:
                st.write("")
                st.write("")
                if st.button("Apply & Test", use_container_width=True):
                    st.session_state['lm_studio_url'] = new_url.strip()
                    st.session_state['lm_studio_model'] = new_model.strip()
                    test_client = LMStudioClient(base_url=new_url.strip(), default_model=new_model.strip())
                    test_check = test_client.check_connection(timeout=2.0)
                    if test_check["online"]:
                        st.toast(f"✅ Connected to LM Studio! Active model: {test_check['active_model']}", icon="🟢")
                    else:
                        st.toast(f"⚠️ {test_check['message']}", icon="🟡")
                    st.rerun()

        # Initialize chat history
        if "messages" not in st.session_state:
            st.session_state.messages = []
            greeting = "Namaste! I am your MAATRI AI Assistant. How can I help you with your pregnancy journey today?"
            current_lang = st.session_state.get('language', 'English')
            if current_lang != "English":
                greeting = ai_svc.translate_text(greeting, current_lang)
            st.session_state.messages.append({"role": "assistant", "content": greeting})

        # Unified query execution handler
        def execute_user_query(query_text: str):
            if not query_text or not query_text.strip():
                return
            
            # 1. Append user message to state
            st.session_state.messages.append({"role": "user", "content": query_text.strip()})

            # 2. Fetch patient context from DB
            mother_id = st.session_state.get('unique_id', 'Unknown')
            mother_name = st.session_state.get('mother_name', '')
            risk_level = "Normal"
            if mother_id != 'Unknown':
                try:
                    conn = sqlite3.connect("maatrisuraksha.db")
                    c = conn.cursor()
                    c.execute("SELECT risk_level FROM daily_logs WHERE user_id=? ORDER BY date DESC LIMIT 1", (mother_id,))
                    latest_log = c.fetchone()
                    conn.close()
                    if latest_log:
                        risk_level = latest_log[0]
                except Exception:
                    pass

            user_ctx = {"risk_level": risk_level, "mother_name": mother_name}
            active_lang = st.session_state.get('language', 'English')

            # 3. Call AI Service (unified pipeline for text and voice)
            result = ai_svc.process_message(
                prompt=query_text,
                chat_history=st.session_state.messages[:-1],
                user_context=user_ctx,
                language_name=active_lang,
                custom_model=st.session_state.get('lm_studio_model')
            )

            # 4. Append assistant response
            st.session_state.messages.append({
                "role": "assistant",
                "content": result["response"],
                "source": result["source"],
                "is_emergency": result["is_emergency"],
                "diagnostic": result.get("diagnostic", "")
            })

        # Display chat messages and voice output controls
        for idx, message in enumerate(st.session_state.messages):
            role = message.get("role", "assistant")
            with st.chat_message(role, avatar="🤖" if role == "assistant" else "👤"):
                st.markdown(message["content"])

                # Voice output controls for assistant responses
                if role == "assistant":
                    col_listen, col_stop, col_diag = st.columns([1, 1, 4])
                    is_currently_playing = (st.session_state.get('active_audio_idx') == idx)

                    with col_listen:
                        btn_label = "🔊 Listen" if not is_currently_playing else "🔄 Replay"
                        if st.button(btn_label, key=f"btn_play_{idx}", use_container_width=True):
                            st.session_state['active_audio_idx'] = idx
                            st.rerun()

                    with col_stop:
                        if is_currently_playing:
                            if st.button("⏹ Stop", key=f"btn_stop_{idx}", use_container_width=True):
                                st.session_state['active_audio_idx'] = None
                                st.rerun()

                    with col_diag:
                        src = message.get("source")
                        if src == "lm_studio":
                            st.caption("⚡ Powered by LM Studio Local Model")
                        elif src == "emergency_override":
                            st.caption("🚨 Medical Emergency Interceptor")
                        elif src == "fallback":
                            st.caption("ℹ️ Local Knowledge Base")

                    # If this message is active for playback, synthesize or play cached audio
                    if is_currently_playing:
                        cached_audio = st.session_state.get('audio_cache', {}).get(idx)
                        if not cached_audio:
                            with st.spinner("Synthesizing voice audio..."):
                                cached_audio = tts_svc.synthesize(
                                    message["content"],
                                    language_name=st.session_state.get('language', 'English')
                                )
                                if 'audio_cache' not in st.session_state:
                                    st.session_state['audio_cache'] = {}
                                st.session_state['audio_cache'][idx] = cached_audio

                        if cached_audio:
                            st.audio(cached_audio, format="audio/mp3", autoplay=True)
                        else:
                            st.warning("⚠️ Audio playback could not be generated for this response.")

        # Voice Input Control (Microphone Section)
        st.markdown("<div style='margin-top: 25px;'></div>", unsafe_allow_html=True)
        with st.container():
            st.markdown(f"#### 🎙️ Voice Input ({st.session_state.get('language', 'English')})")
            st.caption("Speak your question or symptoms in your preferred language. Audio is recognized and fed into the AI assistant.")
            
            voice_audio = st.audio_input("Record voice query", key="assistant_voice_mic")
            
            if voice_audio is not None:
                if not st.session_state.get('voice_chat_processed', False):
                    with st.spinner(f"🎙️ Listening & Transcribing speech in {st.session_state.get('language', 'English')}..."):
                        rec_result = voice_svc.transcribe_audio_data(
                            voice_audio,
                            language_name=st.session_state.get('language', 'English')
                        )
                    
                    if rec_result["status"] == "success":
                        recognized_text = rec_result["text"]
                        st.success(f"✅ Speech recognized: \"{recognized_text}\"")
                        st.session_state['voice_chat_processed'] = True
                        execute_user_query(recognized_text)
                        st.rerun()
                    elif rec_result["status"] == "not_understood":
                        st.warning("❓ Speech not understood. Please speak clearly and record again.")
                    else:
                        st.error(f"❌ Microphone/Speech error: {rec_result['message']}")
            else:
                st.session_state['voice_chat_processed'] = False

        # Text input (keeps normal typed input fully functional)
        if prompt := st.chat_input("Ask a question about your health, nutrition, or pregnancy..."):
            execute_user_query(prompt)
            st.rerun()

        # Safety Disclaimer Footer
        st.markdown("""
        <div style="text-align: center; margin-top: 50px; padding: 10px; border-top: 1px solid #eee;">
            <p style="color: #999; font-size: 0.8rem; margin: 0;"><i>This AI assistant provides general pregnancy guidance and does not replace professional medical advice. Always consult your ASHA worker or doctor for medical treatment.</i></p>
        </div>
        """, unsafe_allow_html=True)


def baby_dashboard():
    """Render the Baby Care (Post Delivery) Portal."""

    from database import get_baby_profile, get_baby_vaccinations, save_baby_log, get_baby_logs
    
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #a1c4fd 0%, #c2e9fb 100%); padding: 30px; border-radius: 15px; margin-bottom: 25px; color: #333; box-shadow: 0 4px 15px rgba(161,196,253,0.3);">
        <h1 style="margin:0; font-size: 2.2rem; display: flex; align-items: center; gap: 10px;">👶 {_t('baby_portal_title')}</h1>
        <p style="margin: 5px 0 0 0; font-size: 1.1rem; opacity: 0.9;">Monitoring your little one's health and development.</p>
    </div>
    """, unsafe_allow_html=True)
    
    mother_id = st.session_state.get('unique_id', '')
    mother_name = st.session_state.get('mother_name', '')
    profile = get_baby_profile(mother_id)
    
    if not profile:
        st.warning(_t('err_no_baby_profile'))
        return
        
    delivery_date_str = profile[2]
    baby_gender = profile[3]
    
    delivery_dt = datetime.datetime.strptime(delivery_date_str, "%Y-%m-%d")
    now_dt = datetime.datetime.now()
    days_old = (now_dt - delivery_dt).days
    months_old = max(0, days_old // 30)
    
    with st.sidebar:
        st.header(_t('baby_nav_title'))
        nav_options = {
            _t('nav_baby_profile'): "📋",
            _t('nav_nutrition'): "🍎", 
            _t('nav_vaccination'): "💉",
            _t('nav_growth'): "📈",
            _t('nav_health_log'): "🩺",
            _t('nav_emergency'): "🚨"
        }
        for key, icon in nav_options.items():
            if st.button(f"{icon} {key}", use_container_width=True, type="secondary" if st.session_state.get('baby_page') != key else "primary"):
                st.session_state['baby_page'] = key
                st.rerun()
                
        st.divider()
        supported_langs = ["English", "Hindi", "Telugu", "Tamil", "Kannada", "Malayalam", "Bengali", "Marathi", "Urdu", "Gujarati", "Odia", "Punjabi"]
        st.selectbox(_t("lang_toggle"), supported_langs, key="lang_toggle_baby", on_change=lambda: st.session_state.update({"language": st.session_state.lang_toggle_baby}))
        
        if st.button(_t("logout_btn"), use_container_width=True):
            logout()
            
    page = st.session_state.get('baby_page', _t('nav_baby_profile'))
    
    if page == _t('nav_baby_profile') or page == "Baby Profile":
        st.markdown(f"### ✨ {_t('baby_profile_sec')}")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
                <div style="background: white; padding: 20px; border-radius: 12px; border-top: 5px solid #ff85a2; box-shadow: 0 4px 6px rgba(0,0,0,0.05); height: 100%; text-align: center;">
                    <h4 style="color: #666; font-size: 0.9rem; text-transform: uppercase; margin-bottom: 10px;">{_t('baby_age')}</h4>
                    <p style="font-size: 1.5rem; font-weight: 800; color: #333; margin:0;">{months_old}</p>
                    <p style="color:#ff85a2; font-weight: 600; font-size: 1rem; margin: 0;">{_t('months_label')}</p>
                    <p style="color:#888; font-size:0.8rem; margin-top:5px; margin-bottom: 0;">{days_old} {_t('days_label')} old</p>
                </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
                <div style="background: white; padding: 20px; border-radius: 12px; border-top: 5px solid #36d1dc; box-shadow: 0 4px 6px rgba(0,0,0,0.05); height: 100%; text-align: center;">
                    <h4 style="color: #666; font-size: 0.9rem; text-transform: uppercase; margin-bottom: 10px;">{_t('baby_gender')}</h4>
                    <div style="font-size: 2rem; margin-bottom: 5px;">{'👦' if baby_gender == 'Male' else '👧'}</div>
                    <p style="font-size: 1.4rem; font-weight: 800; color: #333; margin:0;">{baby_gender}</p>
                </div>
            """, unsafe_allow_html=True)
        with col3:
            st.markdown(f"""
                <div style="background: white; padding: 20px; border-radius: 12px; border-top: 5px solid #f9d423; box-shadow: 0 4px 6px rgba(0,0,0,0.05); height: 100%; text-align: center;">
                    <h4 style="color: #666; font-size: 0.9rem; text-transform: uppercase; margin-bottom: 10px;">{_t('delivery_date')}</h4>
                    <p style="font-size: 1.4rem; font-weight: 800; color: #333; margin:0;">{delivery_date_str}</p>
                    <p style="color:#888; font-size:0.8rem; margin-top:5px; margin-bottom: 0;">Born at {mother_id}</p>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        
        # Recent logs summary
        logs = get_baby_logs(mother_id)
        if logs:
            latest = logs[-1]
            st.markdown("### 📊 Activity Snapshot")
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(f"**Feeding:** {latest[1]}")
            with c2:
                st.markdown(f"**Sleep:** {latest[2]} hrs")
            with c3:
                st.markdown(f"**Weight:** {latest[0]} kg")
        
        st.markdown("<br><h3 style='margin-bottom: 15px;'>⚡ Quick Actions</h3>", unsafe_allow_html=True)
        qa1, qa2, qa3, qa4 = st.columns(4)
        with qa1:
            if st.button("📝 Log Health", key="q_log_baby", use_container_width=True):
                st.session_state['baby_page'] = _t('nav_health_log')
                st.rerun()
        with qa2:
            if st.button("💉 Vaccines", key="q_vax_baby", use_container_width=True):
                st.session_state['baby_page'] = _t('nav_vaccination')
                st.rerun()
        with qa3:
            if st.button("📈 Growth", key="q_growth_baby", use_container_width=True):
                st.session_state['baby_page'] = _t('nav_growth')
                st.rerun()
        with qa4:
            if st.button("🆘 SOS", key="q_sos_baby", type="primary", use_container_width=True):
                st.session_state['baby_page'] = _t('nav_emergency')
                st.rerun()

    elif page == _t('nav_nutrition') or page == "Nutrition Guidance":
        st.subheader(_t('nutri_guide_title'))
        col_text, col_img = st.columns([2, 1])
        with col_text:
            if months_old < 6:
                st.markdown(f"#### 🍼 {_t('age_0_6_title')}")
                desc = _t('age_0_6_desc')
                color = "#2196f3"
                bg_color = "#e3f2fd"
            else:
                st.markdown(f"#### 🥣 {_t('age_6_12_title')}")
                desc = _t('age_6_12_desc')
                color = "#4caf50"
                bg_color = "#e8f5e9"
            
            # Split into items and remove bullets
            steps = [s.strip("- ").strip() for s in desc.split('\n') if s.strip()]
            for i, step in enumerate(steps, 1):
                st.markdown(f"""
                <div style="background: white; padding: 15px; border-radius: 10px; border-left: 5px solid {color}; margin-bottom: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); display: flex; align-items: center; gap: 15px;">
                    <div style="background: {bg_color}; color: {color}; min-width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 1rem;">{i}</div>
                    <div style="color: #444; font-size: 1rem; font-weight: 500;">{step}</div>
                </div>
                """, unsafe_allow_html=True)
                
        with col_img:
            try:
                st.image("assets/baby_nutrition.png", use_container_width=True)
            except: pass
            
    elif page == _t('nav_vaccination') or page == "Vaccination Tracker":
        st.subheader(_t('vax_tracker_title'))
        col1, col2 = st.columns([2, 1])
        with col2:
            try:
                st.image("assets/baby_vaccination.png", use_container_width=True)
            except: pass
            
        with col1:
            vaccines = get_baby_vaccinations(mother_id)
            # Find next pending
            next_vaccine = None
            total_vax = len(vaccines)
            completed_vax = sum(1 for v in vaccines if v[4] != 'Pending')
            progress = int((completed_vax / total_vax) * 100) if total_vax > 0 else 0
            
            for v in vaccines:
                if v[4] == 'Pending':
                    next_vaccine = v
                    break
            
            st.markdown(f"""
            <div style="background: white; padding: 15px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); margin-bottom: 20px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span style="font-weight: 600; color: #555;">Overall Protection</span>
                    <span style="font-weight: bold; color: {'#4caf50' if progress > 80 else '#ff9800'};">{progress}%</span>
                </div>
                <div style="background: #eee; height: 10px; border-radius: 5px; overflow: hidden;">
                    <div style="background: linear-gradient(90deg, #4facfe 0%, #00f2fe 100%); width: {progress}%; height: 100%;"></div>
                </div>
            </div>
            """, unsafe_allow_html=True)
                    
            if next_vaccine:
                due_dt = datetime.datetime.strptime(next_vaccine[3], "%Y-%m-%d")
                delta_days = (due_dt - now_dt).days
                vaccine_name = next_vaccine[2]
                
                if delta_days < 0:
                    status_color = "#ffebee"
                    border_color = "#f44336"
                    text_color = "#d32f2f"
                    msg = _t('vax_overdue_msg').format(vaccine_name, abs(delta_days)).replace('###', '').strip()
                else:
                    status_color = "#fff8e1"
                    border_color = "#ffc107"
                    text_color = "#ff8f00"
                    msg = _t('vax_due_msg').format(vaccine_name, delta_days).replace('###', '').strip()
                
                st.markdown(f"""
                <div style="background: {status_color}; padding: 20px; border-radius: 12px; border-left: 6px solid {border_color}; margin-bottom: 20px;">
                    <h4 style="margin: 0; color: {text_color}; display: flex; align-items: center; gap: 8px;">
                        ⚠️ Action Required
                    </h4>
                    <p style="margin: 5px 0 0 0; color: #333; font-size: 1.1rem; font-weight: 500;">{msg}</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="background: #e8f5e9; padding: 20px; border-radius: 12px; border-left: 6px solid #4caf50; margin-bottom: 20px; display: flex; align-items: center; gap: 15px;">
                    <span style="font-size: 2rem;">🏆</span>
                    <div>
                        <h4 style="margin: 0; color: #2e7d32;">Excellent!</h4>
                        <p style="margin: 5px 0 0 0; color: #333;">{_t('vax_all_done').replace('###', '').strip()}</p>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
            st.markdown("---")
            df_vax = pd.DataFrame(vaccines, columns=["ID", "Mother ID", _t("col_vaccine"), _t("col_due_date"), _t("col_status"), "Completed"])
            st.dataframe(df_vax[[_t("col_vaccine"), _t("col_due_date"), _t("col_status")]], use_container_width=True, hide_index=True)
        
    elif page == _t('nav_growth') or page == "Growth & Development":
        st.subheader(_t('growth_title'))
        
        logs = get_baby_logs(mother_id)
        if logs:
            df = pd.DataFrame(logs, columns=['weight', 'feeding', 'sleep', 'date'])
            df['date'] = pd.to_datetime(df['date'])
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df['date'], y=df['weight'], mode='lines+markers', name='Weight (kg)', line=dict(color='#ff85a2', width=3)))
            fig.update_layout(title="Weight Gain Progress", xaxis_title="Date", yaxis_title="Weight (kg)", template="plotly_white", height=350)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No growth logs yet. Start logging health to see the weight chart!")

        col_text, col_img = st.columns([2, 1])
        with col_img:
            try:
                st.image("assets/baby_growth.png", use_container_width=True)
            except: pass
        with col_text:
            milestones = {
                1: _t('milestone_1'),
                3: _t('milestone_3'),
                6: _t('milestone_6'),
                9: _t('milestone_9'),
                12: _t('milestone_12')
            }
            for m, desc in milestones.items():
                month_str = _t('month_label').format(m)
                if months_old >= m:
                    st.success(f"**{month_str}**: {desc} ✅")
                else:
                    st.info(f"**{month_str}**: {desc} {_t('upcoming_label')}")
                
    elif page == _t('nav_health_log') or page == "Health Log":
        st.subheader(_t('health_log_title'))
        col1, col2 = st.columns([2, 1])
        with col2:
            try:
                st.image("assets/baby_health_log.png", use_container_width=True)
            except: pass
            
        with col1:
            with st.form("baby_health"):
                c1, c2 = st.columns(2)
                with c1:
                    fever = st.selectbox(_t('fever_label'), [_t('choice_no'), _t('choice_mild'), _t('choice_high')])
                    cough = st.selectbox(_t('cough_label'), [_t('choice_no'), _t('choice_mild'), _t('choice_severe')])
                    weight = st.number_input(_t('weight_label'), min_value=1.0, max_value=20.0, value=5.0)
                with c2:
                    feeding = st.selectbox(_t('feeding_label'), [_t('choice_feed_2h'), _t('choice_feed_3h'), _t('choice_feed_4h')])
                    sleep = st.number_input(_t('sleep_label'), min_value=1, max_value=24, value=14)
                    
                submit = st.form_submit_button(_t('btn_submit_log'), use_container_width=True)
                if submit:
                    save_baby_log(mother_id, fever, cough, weight, feeding, sleep)
                    st.success(_t('success_log_saved'))
                    st.rerun()
                    
    elif page == _t('nav_emergency') or page == "Emergency Help":
        st.title(_t('baby_emergency_title'))
        st.error(_t('baby_emergency_desc'))
        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            if st.button(_t('btn_trigger_baby_sos'), type="primary", use_container_width=True):
                create_alert(mother_id, "High", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                if is_online():
                    st.success(_t('success_baby_sos'))
                else:
                    from app import render_offline_sms_button
                    render_offline_sms_button(mother_id)
                    st.info(_t("offline_save_msg"))
    
def asha_worker_dashboard():
    """Render the comprehensive ASHA Worker monitoring portal."""
    
    # Render Sidebar Navigation for ASHA Worker
    with st.sidebar:
        st.header(_t("asha_portal"))
        st.markdown(f"**{_t('asha_district')}**")
        st.divider()
        
        st.markdown(f"<p style='color: #888; font-size: 0.8rem; font-weight: bold;'>{_t('monitoring_menu')}</p>", unsafe_allow_html=True)
        
        nav_options = {
            "Dashboard Overview": (_t("asha_overview"), "📊"),
            "Geospatial Heatmap": (_t("asha_heatmap"), "🌍"),
            "Village Health Intelligence": ("Village Health Intelligence", "🏥"),
            "Register Mother": (_t("asha_register"), "📝"),
            "High Risk Alerts": (_t("asha_alerts"), "🚨"),
            "All Mothers": (_t("asha_all"), "👩"),
            "Baby Monitoring": (_t("nav_baby_monitoring"), "👶"),
            "Risk Trends": (_t("asha_trends"), "📈"),
            "Search Mother": (_t("asha_search"), "🔍")
        }
        
        for key, (label, icon) in nav_options.items():
            if st.button(f"{icon} {label}", use_container_width=True, type="secondary" if st.session_state['asha_page'] != key else "primary"):
                st.session_state['asha_page'] = key
                st.rerun()
                
        st.divider()
        supported_langs = ["English", "Hindi", "Telugu", "Tamil", "Kannada", "Malayalam", "Bengali", "Marathi", "Urdu", "Gujarati", "Odia", "Punjabi"]
        st.selectbox(_t("lang_toggle"), supported_langs, key="lang_toggle_asha", on_change=lambda: st.session_state.update({"language": st.session_state.lang_toggle_asha}))
        
        if st.button(_t("logout_btn"), use_container_width=True):
            logout()

    page = st.session_state['asha_page']
    import pandas as pd
    
    # Fetch real data
    try:
        from database import get_all_logs, get_active_alerts
        logs_data = get_all_logs()
        alerts_data = get_active_alerts()
    except Exception as e:
        logs_data = []
        alerts_data = []
        st.error("Database connection error. Displaying empty datasets.")

    if page == "Dashboard Overview":
        # Check for active alerts strictly during the initial load to auto-redirect
        if not st.session_state.get('alert_checked', False) and alerts_data:
            # We have active alerts and haven't redirected yet!
            st.session_state['alert_checked'] = True
            
            # Find the most recent/highest priority mother
            # alerts_data shape: id, mother_id, risk_level, alert_status, date, village, risk_score
            highest_risk_mother_id = alerts_data[0][1]
            
            st.session_state['asha_page'] = "Geospatial Heatmap"
            st.session_state['map_focus_mother'] = highest_risk_mother_id
            st.rerun()
            
        st.session_state['alert_checked'] = True  # Ensure we don't trap them on future visits to overview
        
        st.title(_t("asha_overview"))
        st.markdown(f"<p style='font-size: 1.1rem; color: #555;'>Real-time situational awareness of assigned mothers.</p>", unsafe_allow_html=True)
        
        # Calculate mock metrics from db rows if available, otherwise fallback to defaults
        total_mothers = max(40, len(logs_data)) if logs_data else 40
        active_alerts = len(alerts_data) if alerts_data else 0
        high_risk = active_alerts
        med_risk = 0
        low_risk = total_mothers - high_risk - med_risk

        st.markdown("<br>", unsafe_allow_html=True)
        m1, m2, m3, m4, m5 = st.columns(5)
        
        with m1:
            st.markdown(f"<div class='asha-metric-box'><p class='metric-title'>{_t('total_mothers')}</p><p class='metric-value val-blue'>{total_mothers}</p></div>", unsafe_allow_html=True)
        with m2:
            st.markdown(f"<div class='asha-metric-box'><p class='metric-title'>{_t('active_alerts')}</p><p class='metric-value val-red'>{active_alerts}</p></div>", unsafe_allow_html=True)
        with m3:
            st.markdown(f"<div class='asha-metric-box'><p class='metric-title' style='color:#dc3545'>{_t('high_risk')}</p><p class='metric-value val-red'>{high_risk}</p></div>", unsafe_allow_html=True)
        with m4:
            st.markdown(f"<div class='asha-metric-box'><p class='metric-title' style='color:#ffc107'>{_t('med_risk')}</p><p class='metric-value val-yellow'>{med_risk}</p></div>", unsafe_allow_html=True)
        with m5:
            st.markdown(f"<div class='asha-metric-box'><p class='metric-title' style='color:#28a745'>{_t('low_risk')}</p><p class='metric-value val-green'>{low_risk}</p></div>", unsafe_allow_html=True)

        st.markdown("<br><hr><br>", unsafe_allow_html=True)
        st.subheader(_t("recent_activity"))
        if logs_data:
            df_recent = pd.DataFrame(logs_data, columns=["Log ID", "Mother ID", "Symptoms", "Mood", "Nutrition", "Risk Score", "Risk Level", "Date"])
            st.dataframe(df_recent.head(5)[["Mother ID", "Risk Level", "Symptoms", "Date"]], use_container_width=True, hide_index=True)
        else:
            st.info("No recent logs found in database.")

    elif page == "Geospatial Heatmap":
        st.title(_t("asha_heatmap_title"))
        st.markdown(_t("asha_heatmap_desc"))
        
        with st.spinner(_t("fetching_geodata")):
            import folium
            from streamlit_folium import st_folium
            from streamlit_folium import st_folium
            all_mothers_data = get_mothers_with_risk_and_location()
        
        if not all_mothers_data:
            st.info(_t("err_no_mothers"))
        else:
            # mother shape: u.unique_id(0), u.name(1), u.village(2), u.latitude(3), u.longitude(4), l.risk_level(5), l.risk_score(6), l.date(7)
            map_data = []
            for row in all_mothers_data:
                lat = row[3]
                lon = row[4]
                if lat and lon: # Only map if location exists
                    map_data.append({
                        "id": row[0],
                        "name": row[1],
                        "village": row[2] or "Unknown",
                        "lat": lat,
                        "lon": lon,
                        "risk_level": row[5] or "Low",
                        "risk_score": row[6] or 0,
                        "timestamp": row[7] or "Unknown"
                    })
                    
            if not map_data:
                st.warning("No mothers have shared their location yet.")
            else:
                # Calculate bounds
                high_risk_bounds = []
                all_bounds = []
                
                for md in map_data:
                    all_bounds.append([md["lat"], md["lon"]])
                    if md["risk_level"] == "High":
                        high_risk_bounds.append([md["lat"], md["lon"]])
                
                # Center map roughly
                avg_lat = sum([float(b[0]) for b in all_bounds]) / len(all_bounds)
                avg_lon = sum([float(b[1]) for b in all_bounds]) / len(all_bounds)
                
                # Initialize map
                m = folium.Map(location=[avg_lat, avg_lon], zoom_start=11)
                
                # Add markers
                for md in map_data:
                    if md["risk_level"] == "High":
                        color = "red"
                        radius = 12
                        fill_opacity = 0.8
                    elif md["risk_level"] == "Medium":
                        color = "orange"
                        radius = 10
                        fill_opacity = 0.6
                    else:
                        color = "green"
                        radius = 8
                        fill_opacity = 0.5
                        
                    html_popup = f"""
                    <div style="font-family: Arial; min-width: 150px;">
                        <h4>{md['id']} - {md['name']}</h4>
                        <b>Village:</b> {md['village']}<br>
                        <b>Risk Level:</b> <span style="color:{color}; font-weight:bold;">{md['risk_level']}</span><br>
                        <b>Risk Score:</b> {md['risk_score']}<br>
                        <b>Last Updated:</b> {md['timestamp']}
                    </div>
                    """
                    
                    folium.CircleMarker(
                        location=[md["lat"], md["lon"]],
                        radius=radius,
                        color=color,
                        fill=True,
                        fill_color=color,
                        fill_opacity=fill_opacity,
                        tooltip=f"{md['id']} ({md['risk_level']})",
                        popup=folium.Popup(html_popup, max_width=300)
                    ).add_to(m)
                
                # Auto-zoom to high-risk clusters if they exist, else to all
                focus_mother_id = st.session_state.get('map_focus_mother')
                focus_bounds = []
                
                if focus_mother_id:
                    for md in map_data:
                        if md["id"] == focus_mother_id:
                            focus_bounds.append([md["lat"], md["lon"]])
                
                if focus_bounds:
                    # Zoom tightly to single mother
                    st.info(f"📍 Map is currently focused on Mother ID: {focus_mother_id}")
                    if st.button("Clear Focus", size="small"):
                        st.session_state['map_focus_mother'] = None
                        st.rerun()
                    m.fit_bounds([focus_bounds[0], focus_bounds[0]], max_zoom=15)
                elif high_risk_bounds:
                    m.fit_bounds(high_risk_bounds)
                else:
                    m.fit_bounds(all_bounds)
                    
                st_folium(m, width=800, height=500)

    elif page == "Village Health Intelligence":
        st.title(_t('asha_village_health_title'))
        st.markdown(_t('asha_village_health_desc'))
        
        from database import (
            get_maternal_risk_distribution,
            get_village_risk_aggregations,
            get_vaccination_coverage,
            get_high_risk_mothers_alert,
            get_baby_health_alerts,
            get_upcoming_vaccinations,
            generate_asha_daily_tasks
        )
        import plotly.express as px
        
        st.markdown("---")
        
        # 1. Maternal Risk Distribution & Vaccination Coverage
        col1, col2 = st.columns(2)
        with col1:
            st.subheader(_t('risk_dist_title'))
            raw_risk_dist = get_maternal_risk_distribution()
            # Map to translated keys
            risk_dist = {
                _t('risk_low'): raw_risk_dist.get("Low Risk", 0),
                _t('risk_med'): raw_risk_dist.get("Medium Risk", 0),
                _t('risk_high'): raw_risk_dist.get("High Risk", 0)
            }
            if sum(risk_dist.values()) > 0:
                df_risk = pd.DataFrame(list(risk_dist.items()), columns=[_t('col_risk_level'), _t('mothers_count_label')])
                fig = px.pie(df_risk, values=_t('mothers_count_label'), names=_t('col_risk_level'), 
                             color=_t('col_risk_level'), 
                             color_discrete_map={_t('risk_low'): "#28a745", _t('risk_med'): "#ffc107", _t('risk_high'): "#dc3545"},
                             hole=0.4)
                fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=300)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info(_t('no_risk_data'))
                
        with col2:
            st.subheader(_t('vax_monitor_title'))
            raw_vax_cov = get_vaccination_coverage()
            # Map to translated keys
            vax_cov = {
                _t('vax_status_done'): raw_vax_cov.get("Vaccinated", 0),
                _t('vax_status_pending'): raw_vax_cov.get("Pending", 0),
                _t('vax_status_overdue'): raw_vax_cov.get("Overdue", 0)
            }
            if sum(vax_cov.values()) > 0:
                df_vax = pd.DataFrame(list(vax_cov.items()), columns=[_t('col_status'), _t('mothers_count_label')])
                fig2 = px.bar(df_vax, x=_t('col_status'), y=_t('mothers_count_label'), color=_t('col_status'),
                              color_discrete_map={
                                  _t('vax_status_done'): "#28a745", 
                                  _t('vax_status_pending'): "#6c757d", 
                                  _t('vax_status_overdue'): "#dc3545"
                              })
                fig2.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=300)
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info(_t('no_vax_data'))
                
        # 2. Village Risk Heatmap & AI Predictions
        st.markdown("---")
        map_col, ai_col = st.columns([2, 1])
        
        with map_col:
            st.subheader(_t('village_heatmap_title'))
            villages_data = get_village_risk_aggregations()
            if villages_data:
                import folium
                from streamlit_folium import st_folium
                
                # Start map at avg center
                avg_lat = sum(v["Lat"] for v in villages_data) / len(villages_data)
                avg_lon = sum(v["Lon"] for v in villages_data) / len(villages_data)
                m = folium.Map(location=[avg_lat, avg_lon], zoom_start=11)
                
                # We need bounding box to fit
                bounds = []
                for v in villages_data:
                    color = "green"
                    risk_label = _t('risk_low')
                    if v["Category"] == "Medium Risk": 
                        color = "orange"
                        risk_label = _t('risk_med')
                    elif v["Category"] == "High Risk": 
                        color = "red"
                        risk_label = _t('risk_high')
                    
                    popup_html = f"<b>{_t('village_label')}:</b> {v['Village']}<br><b>{_t('avg_score_label')}:</b> {v['AvgScore']}<br><b>{_t('mothers_count_label')}:</b> {v['Mothers']}<br><b>{_t('col_risk_level')}:</b> {risk_label}"
                    
                    folium.CircleMarker(
                        location=[v["Lat"], v["Lon"]],
                        radius=20,
                        popup=folium.Popup(popup_html, max_width=200),
                        color=color,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.7
                    ).add_to(m)
                    
                    # Add pulse effect for high risk
                    if v["Category"] == "High Risk":
                        folium.Marker(
                            location=[v["Lat"], v["Lon"]],
                            icon=folium.DivIcon(
                                html=f"""<div style="background-color:rgba(220,53,69,0.5);width:40px;height:40px;border-radius:50%;animation: pulse 1.5s infinite;"></div>"""
                            )
                        ).add_to(m)
                    bounds.append([v["Lat"], v["Lon"]])
                
                m.fit_bounds(bounds)
                st_folium(m, width=600, height=400)
            else:
                st.info(_t('no_village_data'))
                
        with ai_col:
            st.subheader(_t('ai_predictions_title'))
            st.markdown("<div style='background-color:#f8f9fa; padding:15px; border-radius:10px; border-left: 5px solid #6f42c1;'>", unsafe_allow_html=True)
            if not villages_data:
                st.write(_t('awaiting_data'))
            else:
                for v in villages_data:
                    if v["Category"] == "High Risk":
                        st.markdown(f"**{v['Village']}**: 🔴 {_t('high_risk_cluster')}")
                    elif v["Category"] == "Medium Risk":
                        st.markdown(f"**{v['Village']}**: 🟡 {_t('medium_risk_cluster')}")
                    else:
                        st.markdown(f"**{v['Village']}**: 🟢 {_t('stable_health')}")
            st.markdown("</div>", unsafe_allow_html=True)
            
        # 3. Tables and Task Lists
        st.markdown("---")
        t1, t2 = st.columns(2)
        
        with t1:
            st.subheader(_t('high_risk_alerts_title'))
            mother_alerts = get_high_risk_mothers_alert()
            if mother_alerts:
                df_ma = pd.DataFrame(mother_alerts, columns=[_t('col_mother_id'), _t('col_village'), _t('col_risk_score'), _t('search_symptoms')])
                st.dataframe(df_ma, use_container_width=True, hide_index=True)
            else:
                st.success(_t('no_high_risk_flagged'))
                
            st.markdown("<br>", unsafe_allow_html=True)
            st.subheader(_t('baby_health_alerts_title'))
            baby_alerts = get_baby_health_alerts()
            if baby_alerts:
                for a in baby_alerts:
                    st.error(f"Baby of Mother **{a['Mother ID']}** ({a['Village']}) - Issue: {a['Issue']}")
            else:
                st.success(_t('no_baby_alerts'))
        
        with t2:
            st.subheader(_t('daily_task_list_title'))
            task_data = generate_asha_daily_tasks()
            
            st.markdown(f"""
            <div style="background: white; padding: 20px; border-radius: 15px; border: 1px solid #e1e8ed; box-shadow: 0 4px 10px rgba(0,0,0,0.05); margin-bottom: 20px;">
                <h4 style="margin-top:0; color:#333; font-size:1.1rem; border-bottom: 2px solid #f0f2f6; padding-bottom:10px;">📋 {_t('priority_tasks_header')}</h4>
            """, unsafe_allow_html=True)
            
            if not task_data:
                 st.info(_t('task_no_critical'))
            else:
                for i, task_item in enumerate(task_data, 1):
                    t_type = task_item.get("type")
                    t_args = task_item.get("args")
                    
                    icon = "🔘"
                    bg_color = "#f8f9fa"
                    border_color = "#dee2e6"
                    text_color = "#333"
                    
                    if t_type == "followup_high_risk":
                        task_str = _t('task_followup_high_risk').format(*t_args)
                        icon = "🔴"
                        bg_color = "#fff5f5"
                        border_color = "#ffc9c9"
                    elif t_type == "vax_today":
                        m_id, vax, time_val = t_args
                        time_map = {"Today": _t('choice_today'), "Tomorrow": _t('choice_tomorrow')}
                        translated_time = time_map.get(time_val, time_val)
                        task_str = _t('task_vax_today').format(m_id, vax, translated_time)
                        icon = "💉"
                        bg_color = "#f1f3ff"
                        border_color = "#dbe4ff"
                    elif t_type == "routine_visit":
                        task_str = _t('task_routine_visit').format(*t_args)
                        icon = "🏠"
                        bg_color = "#f3f0ff"
                        border_color = "#e5dbff"
                    elif t_type == "no_critical":
                        task_str = _t('task_no_critical')
                        icon = "✅"
                        bg_color = "#ebfbee"
                        border_color = "#d3f9d8"
                    else:
                        task_str = str(task_item)
                        
                    st.markdown(f"""
                    <div style="display:flex; align-items:center; background-color:{bg_color}; padding:12px 15px; border-radius:10px; border-left:5px solid {border_color}; margin-bottom:10px; box-shadow: 0 2px 5px rgba(0,0,0,0.02);">
                        <div style="font-size:1.4rem; margin-right:15px;">{icon}</div>
                        <div style="flex-grow:1; font-weight:500; color:{text_color};">{task_str}</div>
                        <div style="color:#adb5bd; font-size:1.2rem;">⬜</div>
                    </div>
                    """, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            st.subheader(_t('upcoming_vax_title'))
            vax_table = get_upcoming_vaccinations()
            if vax_table:
                df_vt = pd.DataFrame(vax_table)
                st.dataframe(df_vt, use_container_width=True, hide_index=True)
            else:
                st.info(_t('no_upcoming_vax'))

    elif page == "Baby Monitoring":
        st.title(_t('asha_baby_monitoring_title'))
        st.markdown(_t('asha_baby_monitoring_desc'))
        
        from database import get_all_babies, get_baby_vaccinations

        babies = get_all_babies()
        
        if not babies:
            st.info(_t('err_no_baby_records'))
        else:
            baby_data = []
            now_dt = datetime.datetime.now()
            
            for b in babies:
                mother_id, mother_name, village, delivery_date_str = b
                try:
                    delivery_dt = datetime.datetime.strptime(delivery_date_str, "%Y-%m-%d")
                    months_old = max(0, (now_dt - delivery_dt).days // 30)
                except:
                    months_old = 0
                    
                vaccines = get_baby_vaccinations(mother_id)
                next_vax = "None"
                is_overdue = False
                for v in vaccines:
                    if v[4] == 'Pending':
                        v_name = v[2]
                        due_dt = datetime.datetime.strptime(v[3], "%Y-%m-%d")
                        if (due_dt - now_dt).days < 0:
                            next_vax = _t('vax_overdue_table').format(v_name)
                            is_overdue = True
                        else:
                            next_vax = v_name
                        break
                        
                baby_data.append({
                    _t('mother_id'): mother_id,
                    _t('mother_name'): mother_name,
                    _t('col_village'): village,
                    _t('baby_age'): f"{months_old} {_t('months_label')}",
                    _t('col_next_vaccine'): next_vax,
                    "Overdue": is_overdue
                })
                
            df_babies = pd.DataFrame(baby_data)
            
            # Highlight overdue vaccines
            def highlight_overdue(row):
                if row['Overdue']:
                    return ['background-color: #ffe6e6'] * len(row)
                return [''] * len(row)
                
            st.dataframe(df_babies.style.apply(highlight_overdue, axis=1), use_container_width=True, hide_index=True)
            
            st.markdown("---")
            st.subheader(_t('send_sms_reminders'))
            rem_mother_id = st.text_input(_t('enter_mother_id_rem'))
            if st.button(_t('btn_send_fast2sms'), type="primary"):
                if rem_mother_id:
                    if is_online():
                        from app import send_sms_alert
                        # In a real scenario we might pass a custom message string 
                        send_sms_alert(rem_mother_id)
                        st.success(_t('success_reminder_sent').format(rem_mother_id))
                    else:
                        from app import render_offline_sms_button
                        render_offline_sms_button(rem_mother_id)
                else:
                    st.error(_t('err_enter_mother_id'))

    elif page == "High Risk Alerts":
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #FF4B2B 0%, #FF416C 100%); padding: 30px; border-radius: 15px; margin-bottom: 25px; color: white; box-shadow: 0 4px 15px rgba(255,75,43,0.3);">
            <h1 style="margin:0; font-size: 2.2rem; display: flex; align-items: center; gap: 10px;">{_t("asha_alerts_title")}</h1>
            <p style="margin: 5px 0 0 0; font-size: 1.1rem; opacity: 0.9;">{_t("asha_alerts_desc")}</p>
        </div>
        """, unsafe_allow_html=True)
        
        conn = sqlite3.connect("maatrisuraksha.db")
        # Optimization: Only show the LATEST active alert per mother to avoid duplicates
        query = """
            WITH LatestActiveAlerts AS (
                SELECT *, 
                       ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY timestamp DESC) as rn
                FROM alerts 
                WHERE status = 'Active'
            )
            SELECT a.id as alert_db_id, 
                   COALESCE(u.name, 'Unknown') as mother_name,
                   COALESCE(u.unique_id, a.user_id) as mother_id_display,
                   a.user_id as raw_user_id,
                   u.village, a.risk_level, a.status, a.timestamp, 
                   (SELECT risk_score FROM daily_logs WHERE user_id = u.id OR user_id = u.unique_id ORDER BY date DESC LIMIT 1) as risk_score
            FROM LatestActiveAlerts a
            LEFT JOIN users u ON CAST(a.user_id AS TEXT) = CAST(u.unique_id AS TEXT) OR CAST(a.user_id AS TEXT) = CAST(u.id AS TEXT)
            WHERE a.rn = 1
        """
        df_alerts = pd.read_sql_query(query, conn)
        conn.close()
        
        if df_alerts.empty:
            st.success("✅ No active high-risk alerts. All mothers are stable.")
        else:
            if not df_alerts.empty:
                df_alerts['Mother ID'] = df_alerts['mother_name'] + " (" + df_alerts['mother_id_display'].astype(str) + ")"
                df_alerts.rename(columns={
                    "alert_db_id": "Alert ID",
                    "village": "Village",
                    "risk_level": "Risk Level",
                    "risk_score": "Risk Score",
                    "timestamp": "Date",
                    "status": "Alert Status"
                }, inplace=True)
                # Sort by Risk Score descending (highest risk first)
                df_alerts = df_alerts.sort_values(by="Risk Score", ascending=False)

                # Display table with Streamlit configuration
                # We use a copy for display to keep raw columns available for the selectbox map below
                display_cols = ["Alert ID", "Mother ID", "Village", "Risk Level", "Risk Score", "Date", "Alert Status"]
                display_df = df_alerts[display_cols].copy()
                
                # Translate table columns for rendering
                display_df.columns = [_t("col_alert_id"), _t("col_mother_id"), _t("col_village"), _t("col_risk_level"), _t("col_risk_score"), _t("col_date"), _t("col_alert_status")]

                st.dataframe(
                    display_df,
                    use_container_width=True, 
                    hide_index=True
                )
                
                st.markdown("<hr>", unsafe_allow_html=True)
                
                # Action Section
                act_col1, act_col2 = st.columns(2)
                
                with act_col1:
                    st.markdown(f"### 📍 {_t('ash_heatmap')}")
                    # Map display names to raw IDs for internal logic
                    mother_display_map = {f"{row['mother_name']} ({row['mother_id_display']})": row['raw_user_id'] for _, row in df_alerts.iterrows()}
                    focus_display = st.selectbox(_t("select_focus_mother"), list(mother_display_map.keys()))
                    focus_id = mother_display_map[focus_display]
                    
                    if st.button(_t("btn_view_map"), type="primary", use_container_width=True):
                        st.session_state['asha_page'] = "Geospatial Heatmap"
                        st.session_state['map_focus_mother'] = focus_id
                        st.rerun()
                
                with act_col2:
                    st.markdown(f"### " + _t("resolve_alerts_title"))
                    resolve_display = st.selectbox(_t("select_mother_to_resolve"), list(mother_display_map.keys()), key="resolve_select")
                    resolve_id = mother_display_map[resolve_display]
                    
                    if st.button("✅ " + _t("btn_mark_resolved"), type="primary", use_container_width=True):
                        try:
                            from database import resolve_alert
                            resolve_alert(resolve_id)
                            st.success(_t("alert_resolved_success").format(resolve_id))
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error resolving alert: {e}")

    elif page == "All Mothers":
        st.title("👩 All Monitored Mothers")
        st.markdown("Complete directory of assigned cases.")
        conn = sqlite3.connect("maatrisuraksha.db")
        # Fetch latest log for each mother joined with user info
        query_all = """
            WITH LatestLogs AS (
                SELECT user_id, risk_level, risk_score, mood, date
                FROM daily_logs
                WHERE id IN (
                    SELECT MAX(id)
                    FROM daily_logs
                    GROUP BY user_id
                )
            )
            SELECT u.unique_id as 'Mother ID', 
                   COALESCE(l.risk_level, 'Low') as 'Risk Level', 
                   COALESCE(l.risk_score, 0) as 'Risk Score', 
                   COALESCE(l.mood, 'Unknown') as 'Mood',
                   COALESCE(l.date, 'No Logs') as 'Date',
                   u.village as 'Village'
            FROM users u
            LEFT JOIN LatestLogs l ON u.unique_id = l.user_id
            WHERE u.role = 'Mother'
        """
        df_all = pd.read_sql_query(query_all, conn)
        conn.close()
        
        if df_all.empty:
            st.info("No mothers registered yet.")
            df_all = pd.DataFrame(columns=["Mother ID", "Risk Level", "Risk Score", "Mood", "Date", "Village"])
            
        # Fetch exercise logs separately and merge
        try:
            from database import get_latest_exercise_log_for_all_mothers
            ex_logs = get_latest_exercise_log_for_all_mothers()
            if ex_logs:
                df_ex = pd.DataFrame(ex_logs, columns=["Mother ID", "Name", _t("asha_ex_activity"), _t("asha_ex_last_updated")])
                df_all = pd.merge(df_all, df_ex[["Mother ID", _t("asha_ex_activity"), _t("asha_ex_last_updated")]], on="Mother ID", how="left")
                df_all[_t("asha_ex_activity")] = df_all[_t("asha_ex_activity")].fillna("None")
                df_all[_t("asha_ex_last_updated")] = df_all[_t("asha_ex_last_updated")].fillna("N/A")
            else:
                df_all[_t("asha_ex_activity")] = "None"
                df_all[_t("asha_ex_last_updated")] = "N/A"
        except Exception as e:
            df_all[_t("asha_ex_activity")] = "None"
            df_all[_t("asha_ex_last_updated")] = "N/A"
            
        # Filters
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            risk_filter = st.selectbox(_t("filter_risk_label"), [_t("show_all"), _t("risk_high"), _t("risk_med"), _t("risk_low")])
        with col_f2:
            sort_order = st.radio(_t("sort_order_label"), [_t("high_first"), _t("low_first")], horizontal=True)
            
        # Apply filters
        if risk_filter != _t("show_all"):
            df_all = df_all[df_all["Risk Level"] == risk_filter]
            
        # Apply sort
        ascending_sort = False if sort_order == _t("high_first") else True
        df_all = df_all.sort_values(by="Risk Score", ascending=ascending_sort)
        
        st.dataframe(df_all, use_container_width=True, hide_index=True)

    elif page == "Risk Trends":
        st.title(_t("asha_trends_title"))
        st.markdown(_t("asha_trends_desc"))
        
        mother_id = st.text_input(_t("enter_mother_id"))
        
        if st.button(_t("btn_gen_chart")):
            if mother_id:
                st.info(f"Generating 14-day trend for {mother_id}...")
                # Plotly Trend Chart
                
                dates = [(datetime.datetime.now() - datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(14, 0, -1)]
                # Mock trend: getting worse over two weeks
                scores = np.random.randint(20, 90, size=14)
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=dates, y=scores, mode='lines+markers', name=_t('col_risk_score'), line=dict(color='#dc3545', width=3)))
                
                fig.update_layout(
                    title=_t("chart_title_trend").format(mother_id),
                    xaxis_title=_t("xaxis_date"),
                    yaxis_title=_t("yaxis_score"),
                    template="plotly_white"
                )
                
                # Threshold lines
                fig.add_hline(y=75, line_dash="dash", line_color="red", annotation_text=_t("high_threshold"))
                fig.add_hline(y=40, line_dash="dash", line_color="orange", annotation_text=_t("med_threshold"))
                
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning(_t("err_id_name_missing"))

    elif page == "Search Mother":
        st.title(_t("asha_search_title"))
        mother_id = st.text_input(_t("scan_id_label"), placeholder=_t("scan_id_placeholder"))
        
        if st.button(_t("btn_fetch_records")):
            if not mother_id:
                st.error(_t("err_enter_id"))
            else:
                with st.spinner(_t("fetching_db")):
                    time.sleep(1) # Simulate DB fetch
                    st.success(_t("record_found").format(mother_id))
                    
                    st.markdown(f"### {_t('recent_summary_sub')}")
                    st.write(f"**{_t('last_checked')}**: Today, 10:45 AM")
                    st.write(f"**{_t('search_risk_score')}**: 72")
                    st.write(f"**{_t('search_symptoms')}**: Swelling, Mild Headache")
                    st.info(f"**{_t('ai_note_label')}**: Trimester 2. BP slightly elevated. Monitor every 4 hours.")

    elif page == "Register Mother":
        st.title(_t("asha_register_title"))
        st.markdown(_t("asha_register_desc"))
        
        with st.form("reg_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_id = st.text_input(_t("new_id_label"), placeholder=_t("new_id_placeholder"))
                new_name = st.text_input(_t("new_name_label"), placeholder=_t("new_name_placeholder"))
            with col2:
                new_phone = st.text_input(_t("new_phone_label"), placeholder=_t("new_phone_placeholder"))
                new_village = st.text_input(_t("new_village_label"), placeholder=_t("new_village_placeholder"))
            
            submit_register = st.form_submit_button(_t("btn_register_mother"), type="primary")
            
            if submit_register:
                if not new_id.strip() or not new_name.strip() or not new_village.strip():
                    st.error(_t("err_fill_all_req"))
                else:
                    # Mock registration logic
                    # For actual implementation, call register_mother function
                    # success = register_mother(new_id.strip(), new_name.strip(), new_phone.strip(), new_village.strip())
                    # if success:
                    st.success(_t("success_reg_mother").format(new_name.strip(), new_id.strip()))
                    # else:
                    #     st.error(f"❌ ID '{new_id.strip()}' is already taken. Please assign a different Unique ID.")

def logout():
    """Clear session data and return to login."""
    st.session_state['logged_in'] = False
    st.session_state['role'] = None
    st.rerun()

def render_footer():
    """Render the permanent bottom footer."""
    st.markdown("""
        <div class="custom-footer">
            <div>&copy; 2026 MAATRI SURAKSHA AI. All Rights Reserved.</div>
            <div class="footer-links">
                <a href="#">Privacy Policy</a> | <a href="#">Terms of Service</a> | <a href="#">Help Center</a>
            </div>
        </div>
    """, unsafe_allow_html=True)

def splash_screen():
    """Display the initial splash screen for 2 seconds."""
    import base64
    import os
    
    bg_image_base64 = ""
    # Load the background image if it exists
    if os.path.exists("splash_bg.png"):
        with open("splash_bg.png", "rb") as image_file:
            bg_image_base64 = base64.b64encode(image_file.read()).decode()
            
    bg_style = ""
    if bg_image_base64:
        bg_style = f"""
        .stApp {{
            background: linear-gradient(rgba(11, 83, 148, 0.75), rgba(61, 133, 198, 0.75)), url(data:image/png;base64,{bg_image_base64});
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            animation: fadeIn 1.5s ease-in-out;
        }}
        """
    else:
        bg_style = """
        .stApp {{
            background: linear-gradient(rgba(11, 83, 148, 0.8), rgba(61, 133, 198, 0.8));
            animation: fadeIn 1.5s ease-in-out;
        }}
        """

    st.markdown(f"""
        <style>
        {bg_style}
        #MainMenu {{visibility: hidden;}}
        footer {{visibility: hidden;}}
        
        @keyframes fadeIn {{
            0% {{ opacity: 0; }}
            100% {{ opacity: 1; }}
        }}
        
        @keyframes textPulse {{
            0% {{ transform: scale(1); opacity: 0.8; text-shadow: 0px 0px 10px rgba(255,255,255,0.5); }}
            50% {{ transform: scale(1.05); opacity: 1; text-shadow: 0px 0px 20px rgba(255,255,255,0.9); }}
            100% {{ transform: scale(1); opacity: 0.8; text-shadow: 0px 0px 10px rgba(255,255,255,0.5); }}
        }}
        
        .splash-container {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100vh;
            text-align: center;
        }}
        
        .splash-title {{
            font-family: 'Inter', sans-serif;
            color: white !important;
            font-size: 18rem;
            font-weight: 900;
            text-align: center;
            text-shadow: 0px 0px 40px rgba(0, 0, 0, 0.95), 0px 0px 70px rgba(0, 0, 0, 0.6);
            letter-spacing: 5px;
            animation: textPulse 3s infinite ease-in-out;
            margin: 0;
            padding: 20px;
            line-height: 1.1;
            z-index: 1000;
        }}
        
        .full-screen-center {{
            display: flex;
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            justify-content: center;
            align-items: center;
            z-index: 999;
            pointer-events: none;
        }}

        /* Clean up default Streamlit elements during splash */
        [data-testid="stSidebar"], [data-testid="stHeader"] {{
            display: none !important;
        }}
        </style>
        <div class="full-screen-center">
            <h1 class="splash-title">MAATRI SURAKSHA AI</h1>
        </div>
    """, unsafe_allow_html=True)
            
    time.sleep(2)
    st.session_state['splash_shown'] = True
    st.rerun()

def main():
    init_session_state()
    # Process any pending offline data if online
    process_offline_sync()
    
    if not st.session_state.get('splash_shown', False):
        splash_screen()
        return
        
    if not st.session_state.get('logged_in', False):
        login_page()
    else:
        # Session-Based Routing to Respective Dashboards
        role = st.session_state.get('role')
        if role == "Mother":
            mother_dashboard()
        elif role == "ASHA Worker":
            asha_worker_dashboard()
        elif role == "Baby Care":
            baby_dashboard()
            
    # Always render footer at the very end
    render_footer()

if __name__ == "__main__":
    main()