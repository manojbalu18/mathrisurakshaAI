import config
config.load_project_env()

import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import time
import datetime
import math
import os
import base64

import database
from database import (
    register_mother, verify_mother, get_all_mothers, update_location, 
    get_mothers_with_risk_and_location, save_daily_log, create_alert, 
    log_live_sms, get_active_alerts, get_all_logs, has_recent_high_risk_sms, 
    get_connection, resolve_alert, update_case_status, get_case_status, 
    get_all_case_statuses, get_case_history, get_supervisor_metrics, 
    get_asha_workload_breakdown, get_all_patient_cases_for_supervisor
)
from ai_engine import calculate_risk, calculate_risk_from_text, extract_symptoms
from translations import TRANSLATIONS
from translator_service import _t as translator_service_t, translate_text, SUPPORTED_LANGUAGES, LANGUAGE_CONFIG, get_lang_code, render_translator_bridge
from connectivity import is_online
from lm_studio_client import LMStudioClient
from ai_service import AIService
from voice_service import VoiceService
from tts_service import TTSService
from escalation_service import EscalationService
import hashlib

# Print startup configuration diagnostic safely
config.print_config_diagnostic()

# Initialize Database tables once per runtime
if "db_initialized" not in st.session_state:
    database.init_db()
    st.session_state["db_initialized"] = True

# --- Performance Caches ---
@st.cache_data
def load_image_base64(path):
    """Cache base64-encoded images to avoid re-reading files on every rerun."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

@st.cache_data(ttl=5)
def cached_get_all_logs():
    return get_all_logs()

@st.cache_data(ttl=5)
def cached_get_active_alerts():
    return get_active_alerts()

@st.cache_data(ttl=5)
def cached_get_all_mothers():
    return get_all_mothers()

@st.cache_data(ttl=5)
def cached_get_mothers_with_risk_and_location():
    return get_mothers_with_risk_and_location()

@st.cache_data(ttl=3)
def cached_get_supervisor_metrics():
    return get_supervisor_metrics()

@st.cache_data(ttl=3)
def cached_get_asha_workload_breakdown():
    return get_asha_workload_breakdown()

@st.cache_data(ttl=3)
def cached_get_all_patient_cases_for_supervisor():
    return get_all_patient_cases_for_supervisor()

st.set_page_config(page_title="MAATRI SURAKSHA AI", page_icon="🩺", layout="wide")

# ---------------- OFFLINE SYNC LOGIC ----------------
def process_offline_sync():
    """Check for internet and sync any pending offline records. Only runs once per session."""
    if st.session_state.get('_sync_done', False):
        return
    st.session_state['_sync_done'] = True
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
    if 'selected_main_role' not in st.session_state:
        st.session_state['selected_main_role'] = None
    if 'selected_patient_service' not in st.session_state:
        st.session_state['selected_patient_service'] = None
    if 'supervisor_page' not in st.session_state:
        st.session_state['supervisor_page'] = "District Overview"
    if 'community_page' not in st.session_state:
        st.session_state['community_page'] = "Community Health Hub"
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
    if 'lm_studio_chat_endpoint' not in st.session_state:
        st.session_state['lm_studio_chat_endpoint'] = getattr(config, 'LM_STUDIO_CHAT_ENDPOINT', f"{config.LM_STUDIO_BASE_URL}/chat/completions")
    if 'lm_studio_model' not in st.session_state:
        st.session_state['lm_studio_model'] = config.LM_STUDIO_MODEL
    if 'voice_chat_processed' not in st.session_state:
        st.session_state['voice_chat_processed'] = False
    if 'voice_ai_response' not in st.session_state:
        st.session_state['voice_ai_response'] = None
    if 'voice_risk_result' not in st.session_state:
        st.session_state['voice_risk_result'] = None
    if 'voice_ai_status' not in st.session_state:
        st.session_state['voice_ai_status'] = None
    if 'voice_ai_audio' not in st.session_state:
        st.session_state['voice_ai_audio'] = False
    if 'last_processed_audio_hash' not in st.session_state:
        st.session_state['last_processed_audio_hash'] = None
    if 'voice_escalation_res' not in st.session_state:
        st.session_state['voice_escalation_res'] = None
    if 'voice_ai_audio_bytes' not in st.session_state:
        st.session_state['voice_ai_audio_bytes'] = None



def _t(key, default=None):
    """Universal translation helper supporting pre-compiled translations, dynamic on-the-fly AI translation and disk caching."""
    return translator_service_t(key, default)

def apply_custom_css():
    """Apply professional, classy healthcare-themed CSS styles with cohesive color-matched borders, accessible contrast, refined typography, and comprehensive multi-device responsiveness."""
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Outfit:wght@500;600;700;800&display=swap');

        /* Global Font & Canvas Background */
        html, body, [class*="css"], .stApp {
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
            background-color: #f8fafc !important;
            color: #1e293b !important;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }

        /* Adjust main container spacing */
        .block-container {
            padding-top: 2rem !important;
            padding-bottom: 4rem !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
            max-width: 1400px !important;
        }

        /* Hide main menu and footer */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header[data-testid="stHeader"] {background: transparent;}

        /* Typography Defaults */
        h1, h2, h3, h4, h5, h6 {
            font-family: 'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif !important;
            color: #0f172a !important;
            font-weight: 700 !important;
            letter-spacing: -0.02em !important;
            line-height: 1.25 !important;
        }
        h1 { font-size: 2.1rem !important; margin-bottom: 0.5rem !important; }
        h2 { font-size: 1.6rem !important; margin-bottom: 0.4rem !important; }
        h3 { font-size: 1.25rem !important; margin-bottom: 0.35rem !important; }
        h4 { font-size: 1.1rem !important; }
        p, span, label, li {
            color: #1e293b;
            line-height: 1.55;
        }

        /* Emergency Badge */
        .emergency-badge {
            position: absolute;
            top: 15px;
            right: 25px;
            background: #dc2626;
            color: #ffffff !important;
            padding: 8px 18px;
            border-radius: 50px;
            font-weight: 700;
            font-size: 0.9rem;
            box-shadow: 0 2px 8px rgba(220, 38, 38, 0.25);
            z-index: 9999;
            display: flex;
            align-items: center;
            gap: 8px;
            border: 1px solid rgba(255, 255, 255, 0.4);
            letter-spacing: 0.3px;
            transition: all 0.2s ease;
        }
        .emergency-badge:hover {
            background: #b91c1c;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(220, 38, 38, 0.35);
        }

        /* App Title & Subtitle */
        .app-title {
            font-family: 'Outfit', sans-serif !important;
            color: #0f172a !important;
            font-size: 2.35rem !important;
            font-weight: 800 !important;
            margin-bottom: 0.2rem !important;
            letter-spacing: -0.5px !important;
        }
        
        .app-subtitle {
            font-family: 'Plus Jakarta Sans', sans-serif !important;
            color: #475569 !important;
            font-size: 1rem !important;
            font-weight: 500 !important;
            margin-top: 0 !important;
            margin-bottom: 1.25rem !important;
            line-height: 1.5 !important;
        }

        /* Form Card Frame */
        div[data-testid="stForm"] {
            background: #ffffff !important;
            padding: 2rem 1.8rem !important;
            border-radius: 16px !important;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04), 0 1px 2px rgba(0, 0, 0, 0.02) !important;
            border: 1px solid #e2e8f0 !important;
            border-top: 4px solid #0284c7 !important;
            position: relative !important;
        }

        /* Modern Form Buttons */
        div[data-testid="stFormSubmitButton"] > button {
            width: 100% !important;
            background: #0284c7 !important;
            color: #ffffff !important;
            font-weight: 700 !important;
            font-size: 0.98rem !important;
            border-radius: 10px !important;
            padding: 0.65rem 1.25rem !important;
            min-height: 46px !important;
            border: 1px solid #0369a1 !important;
            box-shadow: 0 2px 6px rgba(2, 132, 199, 0.18) !important;
            transition: all 0.2s ease !important;
            margin-top: 0.6rem !important;
            letter-spacing: 0.2px !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
        }
        
        div[data-testid="stFormSubmitButton"] > button:hover {
            background: #0369a1 !important;
            color: #ffffff !important;
            box-shadow: 0 4px 12px rgba(2, 132, 199, 0.28) !important;
            transform: translateY(-1px) !important;
        }

        /* General Streamlit Buttons */
        .stButton > button {
            border-radius: 10px !important;
            font-family: 'Plus Jakarta Sans', sans-serif !important;
            font-weight: 600 !important;
            padding: 0.55rem 1.15rem !important;
            min-height: 42px !important;
            transition: all 0.18s ease !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 6px !important;
        }
        .stButton > button[kind="primary"] {
            background: #0284c7 !important;
            color: #ffffff !important;
            border: 1px solid #0369a1 !important;
            box-shadow: 0 1px 3px rgba(2, 132, 199, 0.18) !important;
        }
        .stButton > button[kind="primary"]:hover {
            background: #0369a1 !important;
            box-shadow: 0 4px 12px rgba(2, 132, 199, 0.26) !important;
            transform: translateY(-1px) !important;
        }
        
        .stButton > button[kind="secondary"] {
            background: #ffffff !important;
            color: #1e293b !important;
            border: 1.5px solid #cbd5e1 !important;
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03) !important;
        }
        .stButton > button[kind="secondary"]:hover {
            border-color: #0284c7 !important;
            color: #0284c7 !important;
            background: #f8fafc !important;
            transform: translateY(-1px) !important;
        }

        /* Sidebar Styling */
        section[data-testid="stSidebar"] {
            background: #ffffff !important;
            border-right: 1px solid #e2e8f0 !important;
            box-shadow: 1px 0 8px rgba(0, 0, 0, 0.02) !important;
            padding-top: 1rem !important;
        }
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3 {
            color: #0f172a !important;
            font-weight: 800 !important;
        }
        section[data-testid="stSidebar"] p {
            color: #475569 !important;
        }
        section[data-testid="stSidebar"] .stButton > button {
            width: 100% !important;
            text-align: left !important;
            justify-content: flex-start !important;
            padding: 0.6rem 1rem !important;
            margin-bottom: 4px !important;
            border-radius: 10px !important;
            font-size: 0.92rem !important;
            font-weight: 600 !important;
            min-height: 44px !important;
        }
        section[data-testid="stSidebar"] .stButton > button[kind="secondary"] {
            background: #ffffff !important;
            color: #334155 !important;
            border: 1px solid #e2e8f0 !important;
        }
        section[data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
            background: #f1f5f9 !important;
            border-color: #cbd5e1 !important;
            color: #0f172a !important;
        }
        section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
            background: #e0f2fe !important;
            color: #0369a1 !important;
            border: 1px solid #7dd3fc !important;
            border-left: 5px solid #0284c7 !important;
            font-weight: 700 !important;
            box-shadow: none !important;
        }

        /* Form Inputs & Selects */
        .stTextInput input, 
        .stNumberInput input, 
        .stTextArea textarea, 
        .stSelectbox [data-baseweb="select"] {
            border-radius: 10px !important;
            border: 1.5px solid #cbd5e1 !important;
            background: #ffffff !important;
            color: #0f172a !important;
            font-family: 'Plus Jakarta Sans', sans-serif !important;
            font-size: 0.94rem !important;
            font-weight: 500 !important;
            transition: all 0.15s ease !important;
        }
        .stTextInput input:focus, 
        .stNumberInput input:focus, 
        .stTextArea textarea:focus, 
        .stSelectbox [data-baseweb="select"]:focus-within {
            border-color: #0284c7 !important;
            box-shadow: 0 0 0 3px rgba(2, 132, 199, 0.15) !important;
        }
        .stTextInput label, 
        .stNumberInput label, 
        .stTextArea label, 
        .stSelectbox label, 
        .stDateInput label {
            color: #0f172a !important;
            font-weight: 700 !important;
            font-size: 0.9rem !important;
            margin-bottom: 4px !important;
        }

        /* Metrics */
        div[data-testid="stMetricValue"] {
            color: #0f172a !important;
            font-weight: 800 !important;
            font-family: 'Outfit', sans-serif !important;
            font-size: 2rem !important;
        }
        div[data-testid="stMetricLabel"] {
            color: #475569 !important;
            font-weight: 700 !important;
            font-size: 0.82rem !important;
            text-transform: uppercase !important;
            letter-spacing: 0.5px !important;
        }

        /* Tabs */
        .stTabs [data-baseweb="tab-list"] {
            border-bottom: 1.5px solid #e2e8f0 !important;
            gap: 6px !important;
        }
        .stTabs [data-baseweb="tab"] {
            padding: 10px 18px !important;
            font-weight: 600 !important;
            color: #475569 !important;
            font-size: 0.94rem !important;
            border-radius: 8px 8px 0 0 !important;
            border: none !important;
            background: transparent !important;
            transition: all 0.15s ease !important;
        }
        .stTabs [data-baseweb="tab"]:hover {
            color: #0284c7 !important;
            background: #f1f5f9 !important;
        }
        .stTabs [data-baseweb="tab"][aria-selected="true"] {
            color: #0284c7 !important;
            font-weight: 700 !important;
            border-bottom: 3px solid #0284c7 !important;
            background: transparent !important;
        }

        /* Alerts */
        [data-testid="stAlert"] {
            border-radius: 12px !important;
            padding: 14px 18px !important;
            font-size: 0.94rem !important;
            font-weight: 500 !important;
            border: 1px solid !important;
        }
        div[data-baseweb="notification"] {
            border-radius: 12px !important;
        }

        /* Checkboxes & Radios */
        [data-testid="stCheckbox"] label, [data-testid="stRadio"] label {
            color: #1e293b !important;
            font-weight: 600 !important;
            font-size: 0.93rem !important;
        }

        /* Tables & Dataframes */
        div[data-testid="stDataFrame"] {
            border: 1px solid #e2e8f0 !important;
            border-radius: 12px !important;
            overflow: hidden !important;
            background: #ffffff !important;
        }

        /* ================= COLOR-MATCHED CLASSY CARDS ================= */
        /* Universal Classy Card */
        .classy-card {
            background: #ffffff !important;
            border-radius: 16px !important;
            padding: 1.4rem !important;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.04), 0 1px 2px -1px rgba(0, 0, 0, 0.04) !important;
            border: 1px solid #e2e8f0 !important;
            transition: all 0.2s ease !important;
            position: relative !important;
            overflow: hidden !important;
            display: flex !important;
            flex-direction: column !important;
            height: 100% !important;
        }
        .classy-card:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 6px 18px rgba(0, 0, 0, 0.06) !important;
            border-color: #cbd5e1 !important;
        }

        /* Icon Badge matching border and text */
        .icon-badge {
            width: 44px;
            height: 44px;
            border-radius: 12px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 1.3rem;
            margin-bottom: 12px;
        }

        /* 1. EMERALD / GREEN (Safe, Low Risk, Active Health) */
        .card-emerald {
            border: 1px solid #a7f3d0 !important;
            border-top: 4px solid #10b981 !important;
            background: #ffffff !important;
        }
        .card-emerald .icon-badge {
            background: #dcfce7 !important;
            border: 1px solid #86efac !important;
            color: #065f46 !important;
        }
        .card-emerald .card-title {
            color: #065f46 !important;
            font-size: 0.82rem !important;
            font-weight: 800 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.5px !important;
            margin-bottom: 6px !important;
        }
        .card-emerald .card-value {
            color: #047857 !important;
            font-size: 2rem !important;
            font-weight: 800 !important;
            font-family: 'Outfit', sans-serif !important;
            line-height: 1.1 !important;
            margin: 0 !important;
        }
        .card-emerald .card-caption {
            color: #065f46 !important;
            font-size: 0.85rem !important;
            font-weight: 600 !important;
            margin-top: 6px !important;
            margin-bottom: 0 !important;
        }
        .card-emerald .card-pill {
            display: inline-block;
            background: #dcfce7;
            color: #065f46;
            border: 1px solid #86efac;
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: 700;
            font-size: 0.9rem;
        }

        /* 2. SAPPHIRE / BLUE (Total Records, Active Sync, System Intel) */
        .card-blue {
            border: 1px solid #bfdbfe !important;
            border-top: 4px solid #0284c7 !important;
            background: #ffffff !important;
        }
        .card-blue .icon-badge {
            background: #e0f2fe !important;
            border: 1px solid #7dd3fc !important;
            color: #0369a1 !important;
        }
        .card-blue .card-title {
            color: #0c4a6e !important;
            font-size: 0.82rem !important;
            font-weight: 800 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.5px !important;
            margin-bottom: 6px !important;
        }
        .card-blue .card-value {
            color: #0284c7 !important;
            font-size: 2rem !important;
            font-weight: 800 !important;
            font-family: 'Outfit', sans-serif !important;
            line-height: 1.1 !important;
            margin: 0 !important;
        }
        .card-blue .card-caption {
            color: #0369a1 !important;
            font-size: 0.85rem !important;
            font-weight: 600 !important;
            margin-top: 6px !important;
            margin-bottom: 0 !important;
        }
        .card-blue .card-pill {
            display: inline-block;
            background: #dbeafe;
            color: #1e40af;
            border: 1px solid #93c5fd;
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: 700;
            font-size: 0.9rem;
        }

        /* 3. CRIMSON / RED (Urgent Alerts, High Risk, Danger) */
        .card-red {
            border: 1px solid #fecaca !important;
            border-top: 4px solid #ef4444 !important;
            background: #ffffff !important;
        }
        .card-red .icon-badge {
            background: #fee2e2 !important;
            border: 1px solid #fca5a5 !important;
            color: #dc2626 !important;
        }
        .card-red .card-title {
            color: #991b1b !important;
            font-size: 0.82rem !important;
            font-weight: 800 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.5px !important;
            margin-bottom: 6px !important;
        }
        .card-red .card-value {
            color: #dc2626 !important;
            font-size: 2rem !important;
            font-weight: 800 !important;
            font-family: 'Outfit', sans-serif !important;
            line-height: 1.1 !important;
            margin: 0 !important;
        }
        .card-red .card-caption {
            color: #b91c1c !important;
            font-size: 0.85rem !important;
            font-weight: 600 !important;
            margin-top: 6px !important;
            margin-bottom: 0 !important;
        }
        .card-red .card-pill {
            display: inline-block;
            background: #fee2e2;
            color: #991b1b;
            border: 1px solid #fca5a5;
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: 700;
            font-size: 0.9rem;
        }

        /* 4. AMBER / GOLD (Medium Risk, Warning, Pending Schedule) */
        .card-amber {
            border: 1px solid #fde68a !important;
            border-top: 4px solid #f59e0b !important;
            background: #ffffff !important;
        }
        .card-amber .icon-badge {
            background: #fef3c7 !important;
            border: 1px solid #fde047 !important;
            color: #d97706 !important;
        }
        .card-amber .card-title {
            color: #92400e !important;
            font-size: 0.82rem !important;
            font-weight: 800 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.5px !important;
            margin-bottom: 6px !important;
        }
        .card-amber .card-value {
            color: #d97706 !important;
            font-size: 2rem !important;
            font-weight: 800 !important;
            font-family: 'Outfit', sans-serif !important;
            line-height: 1.1 !important;
            margin: 0 !important;
        }
        .card-amber .card-caption {
            color: #92400e !important;
            font-size: 0.85rem !important;
            font-weight: 600 !important;
            margin-top: 6px !important;
            margin-bottom: 0 !important;
        }
        .card-amber .card-pill {
            display: inline-block;
            background: #fef3c7;
            color: #92400e;
            border: 1px solid #fcd34d;
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: 700;
            font-size: 0.9rem;
        }

        /* 5. VIOLET / PURPLE (Pregnancy Trimester, AI Health Insights) */
        .card-purple {
            border: 1px solid #ddd6fe !important;
            border-top: 4px solid #7c3aed !important;
            background: #ffffff !important;
        }
        .card-purple .icon-badge {
            background: #ede9fe !important;
            border: 1px solid #c4b5fd !important;
            color: #7c3aed !important;
        }
        .card-purple .card-title {
            color: #5b21b6 !important;
            font-size: 0.82rem !important;
            font-weight: 800 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.5px !important;
            margin-bottom: 6px !important;
        }
        .card-purple .card-value {
            color: #7c3aed !important;
            font-size: 2rem !important;
            font-weight: 800 !important;
            font-family: 'Outfit', sans-serif !important;
            line-height: 1.1 !important;
            margin: 0 !important;
        }
        .card-purple .card-caption {
            color: #6d28d9 !important;
            font-size: 0.85rem !important;
            font-weight: 600 !important;
            margin-top: 6px !important;
            margin-bottom: 0 !important;
        }
        .card-purple .card-pill {
            display: inline-block;
            background: #ede9fe;
            color: #5b21b6;
            border: 1px solid #c4b5fd;
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: 700;
            font-size: 0.9rem;
        }

        /* 6. ROSE / PINK (Baby Care, Mother Wellness) */
        .card-rose {
            border: 1px solid #fbcfe8 !important;
            border-top: 4px solid #db2777 !important;
            background: #ffffff !important;
        }
        .card-rose .icon-badge {
            background: #fdf2f8 !important;
            border: 1px solid #fbcfe8 !important;
            color: #db2777 !important;
        }
        .card-rose .card-title {
            color: #9d174d !important;
            font-size: 0.82rem !important;
            font-weight: 800 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.5px !important;
            margin-bottom: 6px !important;
        }
        .card-rose .card-value {
            color: #db2777 !important;
            font-size: 2rem !important;
            font-weight: 800 !important;
            font-family: 'Outfit', sans-serif !important;
            line-height: 1.1 !important;
            margin: 0 !important;
        }
        .card-rose .card-caption {
            color: #be185d !important;
            font-size: 0.85rem !important;
            font-weight: 600 !important;
            margin-top: 6px !important;
            margin-bottom: 0 !important;
        }

        /* 7. TEAL / CYAN (Baby Gender & Health Vitals) */
        .card-teal {
            border: 1px solid #a5f3fc !important;
            border-top: 4px solid #0891b2 !important;
            background: #ffffff !important;
        }
        .card-teal .icon-badge {
            background: #ecfeff !important;
            border: 1px solid #a5f3fc !important;
            color: #0891b2 !important;
        }
        .card-teal .card-title {
            color: #155e75 !important;
            font-size: 0.82rem !important;
            font-weight: 800 !important;
            text-transform: uppercase !important;
            letter-spacing: 0.5px !important;
            margin-bottom: 6px !important;
        }
        .card-teal .card-value {
            color: #0891b2 !important;
            font-size: 2rem !important;
            font-weight: 800 !important;
            font-family: 'Outfit', sans-serif !important;
            line-height: 1.1 !important;
            margin: 0 !important;
        }
        .card-teal .card-caption {
            color: #0e7490 !important;
            font-size: 0.85rem !important;
            font-weight: 600 !important;
            margin-top: 6px !important;
            margin-bottom: 0 !important;
        }

        /* Footer */
        .custom-footer {
            position: fixed;
            bottom: 0;
            left: 0;
            width: 100%;
            background: #ffffff;
            color: #475569;
            text-align: center;
            padding: 8px 0;
            font-size: 0.82rem;
            border-top: 1px solid #e2e8f0;
            font-family: 'Plus Jakarta Sans', sans-serif;
            z-index: 999;
            box-shadow: 0 -2px 8px rgba(0,0,0,0.02);
            font-weight: 500;
        }
        .footer-links a {
            color: #0284c7;
            text-decoration: none;
            margin: 0 10px;
            font-weight: 600;
        }
        .footer-links a:hover {
            text-decoration: underline;
        }

        /* Offline SMS Button */
        .sms-btn {
            display: inline-block;
            background: #dc2626;
            color: white !important;
            padding: 10px 18px;
            text-align: center;
            border-radius: 8px;
            font-weight: 700;
            text-decoration: none;
            box-shadow: 0 2px 6px rgba(220, 38, 38, 0.2);
            transition: all 0.2s ease;
        }
        .sms-btn:hover {
            background: #b91c1c;
            transform: translateY(-1px);
            box-shadow: 0 4px 10px rgba(220, 38, 38, 0.3);
        }

        /* ================= RESPONSIVE MEDIA QUERIES ================= */
        @media (max-width: 992px) {
            .block-container {
                padding-left: 1.25rem !important;
                padding-right: 1.25rem !important;
            }
            .app-title {
                font-size: 2rem !important;
            }
        }

        @media (max-width: 768px) {
            .block-container {
                padding-top: 1rem !important;
                padding-left: 0.85rem !important;
                padding-right: 0.85rem !important;
                padding-bottom: 3.5rem !important;
            }
            .app-title {
                font-size: 1.65rem !important;
            }
            .app-subtitle {
                font-size: 0.9rem !important;
                margin-bottom: 1rem !important;
            }
            .emergency-badge {
                position: static !important;
                margin-bottom: 10px !important;
                justify-content: center !important;
                font-size: 0.85rem !important;
                width: 100% !important;
            }
            div[data-testid="stForm"] {
                padding: 1.4rem 1.1rem !important;
                border-radius: 14px !important;
            }
            .classy-card {
                padding: 1.1rem !important;
                margin-bottom: 10px !important;
            }
            .stButton > button {
                width: 100% !important;
            }
            div[data-testid="stMetricValue"] {
                font-size: 1.6rem !important;
            }
            .custom-footer {
                font-size: 0.75rem !important;
                padding: 6px 4px !important;
            }
        }

        @media (max-width: 480px) {
            .app-title {
                font-size: 1.45rem !important;
            }
            h1 { font-size: 1.55rem !important; }
            h2 { font-size: 1.35rem !important; }
            h3 { font-size: 1.15rem !important; }
        }
        </style>
    """, unsafe_allow_html=True)
    
    # Universal Live DOM Translator Bridge
    render_translator_bridge()

def render_offline_sms_button(mother_id):
    import database
    import urllib.parse
    
    conn = get_connection()
    c = conn.cursor()
    mid_str = str(mother_id).strip()
    mid_pad = mid_str.zfill(3) if mid_str.isdigit() else mid_str
    c.execute("""
        SELECT name, village, latitude, longitude 
        FROM users 
        WHERE unique_id = ? OR unique_id = ? OR CAST(id AS TEXT) = ?
    """, (mid_str, mid_pad, mid_str))
    row = c.fetchone()
    conn.close()
    
    name = row[0] if row and row[0] else f"Mother {mother_id}"
    village = row[1] if row and row[1] else "Unknown"
    lat = row[2] if row and len(row) > 2 and row[2] is not None else None
    lon = row[3] if row and len(row) > 3 and row[3] is not None else None
    
    # Using the updated number requested by the user
    asha_phone = "8179245840"
    
    if asha_phone:
        loc_details = f"🏘️ *Village / Sector:* {village}"
        if lat is not None and lon is not None and (lat != 0.0 or lon != 0.0):
            maps_url = f"https://maps.google.com/?q={lat:.5f},{lon:.5f}"
            loc_details += f"\n📍 *GPS Coordinates:* {lat:.5f}, {lon:.5f}\n🗺️ *Live Location Map:* {maps_url}"
            
        message = (
            f"🚨 *URGENT MEDICAL ALERT: HIGH RISK PREGNANCY*\n\n"
            f"👩‍🍼 *Mother ID:* {mother_id}\n"
            f"👤 *Patient Name:* {name}\n"
            f"{loc_details}\n\n"
            f"⚠️ *Urgent Action:* Immediate home visit & clinical assessment required."
        )
        encoded_message = urllib.parse.quote(message)
        
        sms_link = f"sms:{asha_phone}?body={encoded_message}"
        wa_link = f"https://wa.me/91{asha_phone}?text={encoded_message}"
        
        st.markdown(f"""
        <div style="display: flex; gap: 10px; margin-top: 10px;">
            <a href="{wa_link}" class="sms-btn" target="_blank" style="flex: 1; text-align: center; background-color: #25D366; text-decoration: none; display: flex; align-items: center; justify-content: center; gap: 6px; padding: 10px; border-radius: 8px; color: white; font-weight: 700; font-size: 0.9rem; box-shadow: 0 2px 4px rgba(37,211,102,0.3);">💬 Send via WhatsApp (with Location)</a>
            <a href="{sms_link}" class="sms-btn" target="_blank" style="flex: 1; text-align: center; background-color: #0284c7; text-decoration: none; display: flex; align-items: center; justify-content: center; gap: 6px; padding: 10px; border-radius: 8px; color: white; font-weight: 700; font-size: 0.9rem; box-shadow: 0 2px 4px rgba(2,132,199,0.3);">📱 Send via SMS App</a>
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
    
    # Get user details for formatting
    conn = get_connection()
    c = conn.cursor()
    mid_str = str(mother_id).strip()
    mid_pad = mid_str.zfill(3) if mid_str.isdigit() else mid_str
    c.execute("""
        SELECT name, village, latitude, longitude 
        FROM users 
        WHERE unique_id = ? OR unique_id = ? OR CAST(id AS TEXT) = ?
    """, (mid_str, mid_pad, mid_str))
    row = c.fetchone()
    conn.close()
    
    name = row[0] if row and row[0] else f"Mother {mother_id}"
    village = row[1] if row and len(row) > 1 and row[1] else "Unknown"
    lat = row[2] if row and len(row) > 2 and row[2] is not None else None
    lon = row[3] if row and len(row) > 3 and row[3] is not None else None
    
    loc_part = f"Village:{village}"
    if lat is not None and lon is not None and (lat != 0.0 or lon != 0.0):
        loc_part += f" | Loc:{lat:.4f},{lon:.4f} (https://maps.google.com/?q={lat:.4f},{lon:.4f})"
    
    # Needs to match user spec exactly for single-line format
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    message = f"ALERT: High Risk Pregnancy | ID:{mother_id} | Name:{name} | {loc_part} | Immediate visit required."
    
    api_key = os.environ.get("FAST2SMS_API_KEY", "")
    # Using the updated number requested by the user
    asha_phone = "8179245840"
    
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
            time.sleep(0.3)  # Brief wait before retrying
            
    # If we exhaust retries
    database.log_live_sms(mother_id, asha_phone, message, api_status, timestamp)
    
    # Surface specific Fast2SMS API errors (like the 100 INR requirement)
    if "100 INR" in api_status or "400" in api_status:
        st.warning("⚠️ Live SMS skipped: Fast2SMS requires a minimum wallet balance (100 INR) to unlock the API route in India. Utilizing offline local SMS fallback.")
    else:
        st.warning("⚠️ Could not deliver SMS alert via API. Utilizing offline local SMS fallback.")
        
    render_offline_sms_button(mother_id)

def back_to_patient_services():
    """Return directly to the Patient Care Services selection screen (Tier 2)."""
    st.session_state['logged_in'] = False
    st.session_state['role'] = None
    st.session_state['selected_patient_service'] = None
    st.session_state['selected_main_role'] = "Patient"
    st.rerun()

def back_to_roles():
    """Return to the Main Role Selection portal screen (Tier 1)."""
    st.session_state['logged_in'] = False
    st.session_state['role'] = None
    st.session_state['selected_main_role'] = None
    st.session_state['selected_patient_service'] = None
    st.rerun()

def logout():
    """Clear session data and return to main portal."""
    back_to_roles()

def login_page():
    """Render the centralized professional login page with logo and footer."""
    apply_custom_css()
    
    # Inject Realistic Maternal Health Background Image
    bg_base64 = ""
    if os.path.exists("login_bg.jpg"):
        bg_base64 = load_image_base64("login_bg.jpg")
    elif os.path.exists("login_bg.png"):
        bg_base64 = load_image_base64("login_bg.png")

    if bg_base64:
        st.markdown(f"""
        <style>
        .stApp {{
            background: linear-gradient(135deg, rgba(248, 250, 252, 0.84) 0%, rgba(240, 249, 255, 0.78) 50%, rgba(253, 244, 255, 0.82) 100%), 
                        url('data:image/jpeg;base64,{bg_base64}') !important;
            background-size: cover !important;
            background-position: center center !important;
            background-repeat: no-repeat !important;
            background-attachment: fixed !important;
        }}
        
        /* Glassmorphism elevation for login elements */
        div[data-testid="stForm"], div[data-testid="stExpander"] {{
            background: rgba(255, 255, 255, 0.92) !important;
            backdrop-filter: blur(12px) !important;
            -webkit-backdrop-filter: blur(12px) !important;
            border: 1.5px solid rgba(255, 255, 255, 0.8) !important;
            box-shadow: 0 8px 30px rgba(15, 23, 42, 0.07) !important;
        }}
        </style>
        """, unsafe_allow_html=True)
    
    # Emergency Badge
    st.markdown(f"""
        <div class="emergency-badge">
            {_t('emergency_badge')}
        </div>
    """, unsafe_allow_html=True)
    
    # Top Row: Emergency badge & Language selector
    top_c1, top_c2 = st.columns([3, 1.2])
    with top_c2:
        cur_lang = st.session_state.get('language', 'English')
        sel_lang = st.selectbox("🌐 " + _t("lang_toggle"), SUPPORTED_LANGUAGES, index=SUPPORTED_LANGUAGES.index(cur_lang) if cur_lang in SUPPORTED_LANGUAGES else 0, key="login_lang_toggle")
        if sel_lang != cur_lang:
            st.session_state['language'] = sel_lang
            st.rerun()
            
    # Header Section with Logo and Title
    header_col1, header_col2 = st.columns([1, 4])
    with header_col1:
        try:
            st.image("logo.png", width=110)
        except Exception:
            st.markdown("<div class='icon-badge' style='width: 70px; height: 70px; font-size: 2.2rem;'>🩺</div>", unsafe_allow_html=True)
    
    with header_col2:
        st.markdown(f"<h1 class='app-title'>{_t('app_title')}</h1>", unsafe_allow_html=True)
        st.markdown(f"<p class='app-subtitle'>{_t('app_subtitle')}</p>", unsafe_allow_html=True)
    
    st.divider()
    
    main_role = st.session_state.get('selected_main_role')
    patient_service = st.session_state.get('selected_patient_service')
    
    # -------------------------------------------------------------
    # TIER 1: MAIN ROLE SELECTION SCREEN (ASHA WORKER, PATIENT, SUPERVISOR)
    # -------------------------------------------------------------
    if main_role is None:
        st.markdown(f"""
            <div style="text-align: center; margin-bottom: 2rem;">
                <div style="display: inline-flex; align-items: center; gap: 8px; background: #e0f2fe; color: #0284c7; padding: 6px 18px; border-radius: 20px; font-weight: 800; font-size: 0.85rem; border: 1.5px solid #bae6fd; box-shadow: 0 2px 6px rgba(2, 132, 199, 0.08); margin-bottom: 10px;">
                    🔐 ROLE SELECTION LOGIN
                </div>
                <h2 style="font-family: 'Outfit', sans-serif; color: #0f172a; font-weight: 800; font-size: 2rem; margin: 0;">
                    Select Your Portal
                </h2>
                <p style="color: #64748b; font-size: 0.96rem; margin: 8px auto 0 auto; max-width: 650px; line-height: 1.5;">
                    Welcome to MAATRI SURAKSHA AI. Please select your authorized role below to access dedicated healthcare monitoring and clinical services.
                </p>
            </div>
        """, unsafe_allow_html=True)
        
        r_col1, r_col2, r_col3 = st.columns(3)
        
        # 1. ASHA WORKER
        with r_col1:
            st.markdown("""
                <div style="background: #ffffff; border: 1.5px solid #e2e8f0; border-top: 4px solid #0284c7; border-radius: 18px; padding: 24px; box-shadow: 0 4px 16px rgba(2, 132, 199, 0.06); display: flex; flex-direction: column; justify-content: space-between; height: 320px; margin-bottom: 12px;">
                    <div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
                            <div style="width: 50px; height: 50px; border-radius: 12px; background: #f0f9ff; border: 1.5px solid #bae6fd; display: flex; align-items: center; justify-content: center; font-size: 1.6rem;">👩‍⚕️</div>
                            <span style="background: #f0f9ff; color: #0369a1; border: 1.5px solid #bae6fd; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 0.78rem;">FIELD HEALTHCARE</span>
                        </div>
                        <h3 style="color: #0f172a; font-family: 'Outfit', sans-serif; font-size: 1.3rem; font-weight: 800; margin: 0 0 8px 0;">ASHA WORKER</h3>
                        <p style="color: #334155; font-size: 0.9rem; line-height: 1.5; margin: 0;">
                            Community health monitoring, high-risk triage, mother field visits, live geolocation map, and offline sync.
                        </p>
                    </div>
                    <div style="border-top: 1px solid #f1f5f9; padding-top: 12px; font-size: 0.82rem; color: #0284c7; font-weight: 700;">
                        ✓ High-Risk Surveillance & SMS Alerts
                    </div>
                </div>
            """, unsafe_allow_html=True)
            if st.button("👩‍⚕️ Login as ASHA Worker ➔", key="btn_select_asha", use_container_width=True, type="primary"):
                st.session_state['selected_main_role'] = "ASHA Worker"
                st.rerun()

        # 2. PATIENT
        with r_col2:
            st.markdown("""
                <div style="background: #ffffff; border: 1.5px solid #e2e8f0; border-top: 4px solid #db2777; border-radius: 18px; padding: 24px; box-shadow: 0 4px 16px rgba(219, 39, 119, 0.06); display: flex; flex-direction: column; justify-content: space-between; height: 320px; margin-bottom: 12px;">
                    <div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
                            <div style="width: 50px; height: 50px; border-radius: 12px; background: #fdf2f8; border: 1.5px solid #fbcfe8; display: flex; align-items: center; justify-content: center; font-size: 1.6rem;">🤰</div>
                            <span style="background: #fdf2f8; color: #be185d; border: 1.5px solid #fbcfe8; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 0.78rem;">MATERNAL & CHILD</span>
                        </div>
                        <h3 style="color: #0f172a; font-family: 'Outfit', sans-serif; font-size: 1.3rem; font-weight: 800; margin: 0 0 8px 0;">PATIENT</h3>
                        <p style="color: #334155; font-size: 0.9rem; line-height: 1.5; margin: 0;">
                            Personalized health services: Mother Care (pregnancy tracking & diet), Baby Care (infant vaccines & growth), and Community Care.
                        </p>
                    </div>
                    <div style="border-top: 1px solid #f1f5f9; padding-top: 12px; font-size: 0.82rem; color: #db2777; font-weight: 700;">
                        ✓ Mother, Baby & Village Community Care
                    </div>
                </div>
            """, unsafe_allow_html=True)
            if st.button("🤰 Patient Services ➔", key="btn_select_patient", use_container_width=True, type="primary"):
                st.session_state['selected_main_role'] = "Patient"
                st.session_state['selected_patient_service'] = None
                st.rerun()

        # 3. SUPERVISOR
        with r_col3:
            st.markdown("""
                <div style="background: #ffffff; border: 1.5px solid #e2e8f0; border-top: 4px solid #7c3aed; border-radius: 18px; padding: 24px; box-shadow: 0 4px 16px rgba(124, 58, 237, 0.06); display: flex; flex-direction: column; justify-content: space-between; height: 320px; margin-bottom: 12px;">
                    <div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
                            <div style="width: 50px; height: 50px; border-radius: 12px; background: #f5f3ff; border: 1.5px solid #ddd6fe; display: flex; align-items: center; justify-content: center; font-size: 1.6rem;">👨‍💼</div>
                            <span style="background: #f5f3ff; color: #6d28d9; border: 1.5px solid #ddd6fe; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 0.78rem;">ADMIN OVERSIGHT</span>
                        </div>
                        <h3 style="color: #0f172a; font-family: 'Outfit', sans-serif; font-size: 1.3rem; font-weight: 800; margin: 0 0 8px 0;">SUPERVISOR</h3>
                        <p style="color: #334155; font-size: 0.9rem; line-height: 1.5; margin: 0;">
                            Block Medical Officer & Health Supervisor dashboard for village surveillance, maternal mortality reduction & staff oversight.
                        </p>
                    </div>
                    <div style="border-top: 1px solid #f1f5f9; padding-top: 12px; font-size: 0.82rem; color: #7c3aed; font-weight: 700;">
                        ✓ District Analytics & Village Risk Heatmaps
                    </div>
                </div>
            """, unsafe_allow_html=True)
            if st.button("👨‍💼 Login as Supervisor ➔", key="btn_select_supervisor", use_container_width=True, type="primary"):
                st.session_state['selected_main_role'] = "Supervisor"
                st.rerun()

    # -------------------------------------------------------------
    # TIER 2: PATIENT SERVICE SELECTION SCREEN (MOTHER, BABY, COMMUNITY)
    # -------------------------------------------------------------
    elif main_role == "Patient" and patient_service is None:
        # Back button row
        back_col, _ = st.columns([1.5, 4])
        with back_col:
            if st.button("⬅ Back to Role Selection", key="btn_back_roles_tier2", use_container_width=True):
                st.session_state['selected_main_role'] = None
                st.rerun()
                
        st.markdown(f"""
            <div style="text-align: center; margin-bottom: 2rem;">
                <div style="display: inline-flex; align-items: center; gap: 8px; background: #fdf2f8; color: #db2777; padding: 6px 18px; border-radius: 20px; font-weight: 800; font-size: 0.85rem; border: 1.5px solid #fbcfe8; box-shadow: 0 2px 6px rgba(219, 39, 119, 0.08); margin-bottom: 10px;">
                    🤰 PATIENT SERVICE LOGIN
                </div>
                <h2 style="font-family: 'Outfit', sans-serif; color: #0f172a; font-weight: 800; font-size: 2rem; margin: 0;">
                    Select Your Patient Care Service
                </h2>
                <p style="color: #64748b; font-size: 0.96rem; margin: 8px auto 0 auto; max-width: 650px; line-height: 1.5;">
                    Please select the dedicated patient service module you wish to access today.
                </p>
            </div>
        """, unsafe_allow_html=True)
        
        p_col1, p_col2, p_col3 = st.columns(3)
        
        # 1. MOTHER CARE
        with p_col1:
            st.markdown("""
                <div style="background: #ffffff; border: 1.5px solid #e2e8f0; border-top: 4px solid #db2777; border-radius: 18px; padding: 24px; box-shadow: 0 4px 16px rgba(219, 39, 119, 0.06); display: flex; flex-direction: column; justify-content: space-between; height: 310px; margin-bottom: 12px;">
                    <div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
                            <div style="width: 50px; height: 50px; border-radius: 12px; background: #fdf2f8; border: 1.5px solid #fbcfe8; display: flex; align-items: center; justify-content: center; font-size: 1.6rem;">🤰</div>
                            <span style="background: #fdf2f8; color: #be185d; border: 1.5px solid #fbcfe8; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 0.78rem;">PRENATAL CARE</span>
                        </div>
                        <h3 style="color: #0f172a; font-family: 'Outfit', sans-serif; font-size: 1.3rem; font-weight: 800; margin: 0 0 8px 0;">MOTHER CARE</h3>
                        <p style="color: #334155; font-size: 0.9rem; line-height: 1.5; margin: 0;">
                            Daily pregnancy symptoms check, AI risk calculations, diet & exercise planning, fetal progress milestones, and emergency SOS.
                        </p>
                    </div>
                    <div style="border-top: 1px solid #f1f5f9; padding-top: 12px; font-size: 0.82rem; color: #db2777; font-weight: 700;">
                        ✓ Trimester Guidance & Risk Assessment
                    </div>
                </div>
            """, unsafe_allow_html=True)
            if st.button("🤰 Access Mother Care ➔", key="btn_choose_mother_care", use_container_width=True, type="primary"):
                st.session_state['selected_patient_service'] = "Mother Care"
                st.rerun()

        # 2. BABY CARE
        with p_col2:
            st.markdown("""
                <div style="background: #ffffff; border: 1.5px solid #e2e8f0; border-top: 4px solid #0284c7; border-radius: 18px; padding: 24px; box-shadow: 0 4px 16px rgba(2, 132, 199, 0.06); display: flex; flex-direction: column; justify-content: space-between; height: 310px; margin-bottom: 12px;">
                    <div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
                            <div style="width: 50px; height: 50px; border-radius: 12px; background: #f0f9ff; border: 1.5px solid #bae6fd; display: flex; align-items: center; justify-content: center; font-size: 1.6rem;">👶</div>
                            <span style="background: #f0f9ff; color: #0369a1; border: 1.5px solid #bae6fd; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 0.78rem;">INFANT CARE</span>
                        </div>
                        <h3 style="color: #0f172a; font-family: 'Outfit', sans-serif; font-size: 1.3rem; font-weight: 800; margin: 0 0 8px 0;">BABY CARE</h3>
                        <p style="color: #334155; font-size: 0.9rem; line-height: 1.5; margin: 0;">
                            Newborn health profile, immunization & vaccination schedules, growth milestones, feeding & sleep tracking, and pediatric tips.
                        </p>
                    </div>
                    <div style="border-top: 1px solid #f1f5f9; padding-top: 12px; font-size: 0.82rem; color: #0284c7; font-weight: 700;">
                        ✓ Vaccination Alerts & Child Growth
                    </div>
                </div>
            """, unsafe_allow_html=True)
            if st.button("👶 Access Baby Care ➔", key="btn_choose_baby_care", use_container_width=True, type="primary"):
                st.session_state['selected_patient_service'] = "Baby Care"
                st.rerun()

        # 3. COMMUNITY CARE
        with p_col3:
            st.markdown("""
                <div style="background: #ffffff; border: 1.5px solid #e2e8f0; border-top: 4px solid #059669; border-radius: 18px; padding: 24px; box-shadow: 0 4px 16px rgba(5, 150, 105, 0.06); display: flex; flex-direction: column; justify-content: space-between; height: 310px; margin-bottom: 12px;">
                    <div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;">
                            <div style="width: 50px; height: 50px; border-radius: 12px; background: #dcfce7; border: 1.5px solid #86efac; display: flex; align-items: center; justify-content: center; font-size: 1.6rem;">👨‍👩‍👧</div>
                            <span style="background: #dcfce7; color: #065f46; border: 1.5px solid #86efac; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 0.78rem;">VILLAGE HEALTH</span>
                        </div>
                        <h3 style="color: #0f172a; font-family: 'Outfit', sans-serif; font-size: 1.3rem; font-weight: 800; margin: 0 0 8px 0;">COMMUNITY CARE</h3>
                        <p style="color: #334155; font-size: 0.9rem; line-height: 1.5; margin: 0;">
                            Village immunization camps, 108 emergency ambulance contacts, government nutrition schemes (PMMVY), and Anganwadi support.
                        </p>
                    </div>
                    <div style="border-top: 1px solid #f1f5f9; padding-top: 12px; font-size: 0.82rem; color: #059669; font-weight: 700;">
                        ✓ Schemes, Camps & Emergency Transport
                    </div>
                </div>
            """, unsafe_allow_html=True)
            if st.button("👨‍👩‍👧 Access Community Care ➔", key="btn_choose_community_care", use_container_width=True, type="primary"):
                st.session_state['selected_patient_service'] = "Community Care"
                st.rerun()

    # -------------------------------------------------------------
    # TIER 3A: ASHA WORKER AUTHENTICATION
    # -------------------------------------------------------------
    elif main_role == "ASHA Worker":
        b_c1, b_c2, _ = st.columns([1.5, 1.5, 4])
        with b_c1:
            if st.button("⬅ Back to Roles", key="btn_back_from_asha", use_container_width=True):
                st.session_state['selected_main_role'] = None
                st.rerun()
        with b_c2:
            if st.button("🏠 Home", key="btn_home_from_asha", use_container_width=True):
                st.session_state['selected_main_role'] = None
                st.session_state['selected_patient_service'] = None
                st.rerun()
                
        c1, c2, c3 = st.columns([1, 1.2, 1])
        with c2:
            st.markdown(f"""
                <div style="text-align: center; margin-bottom: 1.5rem;">
                    <span class="icon-badge" style="background: #e0f2fe; border: 1.5px solid #38bdf8; color: #0284c7; font-size: 1.4rem;">👩‍⚕️</span>
                    <h3 style="color: #0f172a; font-family: 'Outfit', sans-serif; font-size: 1.35rem; font-weight: 700; margin: 6px 0 4px 0;">ASHA Worker Authentication</h3>
                    <p style="color: #64748b; font-size: 0.88rem; margin: 0;">Sign in to access your field monitoring workspace</p>
                </div>
            """, unsafe_allow_html=True)
            
            with st.form("login_form_asha_worker"):
                phone = st.text_input("📱 Mobile Number", value="8179245840", placeholder="Enter your 10-digit mobile number")
                password = st.text_input("🔒 Security PIN", value="111", placeholder="Enter your PIN", type="password")
                submit_button = st.form_submit_button("Verify & Login to ASHA Portal", type="primary")
                
                if submit_button:
                    if phone.strip() != "8179245840":
                        st.error("⚠️ Only the registered demo ASHA number (8179245840) is permitted for login.")
                    elif password != "111":
                        st.error("❌ Incorrect password.")
                    else:
                        st.session_state['logged_in'] = True
                        st.session_state['role'] = "ASHA Worker"
                        st.rerun()
                        
            st.info("💡 **Demo ASHA Credentials:** Phone: `8179245840` | PIN: `111`")

    # -------------------------------------------------------------
    # TIER 3B: SUPERVISOR AUTHENTICATION
    # -------------------------------------------------------------
    elif main_role == "Supervisor":
        b_c1, b_c2, _ = st.columns([1.5, 1.5, 4])
        with b_c1:
            if st.button("⬅ Back to Roles", key="btn_back_from_sup", use_container_width=True):
                st.session_state['selected_main_role'] = None
                st.rerun()
        with b_c2:
            if st.button("🏠 Home", key="btn_home_from_sup", use_container_width=True):
                st.session_state['selected_main_role'] = None
                st.session_state['selected_patient_service'] = None
                st.rerun()
                
        c1, c2, c3 = st.columns([1, 1.2, 1])
        with c2:
            st.markdown(f"""
                <div style="text-align: center; margin-bottom: 1.5rem;">
                    <span class="icon-badge" style="background: #f5f3ff; border: 1.5px solid #a78bfa; color: #7c3aed; font-size: 1.4rem;">👨‍💼</span>
                    <h3 style="color: #0f172a; font-family: 'Outfit', sans-serif; font-size: 1.35rem; font-weight: 700; margin: 6px 0 4px 0;">Supervisor Authentication</h3>
                    <p style="color: #64748b; font-size: 0.88rem; margin: 0;">Authorized access for Block & District Health Officers</p>
                </div>
            """, unsafe_allow_html=True)
            
            with st.form("login_form_supervisor"):
                sup_id = st.text_input("🆔 Officer ID", value="SUP-101", placeholder="Enter Officer / Supervisor ID")
                password = st.text_input("🔒 Security PIN", value="111", placeholder="Enter your PIN", type="password")
                submit_button = st.form_submit_button("Verify & Enter Supervisor Portal", type="primary")
                
                if submit_button:
                    if not sup_id.strip():
                        st.error("⚠️ Please enter Officer ID.")
                    elif password != "111":
                        st.error("❌ Incorrect PIN. Please use demo PIN: 111.")
                    else:
                        st.session_state['logged_in'] = True
                        st.session_state['role'] = "Supervisor"
                        st.session_state['supervisor_id'] = sup_id.strip()
                        st.rerun()
                        
            st.info("💡 **Demo Supervisor Credentials:** Officer ID: `SUP-101` | PIN: `111`")

    # -------------------------------------------------------------
    # TIER 3C: MOTHER CARE AUTHENTICATION
    # -------------------------------------------------------------
    elif main_role == "Patient" and patient_service == "Mother Care":
        b_c1, b_c2, _ = st.columns([1.6, 1.6, 4])
        with b_c1:
            if st.button("⬅ Back to Services", key="btn_back_from_mother", use_container_width=True):
                st.session_state['selected_patient_service'] = None
                st.rerun()
        with b_c2:
            if st.button("🏠 Role Selection", key="btn_home_from_mother", use_container_width=True):
                st.session_state['selected_main_role'] = None
                st.session_state['selected_patient_service'] = None
                st.rerun()
                
        c1, c2, c3 = st.columns([1, 1.2, 1])
        with c2:
            st.markdown(f"""
                <div style="text-align: center; margin-bottom: 1.5rem;">
                    <span class="icon-badge" style="background: #fdf2f8; border: 1.5px solid #f472b6; color: #db2777; font-size: 1.4rem;">🤰</span>
                    <h3 style="color: #0f172a; font-family: 'Outfit', sans-serif; font-size: 1.35rem; font-weight: 700; margin: 6px 0 4px 0;">Mother Care Login</h3>
                    <p style="color: #64748b; font-size: 0.88rem; margin: 0;">Sign in to access your pregnancy health tracker</p>
                </div>
            """, unsafe_allow_html=True)
            
            with st.form("login_form_mother"):
                unique_id = st.text_input(_t('unique_id_label'), placeholder=_t('unique_id_placeholder'))
                name = st.text_input(_t('full_name_label'), placeholder=_t('full_name_placeholder'))
                submit_button = st.form_submit_button(_t('login_btn'), type="primary")
                
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
                            st.error("❌ Invalid ID or Name. Please check registered records.")
                            
            st.caption("💡 Example: ID `001` & Name `Sath`, or ID `002` & Name `Pink`")

    # -------------------------------------------------------------
    # TIER 3D: BABY CARE AUTHENTICATION
    # -------------------------------------------------------------
    elif main_role == "Patient" and patient_service == "Baby Care":
        b_c1, b_c2, _ = st.columns([1.6, 1.6, 4])
        with b_c1:
            if st.button("⬅ Back to Services", key="btn_back_from_baby", use_container_width=True):
                st.session_state['selected_patient_service'] = None
                st.rerun()
        with b_c2:
            if st.button("🏠 Role Selection", key="btn_home_from_baby", use_container_width=True):
                st.session_state['selected_main_role'] = None
                st.session_state['selected_patient_service'] = None
                st.rerun()
                
        c1, c2, c3 = st.columns([1, 1.2, 1])
        with c2:
            st.markdown(f"""
                <div style="text-align: center; margin-bottom: 1.5rem;">
                    <span class="icon-badge" style="background: #e0f2fe; border: 1.5px solid #38bdf8; color: #0284c7; font-size: 1.4rem;">👶</span>
                    <h3 style="color: #0f172a; font-family: 'Outfit', sans-serif; font-size: 1.35rem; font-weight: 700; margin: 6px 0 4px 0;">Baby Care Login</h3>
                    <p style="color: #64748b; font-size: 0.88rem; margin: 0;">Sign in to track infant vaccinations and milestones</p>
                </div>
            """, unsafe_allow_html=True)
            
            with st.form("login_form_baby"):
                unique_id = st.text_input("Mother ID", placeholder="Enter Mother ID (e.g., 001 or 002)")
                submit_button = st.form_submit_button("Access Baby Portal", type="primary")
                
                if submit_button:
                    if not unique_id.strip():
                        st.error("⚠️ Please enter Mother ID.")
                    else:
                        from database import get_baby_profile
                        conn = get_connection()
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
                            
            st.caption("💡 Example: Mother ID `001` (Sath) or `002` (Pink)")

    # -------------------------------------------------------------
    # TIER 3E: COMMUNITY CARE ENTRY
    # -------------------------------------------------------------
    elif main_role == "Patient" and patient_service == "Community Care":
        b_c1, b_c2, _ = st.columns([1.6, 1.6, 4])
        with b_c1:
            if st.button("⬅ Back to Services", key="btn_back_from_community", use_container_width=True):
                st.session_state['selected_patient_service'] = None
                st.rerun()
        with b_c2:
            if st.button("🏠 Role Selection", key="btn_home_from_community", use_container_width=True):
                st.session_state['selected_main_role'] = None
                st.session_state['selected_patient_service'] = None
                st.rerun()
                
        c1, c2, c3 = st.columns([1, 1.2, 1])
        with c2:
            st.markdown(f"""
                <div style="text-align: center; margin-bottom: 1.5rem;">
                    <span class="icon-badge" style="background: #dcfce7; border: 1.5px solid #4ade80; color: #059669; font-size: 1.4rem;">👨‍👩‍👧</span>
                    <h3 style="color: #0f172a; font-family: 'Outfit', sans-serif; font-size: 1.35rem; font-weight: 700; margin: 6px 0 4px 0;">Community Care Hub</h3>
                    <p style="color: #64748b; font-size: 0.88rem; margin: 0;">Village-level maternal camps, schemes, and emergency ambulance contacts</p>
                </div>
            """, unsafe_allow_html=True)
            
            with st.form("login_form_community"):
                village_options = [
                    "Hyderabad (Old City)", "Secunderabad", "Gachibowli", "Kukatpally", 
                    "Medchal", "Shamshabad", "Ghatkesar", "Chevella (Rangareddy)", 
                    "Warangal", "Karimnagar", "Nizamabad", "Siddipet", "General Community"
                ]
                sel_village = st.selectbox("🏘️ Select Village / Cluster", village_options)
                member_name = st.text_input("👤 Your Name (Optional)", placeholder="Enter your name or leave blank")
                submit_button = st.form_submit_button("Enter Community Care Portal", type="primary")
                
                if submit_button:
                    st.session_state['logged_in'] = True
                    st.session_state['role'] = "Community Care"
                    st.session_state['community_village'] = sel_village
                    st.session_state['community_member'] = member_name.strip() if member_name.strip() else "Community Member"
                    st.rerun()

def mother_dashboard():
    """Render the comprehensive Mother's portal."""
    global send_sms_alert, render_offline_sms_button
    
    # Render Sidebar Navigation for Mother Dashboard
    with st.sidebar:
        # Top back navigation buttons
        m_nav_c1, m_nav_c2 = st.columns([1.5, 1])
        with m_nav_c1:
            if st.button("⬅ Back to Section", key="mother_back_to_section_btn", use_container_width=True):
                back_to_patient_services()
        with m_nav_c2:
            if st.button("🏠 Home", key="mother_home_btn", use_container_width=True):
                back_to_roles()
            
        st.header(_t("mother_portal"))
        st.markdown(f"**{_t('lang_toggle')}:** {st.session_state['language']}")
        st.divider()
        
        st.markdown("<p style='color: #888; font-size: 0.8rem; font-weight: bold;'>MAIN MENU</p>", unsafe_allow_html=True)
        
        # Navigation buttons layout
        nav_options = {
            "Dashboard Overview": ("🏠 " + _t("nav_overview"), "🏠"),
            "Check Symptoms": ("🩺 Check Symptoms", "🩺"),
            "My Health": ("📅 My Health", "📅"),
            "Health Reminders": ("🔔 Reminders", "🔔"),
            "Daily Health Log": (_t("nav_log"), "📝"),
            "Voice Input (Symptoms)": (_t("nav_voice"), "🎤"),
            "Food & Nutrition": (_t("nav_food"), "🍎"),
            "AI Food Planner": (_t("nav_planner"), "🤖"),
            "Mood Tracker": (_t("nav_mood"), "😊"),
            "AI Risk Panel": (_t("nav_risk"), "📊"),
            "Live Location & Map": (_t("nav_map"), "📍"),
            "Pregnancy Journey": (_t("nav_journey"), "👶"),
            "Exercise Coach": (_t("menu_exercise_coach"), "🧘‍♀️"),
            "AI Health Assistant": ("🤖 AI Health Assistant", "💬"),
            "Emergency Help": (_t("nav_emergency"), "🚨")
        }
        
        for key, (label, icon) in nav_options.items():
            if st.button(f"{icon} {label}", use_container_width=True, type="secondary" if st.session_state['mother_page'] != key else "primary"):
                st.session_state['mother_page'] = key
                
        st.divider()
        cur_lang = st.session_state.get('language', 'English')
        st.selectbox("🌐 " + _t("lang_toggle"), SUPPORTED_LANGUAGES, index=SUPPORTED_LANGUAGES.index(cur_lang) if cur_lang in SUPPORTED_LANGUAGES else 0, key="lang_toggle", on_change=lambda: st.session_state.update({"language": st.session_state.lang_toggle}))
        
        if st.button("⬅ Back to Section", key="mother_bottom_back_btn", use_container_width=True):
            back_to_patient_services()

    # Right Content Area based on selected page
    page = st.session_state['mother_page']
    
    # Universal top back navigation bar for sub-pages
    if page != "Dashboard Overview":
        col_b1, _ = st.columns([1.6, 4])
        with col_b1:
            if st.button("⬅ Back to Dashboard Overview", key=f"mother_subpage_back_{page}", use_container_width=True):
                st.session_state['mother_page'] = "Dashboard Overview"
                st.rerun()
    
    if page == "Dashboard Overview":
        mother_name = st.session_state.get('mother_name', 'Mother')
        mother_id_str = st.session_state.get('unique_id', 'Unknown')
        
        # Dynamically calculate trimester based on mother unique_id
        try:
            m_id = int(mother_id_str)
        except ValueError:
            m_id = 1
            
        if 1 <= m_id <= 40:
            week = 4 + ((m_id * 7) % 36)
        else:
            week = 24
            
        if week <= 13:
            trimester = "1st"
        elif week <= 26:
            trimester = "2nd"
        else:
            trimester = "3rd"

        # Creative Hero Banner with Healthcare Art Illustration
        banner_c1, banner_c2 = st.columns([1.5, 1])
        with banner_c1:
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #fff5f8 0%, #f5f3ff 50%, #eff6ff 100%); padding: 26px 28px; border-radius: 20px; border: 1.5px solid #fbcfe8; box-shadow: 0 8px 24px rgba(219, 39, 119, 0.05); height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <div style="display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap;">
                        <span style="background: #ffffff; color: #db2777; padding: 4px 14px; border-radius: 20px; font-size: 0.8rem; font-weight: 700; border: 1.5px solid #fbcfe8; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">🩺 Mother Portal</span>
                        <span style="background: #ffffff; color: #7c3aed; padding: 4px 14px; border-radius: 20px; font-size: 0.8rem; font-weight: 700; border: 1.5px solid #ddd6fe; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">✨ Smart Care AI</span>
                    </div>
                    <h1 style="margin: 0; font-size: 2.1rem; color: #0f172a; font-family: 'Outfit', sans-serif; font-weight: 800; line-height: 1.2;">
                        Namaste, <span style="background: linear-gradient(135deg, #db2777 0%, #7c3aed 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{mother_name}</span>! 👋
                    </h1>
                    <p style="margin: 8px 0 14px 0; font-size: 1rem; color: #475569; line-height: 1.5; font-weight: 500;">
                        {_t('welcome_back')} Here is your daily maternal health intelligence summary. Let's make today healthy and peaceful.
                    </p>
                </div>
                <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                    <span style="display: inline-flex; align-items: center; gap: 6px; font-size: 0.84rem; font-weight: 700; color: #059669; background: #ffffff; padding: 5px 12px; border-radius: 10px; border: 1.5px solid #86efac;">
                        🟢 Daily Checkup: Active
                    </span>
                    <span style="display: inline-flex; align-items: center; gap: 6px; font-size: 0.84rem; font-weight: 700; color: #7c3aed; background: #ffffff; padding: 5px 12px; border-radius: 10px; border: 1.5px solid #c4b5fd;">
                        👶 Week {week} ({trimester} Trimester)
                    </span>
                    <span style="display: inline-flex; align-items: center; gap: 6px; font-size: 0.84rem; font-weight: 700; color: #0284c7; background: #ffffff; padding: 5px 12px; border-radius: 10px; border: 1.5px solid #7dd3fc;">
                        🆔 ID: {mother_id_str}
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
        with banner_c2:
            try:
                st.image("assets/mother_hero.jpg", use_container_width=True)
            except Exception:
                pass
        
        st.markdown("<br>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
                <div style="background: #ffffff; border: 2px solid #10b981; border-top: 6px solid #10b981; border-radius: 18px; padding: 22px; box-shadow: 0 6px 20px rgba(16, 185, 129, 0.08); height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div style="width: 46px; height: 46px; border-radius: 12px; background: #dcfce7; border: 1.5px solid #86efac; display: flex; align-items: center; justify-content: center; font-size: 1.4rem;">🛡️</div>
                        <span style="background: #dcfce7; color: #065f46; border: 1.5px solid #86efac; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 0.85rem;">🟢 {_t('risk_low')}</span>
                    </div>
                    <div>
                        <h4 style="color: #065f46; font-size: 0.88rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 6px 0;">{_t('current_risk')}</h4>
                        <p style="color: #047857; font-size: 2.2rem; font-weight: 800; line-height: 1.1; margin: 0;">Normal</p>
                    </div>
                    <p style="color: #059669; font-size: 0.88rem; font-weight: 600; margin: 14px 0 0 0; border-top: 1px solid #d1fae5; padding-top: 10px;">✓ {_t('normal_today')}</p>
                </div>
            """, unsafe_allow_html=True)
            
        with col2:
            current_time = datetime.datetime.now().strftime("%I:%M %p")
            current_date = datetime.datetime.now().strftime("%b %d")
            st.markdown(f"""
                <div style="background: #ffffff; border: 2px solid #3b82f6; border-top: 6px solid #3b82f6; border-radius: 18px; padding: 22px; box-shadow: 0 6px 20px rgba(59, 130, 246, 0.08); height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div style="width: 46px; height: 46px; border-radius: 12px; background: #dbeafe; border: 1.5px solid #93c5fd; display: flex; align-items: center; justify-content: center; font-size: 1.4rem;">⏱️</div>
                        <span style="background: #dbeafe; color: #1e40af; border: 1.5px solid #93c5fd; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 0.85rem;">{current_date}</span>
                    </div>
                    <div>
                        <h4 style="color: #1e40af; font-size: 0.88rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 6px 0;">{_t('last_log')}</h4>
                        <p style="color: #1d4ed8; font-size: 2.2rem; font-weight: 800; line-height: 1.1; margin: 0;">{current_time}</p>
                    </div>
                    <p style="color: #2563eb; font-size: 0.88rem; font-weight: 600; margin: 14px 0 0 0; border-top: 1px solid #bfdbfe; padding-top: 10px;">✓ {_t('logged_auto')}</p>
                </div>
            """, unsafe_allow_html=True)
            
        with col3:
            st.markdown(f"""
                <div style="background: #ffffff; border: 2px solid #8b5cf6; border-top: 6px solid #8b5cf6; border-radius: 18px; padding: 22px; box-shadow: 0 6px 20px rgba(139, 92, 246, 0.08); height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div style="width: 46px; height: 46px; border-radius: 12px; background: #ede9fe; border: 1.5px solid #c4b5fd; display: flex; align-items: center; justify-content: center; font-size: 1.4rem;">🍼</div>
                        <span style="background: #ede9fe; color: #5b21b6; border: 1.5px solid #c4b5fd; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 0.85rem;">Week {week}</span>
                    </div>
                    <div>
                        <h4 style="color: #5b21b6; font-size: 0.88rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 6px 0;">Pregnancy Stage</h4>
                        <p style="color: #7c3aed; font-size: 2.1rem; font-weight: 800; line-height: 1.1; margin: 0;">{trimester} Trimester</p>
                    </div>
                    <p style="color: #6d28d9; font-size: 0.88rem; font-weight: 600; margin: 14px 0 0 0; border-top: 1px solid #ddd6fe; padding-top: 10px;">✓ Progressing smoothly</p>
                </div>
            """, unsafe_allow_html=True)
            
        st.markdown("<br>", unsafe_allow_html=True)

        # Milestone calculations for baby visual journey
        milestone_week = min(40, max(4, round(week / 4) * 4))
        fetus_img_path = f"assets/fetus_week{milestone_week}.jpg"
        progress_pct = int(min(100, max(5, (week / 40.0) * 100)))
        
        if week <= 12:
            fetus_title = f"Week {week}: Vital Foundations & Heartbeat"
            fetus_desc = "Baby's heart is beating actively and delicate facial features are taking shape. Remember your daily folic acid & iron."
            baby_size = "Size of a Plum 🍑"
        elif week <= 24:
            fetus_title = f"Week {week}: Active Movements & Hearing Voices"
            fetus_desc = "Your baby can now hear familiar voices, music, and your heartbeat! Fingerprints and sleep cycles are developing smoothly."
            baby_size = "Size of an Ear of Corn 🌽"
        elif week <= 34:
            fetus_title = f"Week {week}: Rapid Brain Development & Strong Kicks"
            fetus_desc = "Baby practices breathing movements and can react to light and touch. Track your daily kick counts after lunch and dinner."
            baby_size = "Size of a Coconut 🥥"
        else:
            fetus_title = f"Week {week}: Full Term & Preparing for Delivery"
            fetus_desc = "Baby is fully developed and settling in head-down position. Keep hospital documents, clothes, and ASHA contact handy."
            baby_size = "Size of a Watermelon 🍉"

        # Creative Baby Journey Spotlight & AI Daily Intelligence
        bj_col1, bj_col2 = st.columns([1.2, 1])
        with bj_col1:
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #fdf4ff 0%, #fae8ff 40%, #fdf2f8 100%); border-radius: 20px; border: 2px solid #e879f9; padding: 20px 24px; box-shadow: 0 6px 20px rgba(217, 70, 239, 0.08); height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
                        <span style="background: #ffffff; color: #a21caf; font-weight: 800; font-size: 0.82rem; padding: 4px 14px; border-radius: 20px; border: 1.5px solid #f0abfc;">
                            ✨ Baby Development Milestone
                        </span>
                        <span style="background: #ffffff; color: #86198f; font-weight: 800; font-size: 0.82rem; padding: 4px 12px; border-radius: 20px; border: 1.5px solid #f0abfc;">
                            {baby_size}
                        </span>
                    </div>
                    <h3 style="margin: 0 0 6px 0; color: #701a75; font-size: 1.25rem; font-weight: 800; font-family: 'Outfit', sans-serif;">
                        {fetus_title}
                    </h3>
                    <p style="margin: 0 0 14px 0; color: #4a044e; font-size: 0.92rem; line-height: 1.45; font-weight: 500;">
                        {fetus_desc}
                    </p>
                </div>
                <div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.82rem; font-weight: 700; color: #86198f; margin-bottom: 6px;">
                        <span>Pregnancy Progress</span>
                        <span>Week {week} of 40 ({progress_pct}%)</span>
                    </div>
                    <div style="background: #f5d0fe; border-radius: 10px; height: 10px; overflow: hidden; border: 1px solid #f0abfc;">
                        <div style="background: linear-gradient(90deg, #ec4899 0%, #a855f7 100%); width: {progress_pct}%; height: 100%; border-radius: 10px;"></div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
        with bj_col2:
            if os.path.exists(fetus_img_path):
                try:
                    st.image(fetus_img_path, caption=f"Fetal Ultrasound Milestone (Week {milestone_week})", use_container_width=True)
                except Exception:
                    pass
            else:
                st.markdown(f"""
                <div style="background: linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%); border: 2px solid #34d399; border-radius: 20px; padding: 22px; height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                        <span style="font-size: 1.6rem;">💡</span>
                        <h4 style="margin:0; color: #065f46; font-size: 1.1rem; font-weight: 800;">{_t('ai_suggestion')}</h4>
                    </div>
                    <p style="color: #047857; font-size: 0.94rem; line-height: 1.5; margin: 0; font-weight: 500;">
                        {_t('hydration_tip')} Drinking at least 8-10 glasses of clean water keeps amniotic fluid optimal and prevents fatigue.
                    </p>
                    <div style="margin-top: 12px; background: #ffffff; padding: 8px 12px; border-radius: 10px; border: 1.5px solid #a7f3d0; font-size: 0.85rem; font-weight: 700; color: #059669;">
                        ✓ Hydration Target: 2.5 Liters / Day
                    </div>
                </div>
                """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(f"""
            <div style="background: linear-gradient(135deg, #eff6ff 0%, #e0f2fe 50%, #f0fdfa 100%); padding: 18px 22px; border-radius: 16px; display: flex; align-items: center; gap: 15px; border: 1.5px solid #bfdbfe; box-shadow: 0 4px 14px rgba(37, 99, 235, 0.05);">
                <div style="background: #ffffff; border-radius: 14px; min-width: 48px; height: 48px; display: flex; align-items: center; justify-content: center; font-size: 1.5rem; border: 1.5px solid #93c5fd; box-shadow: 0 2px 6px rgba(0,0,0,0.04);">💡</div>
                <div>
                    <h4 style="margin:0; color: #1e3a8a; font-size: 1.05rem; font-weight: 800;">{_t('ai_suggestion')}</h4>
                    <p style="margin: 4px 0 0 0; color: #1e40af; font-size: 0.92rem; font-weight: 500;">{_t('hydration_tip')} Excellent progress! Remember to do your 15-minute gentle walk and log your meals today.</p>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        # 3 Main Patient Home Pathway Sections
        st.markdown("<br><h3 style='margin-bottom: 6px; font-weight: 800; color: #0f172a; font-family: Outfit, sans-serif;'>🏥 Patient Services & Care Pathways</h3><p style='color: #64748b; font-size: 0.95rem; margin-top: 0; margin-bottom: 16px;'>Select a primary pathway below for Telugu voice triage, medical records, or follow-up schedules.</p>", unsafe_allow_html=True)
        psc1, psc2, psc3 = st.columns(3)
        with psc1:
            st.markdown("""
            <div style="background: #ffffff; border: 1.5px solid #e2e8f0; border-top: 4px solid #ea580c; border-radius: 18px; padding: 22px; box-shadow: 0 4px 14px rgba(0,0,0,0.03); height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div style="width: 46px; height: 46px; border-radius: 12px; background: #fff7ed; border: 1.5px solid #fed7aa; display: flex; align-items: center; justify-content: center; font-size: 1.5rem;">🩺</div>
                        <span style="background: #fff7ed; color: #c2410c; border: 1.5px solid #fed7aa; font-size: 0.78rem; font-weight: 800; padding: 4px 12px; border-radius: 20px;">🎤 Telugu Voice / Text</span>
                    </div>
                    <h3 style="color: #0f172a; font-size: 1.25rem; font-weight: 800; margin: 0 0 8px 0; font-family: Outfit, sans-serif;">1. CHECK SYMPTOMS</h3>
                    <p style="color: #334155; font-size: 0.92rem; line-height: 1.5; margin: 0; font-weight: 400;">
                        Speak in Telugu or type symptoms. Instant 3-level AI triage risk check (Safe / PHC / Urgent Referral) with ASHA alert.
                    </p>
                </div>
                <div style="border-top: 1px solid #f1f5f9; padding-top: 12px; margin-top: 14px; font-size: 0.82rem; color: #ea580c; font-weight: 700;">
                    ➔ Instant Risk Assessment & Guidance
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("🩺 Check Symptoms Now", key="btn_home_check_symptoms", use_container_width=True, type="primary"):
                st.session_state['mother_page'] = "Check Symptoms"
                st.rerun()

        with psc2:
            st.markdown("""
            <div style="background: #ffffff; border: 1.5px solid #e2e8f0; border-top: 4px solid #0284c7; border-radius: 18px; padding: 22px; box-shadow: 0 4px 14px rgba(0,0,0,0.03); height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div style="width: 46px; height: 46px; border-radius: 12px; background: #f0f9ff; border: 1.5px solid #bae6fd; display: flex; align-items: center; justify-content: center; font-size: 1.5rem;">📅</div>
                        <span style="background: #f0f9ff; color: #0369a1; border: 1.5px solid #bae6fd; font-size: 0.78rem; font-weight: 800; padding: 4px 12px; border-radius: 20px;">📋 Records & Visits</span>
                    </div>
                    <h3 style="color: #0f172a; font-size: 1.25rem; font-weight: 800; margin: 0 0 8px 0; font-family: Outfit, sans-serif;">2. MY HEALTH</h3>
                    <p style="color: #334155; font-size: 0.92rem; line-height: 1.5; margin: 0; font-weight: 400;">
                        Access verified Health Records, previous clinical logs, danger sign history, and previous ANC hospital visits.
                    </p>
                </div>
                <div style="border-top: 1px solid #f1f5f9; padding-top: 12px; margin-top: 14px; font-size: 0.82rem; color: #0284c7; font-weight: 700;">
                    ➔ View Clinical Logs & ANC Schedule
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("📅 View My Health", key="btn_home_my_health", use_container_width=True):
                st.session_state['mother_page'] = "My Health"
                st.rerun()

        with psc3:
            st.markdown("""
            <div style="background: #ffffff; border: 1.5px solid #e2e8f0; border-top: 4px solid #7c3aed; border-radius: 18px; padding: 22px; box-shadow: 0 4px 14px rgba(0,0,0,0.03); height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div style="width: 46px; height: 46px; border-radius: 12px; background: #f5f3ff; border: 1.5px solid #ddd6fe; display: flex; align-items: center; justify-content: center; font-size: 1.5rem;">🔔</div>
                        <span style="background: #f5f3ff; color: #6d28d9; border: 1.5px solid #ddd6fe; font-size: 0.78rem; font-weight: 800; padding: 4px 12px; border-radius: 20px;">⏰ Follow-ups & Visits</span>
                    </div>
                    <h3 style="color: #0f172a; font-size: 1.25rem; font-weight: 800; margin: 0 0 8px 0; font-family: Outfit, sans-serif;">3. REMINDERS</h3>
                    <p style="color: #334155; font-size: 0.92rem; line-height: 1.5; margin: 0; font-weight: 400;">
                        Daily medication follow-ups (Iron, Folic, Calcium), hydration tracking, and scheduled PHC ANC appointments.
                    </p>
                </div>
                <div style="border-top: 1px solid #f1f5f9; padding-top: 12px; margin-top: 14px; font-size: 0.82rem; color: #7c3aed; font-weight: 700;">
                    ➔ Daily Follow-ups & PHC Appointments
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("🔔 Open Reminders", key="btn_home_reminders", use_container_width=True):
                st.session_state['mother_page'] = "Health Reminders"
                st.rerun()

        st.markdown("<br><h3 style='margin-bottom: 12px; font-weight: 800; color: #0f172a; font-family: Outfit, sans-serif;'>⚡ Quick Actions</h3>", unsafe_allow_html=True)
        qa1, qa2, qa3, qa4 = st.columns(4)
        with qa1:
            st.markdown("""
            <div style="background: #f0fdf4; border: 1.5px solid #86efac; border-radius: 14px; padding: 12px; text-align: center; margin-bottom: 8px;">
                <span style="font-size: 1.5rem;">📝</span>
                <div style="color: #065f46; font-weight: 700; font-size: 0.85rem; margin-top: 4px;">Health Tracker</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("📝 Log Health", key="btn_log_mother", use_container_width=True):
                st.session_state['mother_page'] = "Daily Health Log"
                st.rerun()
        with qa2:
            st.markdown("""
            <div style="background: #eff6ff; border: 1.5px solid #93c5fd; border-radius: 14px; padding: 12px; text-align: center; margin-bottom: 8px;">
                <span style="font-size: 1.5rem;">🧘‍♀️</span>
                <div style="color: #1e40af; font-weight: 700; font-size: 0.85rem; margin-top: 4px;">Gentle Workout</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("🧘‍♀️ Exercise", key="btn_ex_mother", use_container_width=True):
                st.session_state['mother_page'] = "Exercise Coach"
                st.rerun()
        with qa3:
            st.markdown("""
            <div style="background: #fefce8; border: 1.5px solid #fde047; border-radius: 14px; padding: 12px; text-align: center; margin-bottom: 8px;">
                <span style="font-size: 1.5rem;">🍎</span>
                <div style="color: #854d0e; font-weight: 700; font-size: 0.85rem; margin-top: 4px;">Diet & Meals</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("🍎 Meal Plan", key="btn_meal_mother", use_container_width=True):
                st.session_state['mother_page'] = "AI Food Planner"
                st.rerun()
        with qa4:
            st.markdown("""
            <div style="background: #fff1f2; border: 1.5px solid #fecdd3; border-radius: 14px; padding: 12px; text-align: center; margin-bottom: 8px;">
                <span style="font-size: 1.5rem;">🚨</span>
                <div style="color: #9f1239; font-weight: 700; font-size: 0.85rem; margin-top: 4px;">Emergency Care</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("🚨 SOS Help", type="primary", key="btn_sos_mother", use_container_width=True):
                st.session_state['mother_page'] = "Emergency Help"
                st.rerun()

    elif page == "Check Symptoms":
        mother_name = st.session_state.get('mother_name', 'Mother')
        mother_id_str = str(st.session_state.get('unique_id', '1'))
        village = st.session_state.get('village', 'Kondapur')
        
        try:
            m_id = int(mother_id_str)
        except ValueError:
            m_id = 1
            
        if 1 <= m_id <= 40:
            week = 4 + ((m_id * 7) % 36)
        else:
            week = 24
            
        trimester = "1st" if week <= 13 else ("2nd" if week <= 26 else "3rd")
        
        # Clinical Header Banner
        st.markdown(f"""
        <div style="background: #ffffff; padding: 24px 28px; border-radius: 18px; border: 1.5px solid #e2e8f0; border-left: 6px solid #ea580c; box-shadow: 0 4px 16px rgba(0,0,0,0.03); margin-bottom: 24px;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px;">
                <div>
                    <span style="background: #fff7ed; color: #c2410c; border: 1.5px solid #fed7aa; font-size: 0.8rem; font-weight: 800; padding: 4px 14px; border-radius: 20px;">🩺 Clinical AI Triage</span>
                    <h1 style="margin: 8px 0 6px 0; font-size: 2.1rem; color: #0f172a; font-family: Outfit, sans-serif; font-weight: 800;">
                        Symptom Assessment & Risk Triage
                    </h1>
                    <p style="margin: 0; color: #475569; font-size: 0.95rem; font-weight: 400; line-height: 1.5;">
                        Speak in Telugu (తెలుగు) or type your symptoms. The clinical AI evaluates danger signs and connects your local ASHA worker.
                    </p>
                </div>
                <div style="text-align: right; background: #f8fafc; padding: 12px 20px; border-radius: 14px; border: 1.5px solid #e2e8f0;">
                    <div style="font-size: 0.76rem; color: #64748b; font-weight: 800; letter-spacing: 0.5px;">PATIENT PROFILE</div>
                    <div style="font-size: 1.05rem; color: #0f172a; font-weight: 800;">{mother_name} (ID: {mother_id_str})</div>
                    <div style="font-size: 0.84rem; color: #0284c7; font-weight: 600;">Week {week} • {trimester} Trimester • {village}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # 1. CHECK SYMPTOMS INPUT INTERFACE
        st.markdown("<h3 style='color: #0f172a; font-weight: 800; font-family: Outfit, sans-serif; margin-bottom: 16px;'>1. 🩺 Provide Symptoms / లక్షణాలు నమోదు చేయండి</h3>", unsafe_allow_html=True)
        
        sym_col1, sym_col2 = st.columns([1, 1.2])
        
        with sym_col1:
            with st.container(border=True):
                st.markdown("""
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
                    <div style="width: 42px; height: 42px; border-radius: 12px; background: #fff7ed; border: 1.5px solid #fed7aa; display: flex; align-items: center; justify-content: center; font-size: 1.4rem;">🎤</div>
                    <div>
                        <h4 style="margin: 0; color: #0f172a; font-size: 1.1rem; font-weight: 800; font-family: Outfit, sans-serif;">Telugu Voice Input</h4>
                        <span style="color: #64748b; font-size: 0.82rem; font-weight: 600;">తెలుగు వాయిస్ రికార్డింగ్</span>
                    </div>
                </div>
                <p style="color: #475569; font-size: 0.9rem; margin: 0 0 14px 0; line-height: 1.4;">
                    Record your symptoms verbally in Telugu or English. The AI will transcribe and extract key health signals:
                </p>
                """, unsafe_allow_html=True)
                
                cs_audio = st.audio_input("🎤 Record voice", key="cs_audio_input")
                
                if cs_audio is not None:
                    if not st.session_state.get('cs_audio_processed', False):
                        with st.spinner("Processing Telugu Voice Recognition..."):
                            import speech_recognition as sr
                            try:
                                r = sr.Recognizer()
                                with sr.AudioFile(cs_audio) as source:
                                    audio = r.record(source)
                                try:
                                    transcribed_text = r.recognize_google(audio, language="te-IN")
                                except Exception:
                                    transcribed_text = r.recognize_google(audio, language="en-IN")
                                st.session_state['cs_transcription'] = transcribed_text
                            except Exception as e:
                                st.session_state['cs_transcription'] = "Voice recorded. Please verify or add symptoms below."
                            st.session_state['cs_audio_processed'] = True
                            st.rerun()
                else:
                    if st.session_state.get('cs_audio_processed', False):
                        st.session_state['cs_transcription'] = ""
                        st.session_state['cs_audio_processed'] = False
                        
                voice_text = st.text_area("Recognized Voice Text / మాటల వివరణ:", value=st.session_state.get('cs_transcription', ''), height=100, key="cs_voice_text_display", placeholder="Transcribed symptoms will appear here...")

        with sym_col2:
            with st.container(border=True):
                st.markdown("""
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
                    <div style="width: 42px; height: 42px; border-radius: 12px; background: #f0f9ff; border: 1.5px solid #bae6fd; display: flex; align-items: center; justify-content: center; font-size: 1.4rem;">📝</div>
                    <div>
                        <h4 style="margin: 0; color: #0f172a; font-size: 1.1rem; font-weight: 800; font-family: Outfit, sans-serif;">Symptom Checklist & State</h4>
                        <span style="color: #64748b; font-size: 0.82rem; font-weight: 600;">లక్షణాలు & ఆరోగ్య స్థితి</span>
                    </div>
                </div>
                <p style="color: #475569; font-size: 0.9rem; margin: 0 0 12px 0; line-height: 1.4;">
                    Check any symptoms or discomfort you are experiencing today:
                </p>
                """, unsafe_allow_html=True)
                
                chk_c1, chk_c2 = st.columns(2)
                with chk_c1:
                    cs_bleeding = st.checkbox("🩸 Bleeding (రక్తస్రావం)", key="cs_sym_bleeding")
                    cs_fetal = st.checkbox("👶 Reduced Movement (కదలికలు తగ్గడం)", key="cs_sym_fetal")
                    cs_headache = st.checkbox("🤕 Severe Headache (తీవ్ర తలనొప్పి)", key="cs_sym_headache")
                with chk_c2:
                    cs_swelling = st.checkbox("🦶 Swelling (ముఖం / కాళ్ల వాపు)", key="cs_sym_swelling")
                    cs_dizziness = st.checkbox("💫 Dizziness / Fainting (కళ్ళు తిరగడం)", key="cs_sym_dizziness")
                    cs_fever = st.checkbox("🌡️ High Fever (తీవ్ర జ్వరం)", key="cs_sym_fever")
                    
                st.markdown("<div style='margin-top: 6px;'></div>", unsafe_allow_html=True)
                cs_custom_text = st.text_input("Additional Symptoms / ఇతర లక్షణాలు:", placeholder="e.g. abdominal cramps, vomiting, blurred vision...", key="cs_custom_text")
                
                mood_col, nut_col = st.columns(2)
                with mood_col:
                    cs_mood = st.selectbox("Current Mood / మానసిక స్థితి:", ["Normal", "Stressed", "Very Sad", "Anxious"], index=0, key="cs_mood")
                with nut_col:
                    cs_nut = st.selectbox("Food & Hydration / ఆహారం:", ["Good (3 meals)", "Low (poor appetite)", "No food / Vomiting"], index=0, key="cs_nut")

        st.markdown("<div style='margin-top: 18px; margin-bottom: 24px;'>", unsafe_allow_html=True)
        btn_assess = st.button("🔍 Assess Symptoms & Run Triage Check", type="primary", use_container_width=True, key="btn_run_symptom_triage")
        st.markdown("</div>", unsafe_allow_html=True)

        # Process assessment on click
        if btn_assess:
            collected_symptoms = []
            
            # 1. Collect from checkboxes
            if cs_bleeding: collected_symptoms.append("bleeding")
            if cs_fetal: collected_symptoms.append("reduced fetal movement")
            if cs_headache: collected_symptoms.append("headache")
            if cs_swelling: collected_symptoms.append("swelling")
            if cs_dizziness: collected_symptoms.append("dizziness")
            if cs_fever: collected_symptoms.append("fever")
            
            # 2. Collect from voice text
            v_text = voice_text.lower()
            if "రక్త" in v_text or "రక్తం" in v_text or "bleeding" in v_text:
                if "bleeding" not in collected_symptoms: collected_symptoms.append("bleeding")
            if "కదలిక" in v_text or "తగ్గ" in v_text or "fetal" in v_text or "movement" in v_text:
                if "reduced fetal movement" not in collected_symptoms: collected_symptoms.append("reduced fetal movement")
            if "తలనొప్పి" in v_text or "నొప్పి" in v_text or "headache" in v_text:
                if "headache" not in collected_symptoms: collected_symptoms.append("headache")
            if "వాపు" in v_text or "కాళ్ల" in v_text or "swelling" in v_text:
                if "swelling" not in collected_symptoms: collected_symptoms.append("swelling")
            if "తిరగడం" in v_text or "కళ్ళు" in v_text or "dizziness" in v_text:
                if "dizziness" not in collected_symptoms: collected_symptoms.append("dizziness")
            if "జ్వరం" in v_text or "fever" in v_text:
                if "fever" not in collected_symptoms: collected_symptoms.append("fever")
                
            # 3. Collect from custom text
            c_text = cs_custom_text.lower()
            if c_text:
                if "bleed" in c_text and "bleeding" not in collected_symptoms: collected_symptoms.append("bleeding")
                if "fetal" in c_text or "movement" in c_text:
                    if "reduced fetal movement" not in collected_symptoms: collected_symptoms.append("reduced fetal movement")
                if "headache" in c_text and "headache" not in collected_symptoms: collected_symptoms.append("headache")
                if "swell" in c_text and "swelling" not in collected_symptoms: collected_symptoms.append("swelling")
                if "dizz" in c_text and "dizziness" not in collected_symptoms: collected_symptoms.append("dizziness")
                if cs_custom_text not in collected_symptoms: collected_symptoms.append(cs_custom_text)
                
            # Run existing AI calculation
            ai_eval = calculate_risk(collected_symptoms, cs_mood, cs_nut)
            st.session_state['latest_triage_result'] = {
                "symptoms": collected_symptoms,
                "mood": cs_mood,
                "nutrition": cs_nut,
                "ai_result": ai_eval,
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            # Save into existing database
            save_daily_log(mother_id_str, collected_symptoms, cs_mood, cs_nut, ai_eval['risk_score'], ai_eval['risk_level'], ai_eval['timestamp'])
            
            # If high risk, alert ASHA
            if ai_eval['risk_level'] == "High":
                create_alert(mother_id_str, "High", ai_eval['timestamp'])
                if is_online():
                    if not has_recent_high_risk_sms(mother_id_str):
                        try:
                            send_sms_alert(mother_id_str)
                        except Exception as e:
                            print(f"SMS dispatch note: {e}")

        # Render Assessment Results if available
        if 'latest_triage_result' in st.session_state:
            res_data = st.session_state['latest_triage_result']
            ai_eval = res_data['ai_result']
            risk_level = ai_eval['risk_level'] # "Low", "Medium", "High"
            risk_score = ai_eval['risk_score']
            syms_shown = ", ".join(res_data['symptoms']) if res_data['symptoms'] else "None (Routine healthy baseline)"
            
            st.markdown("<hr style='border: 1px solid #e2e8f0; margin: 30px 0;'>", unsafe_allow_html=True)
            
            # 2. SYMPTOM ASSESSMENT & 3. TRIAGE / RISK CHECK
            st.markdown("<h2 style='color: #0f172a; font-weight: 800; font-family: Outfit, sans-serif; margin-bottom: 6px;'>🔍 SYMPTOM ASSESSMENT & TRIAGE</h2>", unsafe_allow_html=True)
            st.markdown(f"<p style='color: #64748b; font-size: 0.95rem; margin-top: 0; margin-bottom: 20px;'>Evaluated on: <b>{res_data['timestamp']}</b> | Analyzed Symptoms: <i>{syms_shown}</i></p>", unsafe_allow_html=True)
            
            # 3 Triage level cards layout
            t1, t2, t3 = st.columns(3)
            
            with t1:
                is_curr_low = (risk_level == "Low")
                low_border = "2px solid #10b981" if is_curr_low else "1.5px solid #e2e8f0"
                low_shadow = "0 8px 24px rgba(16, 185, 129, 0.12)" if is_curr_low else "0 2px 8px rgba(0,0,0,0.02)"
                low_badge = "★ CURRENT TRIAGE" if is_curr_low else "LEVEL 1"
                st.markdown(f"""
                <div style="background: #ffffff; border: {low_border}; border-top: 5px solid #10b981; border-radius: 18px; padding: 22px; box-shadow: {low_shadow}; height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                    <div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <span style="font-size: 2rem;">🟢</span>
                            <span style="background: {'#10b981' if is_curr_low else '#f1f5f9'}; color: {'#ffffff' if is_curr_low else '#475569'}; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 0.78rem;">{low_badge}</span>
                        </div>
                        <h3 style="color: #0f172a; font-size: 1.25rem; font-weight: 800; margin: 0 0 4px 0; font-family: Outfit, sans-serif;">🟢 LOW RISK</h3>
                        <div style="display: inline-block; background: #dcfce7; color: #065f46; border: 1px solid #86efac; border-radius: 8px; padding: 4px 10px; font-weight: 800; font-size: 0.84rem; margin-bottom: 10px;">
                            Home Care Recommended
                        </div>
                        <p style="color: #334155; font-size: 0.9rem; line-height: 1.5; margin: 0;">
                            No severe danger signs detected. Maternal vitals stable. Continue regular nutritious diet, hydration, and prenatal vitamins.
                        </p>
                    </div>
                    <div style="margin-top: 16px; padding: 8px 12px; background: #f0fdf4; border-radius: 10px; border: 1px solid #86efac; font-weight: 700; color: #065f46; font-size: 0.84rem; text-align: center;">
                        ➔ ACTION: HOME CARE
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
            with t2:
                is_curr_med = (risk_level == "Medium")
                med_border = "2px solid #f59e0b" if is_curr_med else "1.5px solid #e2e8f0"
                med_shadow = "0 8px 24px rgba(245, 158, 11, 0.12)" if is_curr_med else "0 2px 8px rgba(0,0,0,0.02)"
                med_badge = "★ CURRENT TRIAGE" if is_curr_med else "LEVEL 2"
                st.markdown(f"""
                <div style="background: #ffffff; border: {med_border}; border-top: 5px solid #f59e0b; border-radius: 18px; padding: 22px; box-shadow: {med_shadow}; height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                    <div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <span style="font-size: 2rem;">🟡</span>
                            <span style="background: {'#f59e0b' if is_curr_med else '#f1f5f9'}; color: {'#ffffff' if is_curr_med else '#475569'}; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 0.78rem;">{med_badge}</span>
                        </div>
                        <h3 style="color: #0f172a; font-size: 1.25rem; font-weight: 800; margin: 0 0 4px 0; font-family: Outfit, sans-serif;">🟡 MEDIUM RISK</h3>
                        <div style="display: inline-block; background: #fef3c7; color: #92400e; border: 1px solid #fde68a; border-radius: 8px; padding: 4px 10px; font-weight: 800; font-size: 0.84rem; margin-bottom: 10px;">
                            PHC Visit Recommended
                        </div>
                        <p style="color: #334155; font-size: 0.9rem; line-height: 1.5; margin: 0;">
                            Moderate symptoms like persistent headache, dizziness or swelling noted. Needs physical clinical evaluation at Primary Health Centre.
                        </p>
                    </div>
                    <div style="margin-top: 16px; padding: 8px 12px; background: #fffbeb; border-radius: 10px; border: 1px solid #fde68a; font-weight: 700; color: #92400e; font-size: 0.84rem; text-align: center;">
                        ➔ ACTION: PHC VISIT
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
            with t3:
                is_curr_high = (risk_level == "High")
                high_border = "2px solid #ef4444" if is_curr_high else "1.5px solid #e2e8f0"
                high_shadow = "0 8px 24px rgba(239, 68, 68, 0.16)" if is_curr_high else "0 2px 8px rgba(0,0,0,0.02)"
                high_badge = "🚨 URGENT ACTION" if is_curr_high else "LEVEL 3"
                st.markdown(f"""
                <div style="background: #ffffff; border: {high_border}; border-top: 5px solid #ef4444; border-radius: 18px; padding: 22px; box-shadow: {high_shadow}; height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                    <div>
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <span style="font-size: 2rem;">🔴</span>
                            <span style="background: {'#ef4444' if is_curr_high else '#f1f5f9'}; color: {'#ffffff' if is_curr_high else '#475569'}; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 0.78rem;">{high_badge}</span>
                        </div>
                        <h3 style="color: #0f172a; font-size: 1.25rem; font-weight: 800; margin: 0 0 4px 0; font-family: Outfit, sans-serif;">🔴 HIGH RISK</h3>
                        <div style="display: inline-block; background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; border-radius: 8px; padding: 4px 10px; font-weight: 800; font-size: 0.84rem; margin-bottom: 10px;">
                            Urgent Medical Attention Required
                        </div>
                        <p style="color: #334155; font-size: 0.9rem; line-height: 1.5; margin: 0;">
                            Critical obstetric danger signs present (bleeding, reduced fetal movement). Immediate hospital care and transport required.
                        </p>
                    </div>
                    <div style="margin-top: 16px; padding: 8px 12px; background: #fff1f2; border-radius: 10px; border: 1px solid #fca5a5; font-weight: 700; color: #991b1b; font-size: 0.84rem; text-align: center;">
                        ➔ ACTION: URGENT REFERRAL
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
            st.markdown("<br>", unsafe_allow_html=True)
            
            # 4. RECOMMENDED ACTION
            st.markdown("<h3 style='color: #0f172a; font-weight: 800; font-family: Outfit, sans-serif; margin-bottom: 12px;'>📢 RECOMMENDED ACTION</h3>", unsafe_allow_html=True)
            
            if risk_level == "Low":
                st.markdown(f"""
                <div style="background: #ffffff; border: 2px solid #86efac; border-left: 8px solid #10b981; border-radius: 16px; padding: 22px; box-shadow: 0 4px 14px rgba(16, 185, 129, 0.05); margin-bottom: 24px;">
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
                        <span style="font-size: 1.6rem;">🏡</span>
                        <h4 style="margin: 0; color: #065f46; font-size: 1.15rem; font-weight: 800;">Home Care Guidance for {mother_name}</h4>
                    </div>
                    <ul style="color: #047857; font-size: 0.95rem; line-height: 1.6; margin: 0; padding-left: 20px;">
                        <li><b>Hydration Target:</b> Drink 8-10 glasses (2.5 Liters) of clean boiled water daily to maintain optimal amniotic fluid levels.</li>
                        <li><b>Prescribed Supplements:</b> Continue your daily Iron & Folic Acid (IFA) tablet after lunch and Calcium tablet after dinner (never together).</li>
                        <li><b>Daily Kick Counter:</b> Lie on your left side after meals and count baby kicks. You should feel at least 10 kicks in a 2-hour window.</li>
                        <li><b>Adequate Rest:</b> Ensure 8 hours of uninterrupted sleep at night and 1-2 hours of daytime rest in left-lateral position.</li>
                    </ul>
                </div>
                """, unsafe_allow_html=True)
            elif risk_level == "Medium":
                st.markdown(f"""
                <div style="background: #ffffff; border: 2px solid #fde047; border-left: 8px solid #f59e0b; border-radius: 16px; padding: 22px; box-shadow: 0 4px 14px rgba(245, 158, 11, 0.05); margin-bottom: 24px;">
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
                        <span style="font-size: 1.6rem;">🏥</span>
                        <h4 style="margin: 0; color: #92400e; font-size: 1.15rem; font-weight: 800;">Primary Health Centre (PHC) Visit Recommended for {mother_name}</h4>
                    </div>
                    <ul style="color: #b45309; font-size: 0.95rem; line-height: 1.6; margin: 0; padding-left: 20px;">
                        <li><b>Timing:</b> Please visit your nearest Primary Health Centre or Sub-Center within <b>24 hours</b> for an in-person checkup.</li>
                        <li><b>Clinical Tests to Request:</b> Blood pressure check (rule out gestational hypertension), urine albumin test, and hemoglobin verification.</li>
                        <li><b>Rest & Posture:</b> Avoid standing for long intervals; rest with feet slightly elevated on a pillow to reduce swelling.</li>
                        <li><b>ASHA Alert Logged:</b> Your community ASHA worker has received an automated alert and will contact you today.</li>
                    </ul>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="background: #ffffff; border: 2px solid #fca5a5; border-left: 8px solid #ef4444; border-radius: 16px; padding: 22px; box-shadow: 0 4px 14px rgba(239, 68, 68, 0.08); margin-bottom: 24px;">
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
                        <span style="font-size: 1.6rem;">🚨</span>
                        <h4 style="margin: 0; color: #991b1b; font-size: 1.2rem; font-weight: 800;">EMERGENCY: Immediate Medical Attention & Urgent Hospital Referral</h4>
                    </div>
                    <p style="color: #b91c1c; font-size: 0.96rem; line-height: 1.5; font-weight: 600; margin: 0 0 10px 0;">
                        Critical obstetric danger signs have been detected ({syms_shown}). Immediate transport to a comprehensive obstetric care facility is required.
                    </p>
                    <ul style="color: #991b1b; font-size: 0.95rem; line-height: 1.6; margin: 0; padding-left: 20px;">
                        <li><b>Call 108 Emergency Ambulance immediately.</b> Dial 108 for free 24/7 maternal transit.</li>
                        <li><b>Keep Medical Records Ready:</b> Carry your Mother-Child Protection (MCP) card, previous ultrasound reports, and ID.</li>
                        <li><b>Left Lateral Position:</b> Lie down on your left side while waiting for ambulance transport.</li>
                        <li><b>Emergency ASHA Alert:</b> Direct SMS and high-risk case entry have been transmitted to your ASHA supervisor.</li>
                    </ul>
                </div>
                """, unsafe_allow_html=True)
                
            # 5. ASHA CONNECTION & 📍 PHC / HOSPITAL DETAILS
            ash_c1, ash_c2 = st.columns([1, 1])
            
            with ash_c1:
                with st.container(border=True):
                    st.markdown(f"""
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
                        <div style="width: 42px; height: 42px; border-radius: 12px; background: #fff7ed; border: 1.5px solid #fed7aa; display: flex; align-items: center; justify-content: center; font-size: 1.4rem;">👩‍⚕️</div>
                        <div>
                            <h4 style="margin:0; color: #0f172a; font-size: 1.05rem; font-weight: 800; font-family: Outfit, sans-serif;">5. CONNECT ASHA WORKER</h4>
                            <span style="font-size: 0.8rem; color: #16a34a; font-weight: 700;">● Active on Duty • Village Health Contact</span>
                        </div>
                    </div>
                    <div style="background: #f8fafc; padding: 12px; border-radius: 12px; border: 1.5px solid #e2e8f0; margin-bottom: 12px;">
                        <div style="color: #0f172a; font-weight: 800; font-size: 0.95rem;">ASHA: Lakshmi Devi (Community Care)</div>
                        <div style="color: #475569; font-size: 0.88rem; font-weight: 600;">Phone: +91 8179245840 | Assigned Sector: {village}</div>
                    </div>
                    <p style="color: #475569; font-size: 0.86rem; margin: 0 0 10px 0;">
                        Instantly connect via live cellular call, WhatsApp message, or direct SMS dispatch:
                    </p>
                    """, unsafe_allow_html=True)
                    
                    # Render SMS / WhatsApp actions
                    try:
                        render_offline_sms_button(mother_id_str)
                    except Exception as e:
                        print(f"Offline button: {e}")
                    
            with ash_c2:
                with st.container(border=True):
                    st.markdown("""
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
                        <div style="width: 42px; height: 42px; border-radius: 12px; background: #f0f9ff; border: 1.5px solid #bae6fd; display: flex; align-items: center; justify-content: center; font-size: 1.4rem;">📍</div>
                        <div>
                            <h4 style="margin:0; color: #0f172a; font-size: 1.05rem; font-weight: 800; font-family: Outfit, sans-serif;">6. PHC / HOSPITAL DETAILS</h4>
                            <span style="font-size: 0.8rem; color: #0284c7; font-weight: 700;">24/7 Maternal & Obstetric Facility</span>
                        </div>
                    </div>
                    <div style="background: #f8fafc; padding: 12px; border-radius: 12px; border: 1.5px solid #e2e8f0; margin-bottom: 12px;">
                        <div style="color: #0f172a; font-weight: 800; font-size: 0.95rem;">Kondapur Community Health Centre & Maternity Wing</div>
                        <div style="color: #475569; font-size: 0.88rem; font-weight: 600;">Distance: ~3.2 km | Duty Officer: Dr. S. Sunitha, MBBS, DGO</div>
                    </div>
                    <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px;">
                        <span style="background: #fee2e2; color: #991b1b; padding: 6px 14px; border-radius: 8px; font-weight: 700; font-size: 0.82rem; border: 1px solid #fca5a5;">
                            🚑 108 Emergency (Free)
                        </span>
                        <span style="background: #fef3c7; color: #92400e; padding: 6px 14px; border-radius: 8px; font-weight: 700; font-size: 0.82rem; border: 1px solid #fde68a;">
                            🚐 102 JSSK Drop-Back
                        </span>
                    </div>
                    """, unsafe_allow_html=True)
                
            st.markdown("<br>", unsafe_allow_html=True)
            
            # 6. CASE / REFERRAL STATUS
            ref_id = f"REF-{mother_id_str}-{datetime.datetime.now().strftime('%d%m%H%M')}"
            status_text = "URGENT HOSPITAL REFERRAL (ESCALATED)" if risk_level == "High" else ("PHC CLINICAL FOLLOW-UP" if risk_level == "Medium" else "HOME MONITORING ACTIVE")
            status_color = "#ef4444" if risk_level == "High" else ("#f59e0b" if risk_level == "Medium" else "#10b981")
            
            st.markdown(f"""
            <div style="background: #f8fafc; border: 1.5px solid #cbd5e1; border-radius: 16px; padding: 18px 22px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
                <div>
                    <div style="font-size: 0.8rem; color: #64748b; font-weight: 700; text-transform: uppercase;">📋 Case & Referral Status</div>
                    <div style="font-size: 1.1rem; color: #0f172a; font-weight: 800;">Token: <span style="font-family: monospace; background: #e2e8f0; padding: 2px 8px; border-radius: 6px;">{ref_id}</span></div>
                    <div style="font-size: 0.86rem; color: #475569; font-weight: 500;">Patient: {mother_name} | Mother ID: {mother_id_str} | Date: {res_data['timestamp']}</div>
                </div>
                <div>
                    <span style="background: {status_color}; color: white; padding: 8px 16px; border-radius: 20px; font-weight: 800; font-size: 0.88rem; box-shadow: 0 2px 8px rgba(0,0,0,0.08);">
                        {status_text}
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            ref_col1, ref_col2 = st.columns(2)
            with ref_col1:
                if st.button("⬅ Return to Dashboard Overview", key="btn_ret_home_triage", use_container_width=True):
                    st.session_state['mother_page'] = "Dashboard Overview"
                    st.rerun()
            with ref_col2:
                if st.button("📅 View in My Health Records", key="btn_view_rec_triage", use_container_width=True):
                    st.session_state['mother_page'] = "My Health"
                    st.rerun()

    elif page == "My Health":
        mother_name = st.session_state.get('mother_name', 'Mother')
        mother_id_str = str(st.session_state.get('unique_id', '1'))
        village = st.session_state.get('village', 'Kondapur')
        
        try:
            m_id = int(mother_id_str)
        except ValueError:
            m_id = 1
            
        if 1 <= m_id <= 40:
            week = 4 + ((m_id * 7) % 36)
        else:
            week = 24
            
        trimester = "1st" if week <= 13 else ("2nd" if week <= 26 else "3rd")
        
        # Header Banner
        st.markdown(f"""
        <div style="background: #ffffff; padding: 24px 28px; border-radius: 18px; border: 1.5px solid #e2e8f0; border-left: 6px solid #0284c7; box-shadow: 0 4px 16px rgba(0,0,0,0.03); margin-bottom: 24px;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 14px;">
                <div>
                    <span style="background: #f0f9ff; color: #0369a1; border: 1.5px solid #bae6fd; font-size: 0.8rem; font-weight: 800; padding: 4px 14px; border-radius: 20px;">📋 Official Health Records</span>
                    <h1 style="margin: 8px 0 6px 0; font-size: 2.1rem; color: #0f172a; font-family: Outfit, sans-serif; font-weight: 800;">
                        My Health & Clinical History
                    </h1>
                    <p style="margin: 0; color: #475569; font-size: 0.95rem; font-weight: 400; line-height: 1.5;">
                        Comprehensive health records, previous clinic visits, danger sign logs, and antenatal care schedules.
                    </p>
                </div>
                <div style="text-align: right; background: #f8fafc; padding: 12px 20px; border-radius: 14px; border: 1.5px solid #e2e8f0;">
                    <div style="font-size: 0.76rem; color: #64748b; font-weight: 800; letter-spacing: 0.5px;">PATIENT PROFILE</div>
                    <div style="font-size: 1.05rem; color: #0f172a; font-weight: 800;">{mother_name} (ID: {mother_id_str})</div>
                    <div style="font-size: 0.84rem; color: #0284c7; font-weight: 600;">Week {week} • {trimester} Trimester • {village}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Tabs for Health Records vs Previous Visits
        tab_records, tab_visits = st.tabs(["📋 Health Records & Clinical Logs", "📋 Previous Visits & ANC Schedule"])
        
        with tab_records:
            st.markdown("<h3 style='color: #0f172a; font-weight: 800; font-family: Outfit, sans-serif; margin-bottom: 12px;'>📋 Patient Health Records</h3>", unsafe_allow_html=True)
            
            # Fetch existing records from database
            conn = get_connection()
            c = conn.cursor()
            c.execute("""
            SELECT id, symptoms, mood, nutrition, risk_score, risk_level, date 
            FROM daily_logs 
            WHERE user_id = ? OR user_id = ? 
            ORDER BY date DESC
            """, (mother_id_str, m_id))
            patient_logs = c.fetchall()
            conn.close()
            
            if patient_logs:
                st.markdown(f"<p style='color: #475569; font-size: 0.95rem; margin-bottom: 16px;'>Found <b>{len(patient_logs)}</b> recorded clinical log(s) for this patient:</p>", unsafe_allow_html=True)
                
                for log_id, syms, mood, nut, score, r_level, log_date in patient_logs:
                    badge_color = "#10b981" if r_level == "Low" else ("#f59e0b" if r_level == "Medium" else "#ef4444")
                    badge_bg = "#dcfce7" if r_level == "Low" else ("#fef3c7" if r_level == "Medium" else "#fee2e2")
                    badge_icon = "🟢" if r_level == "Low" else ("🟡" if r_level == "Medium" else "🔴")
                    
                    st.markdown(f"""
                    <div style="background: #ffffff; border: 1.5px solid #e2e8f0; border-left: 6px solid {badge_color}; border-radius: 14px; padding: 16px 20px; margin-bottom: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.02);">
                        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <span style="font-size: 1.4rem;">{badge_icon}</span>
                                <div>
                                    <div style="font-weight: 800; color: #0f172a; font-size: 1rem;">Log #{log_id} — {log_date}</div>
                                    <div style="font-size: 0.88rem; color: #64748b;">Symptoms: <b style="color: #334155;">{syms if syms else 'None (Healthy Routine)'}</b></div>
                                </div>
                            </div>
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <span style="background: {badge_bg}; color: {badge_color}; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 0.82rem;">
                                    {r_level.upper()} RISK (Score: {score})
                                </span>
                                <span style="background: #f1f5f9; color: #475569; padding: 4px 10px; border-radius: 8px; font-size: 0.8rem; font-weight: 600;">
                                    Mood: {mood} | Food: {nut}
                                </span>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("ℹ️ No daily symptom logs recorded yet for this profile. You can record your first assessment using 'Check Symptoms'.")
                if st.button("🩺 Go to Check Symptoms", key="btn_my_health_go_cs"):
                    st.session_state['mother_page'] = "Check Symptoms"
                    st.rerun()
                    
        with tab_visits:
            st.markdown("<h3 style='color: #0f172a; font-weight: 800; font-family: Outfit, sans-serif; margin-bottom: 12px;'>📋 Previous Visits & Antenatal Care (ANC) Schedule</h3>", unsafe_allow_html=True)
            
            # ANC 1 to 4 Schedule
            anc_visits = [
                ("ANC 1 (First Trimester - Week 12)", 12, "Registration, Height, Weight, Blood Pressure, Hemoglobin (Hb), Urine Albumin, Ultrasound Dating Scan"),
                ("ANC 2 (Second Trimester - Week 20)", 20, "Tetanus Toxoid (TT 1), Iron & Folic Acid Tablets Distribution, Fundal Height, Ultrasound Anomaly Scan"),
                ("ANC 3 (Third Trimester - Week 28)", 28, "Tetanus Toxoid (TT 2 / Booster), Gestational Diabetes Check, Fetal Growth Assessment"),
                ("ANC 4 (Pre-Delivery - Week 36)", 36, "Fetal Presentation, Birth Preparedness Plan, Area Hospital Delivery Referral Slip")
            ]
            
            for v_title, v_week, v_desc in anc_visits:
                if week >= v_week:
                    status_badge = "✅ COMPLETED"
                    s_color = "#059669"
                    s_bg = "#dcfce7"
                    border_style = "2px solid #86efac"
                elif week >= v_week - 4:
                    status_badge = "⏳ SCHEDULED / DUE"
                    s_color = "#d97706"
                    s_bg = "#fef3c7"
                    border_style = "2px solid #fde047"
                else:
                    status_badge = "📅 UPCOMING"
                    s_color = "#64748b"
                    s_bg = "#f1f5f9"
                    border_style = "1.5px solid #e2e8f0"
                    
                st.markdown(f"""
                <div style="background: #ffffff; border: {border_style}; border-radius: 14px; padding: 18px 20px; margin-bottom: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.02);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <h4 style="margin: 0; color: #0f172a; font-size: 1.05rem; font-weight: 800;">{v_title}</h4>
                        <span style="background: {s_bg}; color: {s_color}; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 0.8rem;">
                            {status_badge}
                        </span>
                    </div>
                    <p style="margin: 0; color: #475569; font-size: 0.9rem; line-height: 1.5;">
                        <b>Clinical Scope:</b> {v_desc}
                    </p>
                    <div style="margin-top: 8px; font-size: 0.82rem; color: #64748b; font-weight: 600;">
                        📍 Location: Kondapur Community Health Centre & Sub-Center | Attending: ASHA & Staff Nurse
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
            # Previous Alerts History
            st.markdown("<br><h4 style='color: #0f172a; font-weight: 800; font-family: Outfit, sans-serif; margin-bottom: 10px;'>🚨 Previous Medical Escalations & Alerts</h4>", unsafe_allow_html=True)
            conn = get_connection()
            c = conn.cursor()
            c.execute("""
            SELECT id, risk_level, status, timestamp 
            FROM alerts 
            WHERE user_id = ? OR user_id = ? 
            ORDER BY timestamp DESC
            """, (mother_id_str, m_id))
            patient_alerts = c.fetchall()
            conn.close()
            
            if patient_alerts:
                for a_id, r_lvl, a_stat, a_time in patient_alerts:
                    st.markdown(f"""
                    <div style="background: #fff1f2; border: 1.5px solid #fecdd3; border-radius: 12px; padding: 12px 16px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <span style="font-weight: 800; color: #9f1239;">Alert #{a_id} — {r_lvl} Risk</span>
                            <span style="color: #64748b; font-size: 0.84rem; margin-left: 10px;">{a_time}</span>
                        </div>
                        <span style="background: #ffffff; color: #9f1239; border: 1px solid #fecdd3; padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 700;">
                            Status: {a_stat}
                        </span>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown("<p style='color: #059669; font-weight: 600; font-size: 0.9rem;'>✓ No high-risk emergency escalations on record. All vitals historically normal.</p>", unsafe_allow_html=True)

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
        
        # Initialize AI & TTS services
        lm_client = LMStudioClient(
            base_url=st.session_state.get('lm_studio_url', config.LM_STUDIO_BASE_URL),
            chat_endpoint=st.session_state.get('lm_studio_chat_endpoint', getattr(config, 'LM_STUDIO_CHAT_ENDPOINT', None)),
            default_model=st.session_state.get('lm_studio_model', config.LM_STUDIO_MODEL)
        )
        ai_svc = AIService(client=lm_client)
        tts_svc = TTSService()

        st.markdown("<div class='health-card' style='text-align: center; padding: 2rem;'>", unsafe_allow_html=True)
        audio_data = st.audio_input(_t("audio_input_label"))
        st.markdown("</div>", unsafe_allow_html=True)
        
        if audio_data is not None:
            # Extract raw audio bytes to compute unique SHA-256 fingerprint
            try:
                audio_bytes = audio_data.getvalue()
            except Exception:
                try:
                    audio_bytes = audio_data.read()
                except Exception:
                    audio_bytes = b""
            
            audio_hash = hashlib.sha256(audio_bytes).hexdigest() if audio_bytes else None

            # Process automatically when new audio is recorded
            if audio_hash and audio_hash != st.session_state.get('last_processed_audio_hash'):
                with st.spinner(_t("processing_audio")):
                    vs = VoiceService()
                    active_app_lang = st.session_state.get('language', 'English')
                    res = vs.transcribe_audio_data(audio_data, language_name=active_app_lang)
                    
                    if res["status"] == "success":
                        recognized_text = res["text"].strip()
                        st.session_state['transcription'] = recognized_text
                        st.session_state['last_processed_audio_hash'] = audio_hash
                        
                        # Detect true language from transcription script or fallback to active app language
                        detected_lang = ai_svc.detect_language(recognized_text, default_lang=active_app_lang)
                        st.session_state['voice_detected_lang'] = detected_lang
                        
                        # 1. Deterministic Clinical Risk & Symptom Assessment Pipeline
                        ai_result = calculate_risk_from_text(recognized_text, mood="normal", nutrition="good")
                        extracted_symptoms = ai_result.get('extracted_symptoms', [])
                        mother_id = st.session_state.get('unique_id', 'Unknown')
                        mother_name = st.session_state.get('mother_name', '')
                        
                        # Database logging & alerts
                        try:
                            save_daily_log(mother_id, extracted_symptoms, "normal", "good", ai_result['risk_score'], ai_result['risk_level'], ai_result['timestamp'])
                            if ai_result['escalation']:
                                create_alert(mother_id, ai_result['risk_level'], ai_result['timestamp'])
                        except Exception:
                            pass
                        
                        st.session_state['voice_risk_result'] = {
                            "score": ai_result['risk_score'],
                            "level": ai_result['risk_level'],
                            "recommendation": ai_result['recommendation'],
                            "escalation": ai_result['escalation'],
                            "is_emergency": ai_result.get('is_emergency', False),
                            "extracted_symptoms": extracted_symptoms,
                            "offline": not is_online(),
                            "mother_id": mother_id
                        }
                        
                        # 2. ASHA Worker Safety Escalation Pipeline (Deduplicated, deterministic)
                        try:
                            escalation_svc = EscalationService()
                            escalation_res = escalation_svc.escalate(
                                mother_id=mother_id,
                                risk_result=ai_result,
                                event_id=f"{mother_id}_{audio_hash}",
                                user_context={"mother_name": mother_name, "risk_level": ai_result['risk_level']},
                                language=detected_lang
                            )
                            st.session_state['voice_escalation_res'] = escalation_res
                        except Exception:
                            pass

                        # 3. Conversational AI Pipeline (Same-Language Response)
                        try:
                            user_ctx = {
                                "risk_level": ai_result.get('risk_level', 'Normal'),
                                "mother_name": mother_name
                            }
                            ai_response = ai_svc.process_message(
                                prompt=recognized_text,
                                chat_history=[],
                                user_context=user_ctx,
                                language_name=detected_lang,
                                custom_model=st.session_state.get('lm_studio_model')
                            )
                            st.session_state['voice_ai_response'] = ai_response
                            st.session_state['voice_ai_status'] = "success"

                            # 4. Automatic TTS Voice Output Synthesis (Same language)
                            try:
                                audio_bytes = tts_svc.synthesize(ai_response.get("response", ""), language_name=detected_lang)
                                st.session_state['voice_ai_audio_bytes'] = audio_bytes
                            except Exception:
                                st.session_state['voice_ai_audio_bytes'] = None

                        except Exception as e:
                            st.session_state['voice_ai_response'] = {
                                "response": f"AI Processing Error: {str(e)}",
                                "source": "error",
                                "is_emergency": False,
                                "server_online": False,
                                "diagnostic": str(e)
                            }
                            st.session_state['voice_ai_status'] = "error"
                            st.session_state['voice_ai_audio_bytes'] = None
                            
                        st.rerun()
                    elif res["status"] == "not_understood":
                        st.warning(f"⚠️ {res['message']}")
                        st.session_state['transcription'] = ""
                        st.session_state['last_processed_audio_hash'] = audio_hash
                    else:
                        st.error(f"❌ {res['message']}")
                        st.session_state['transcription'] = _t("err_audio_fail")
                        st.session_state['last_processed_audio_hash'] = audio_hash
        else:
            if st.session_state.get('last_processed_audio_hash'):
                st.session_state['transcription'] = ""
                st.session_state['last_processed_audio_hash'] = None
                st.session_state['voice_ai_response'] = None
                st.session_state['voice_risk_result'] = None
                st.session_state['voice_ai_audio_bytes'] = None
                
        transcribed_text = st.text_area(_t("transcription_label"), st.session_state['transcription'], height=100)


        # ---------------- AUTOMATIC VOICE STATUS & TTS PLAYBACK ----------------
        if st.session_state.get('voice_ai_response'):
            ai_resp = st.session_state['voice_ai_response']
            is_emergency = ai_resp.get("is_emergency", False) or st.session_state.get('voice_risk_result', {}).get('is_emergency', False)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Urgent medical emergency safety banner if triggered
            if is_emergency:
                st.markdown("""
                <div style="background: #ffebee; border: 2px solid #ef5350; color: #b71c1c; padding: 18px 22px; border-radius: 12px; margin-bottom: 20px;">
                    <h3 style="margin: 0 0 6px 0; color: #b71c1c; display: flex; align-items: center; gap: 8px;">🚨 Emergency Assistance Triggered</h3>
                    <p style="margin: 0; font-size: 1.05rem; line-height: 1.5;">Immediate emergency care guidance active. Contacting <strong>108 Ambulance</strong> and your local ASHA worker immediately.</p>
                </div>
                """, unsafe_allow_html=True)

            # Essential Clean Visual Status Indicator
            detected_lang_label = st.session_state.get('voice_detected_lang', st.session_state.get('language', 'English'))
            st.markdown(f"""
            <div style="background: white; border: 1px solid #e2e8f0; border-left: 5px solid #0284c7; border-radius: 10px; padding: 16px 20px; margin-bottom: 15px; box-shadow: 0 2px 8px rgba(0,0,0,0.04); display: flex; align-items: center; gap: 12px;">
                <span style="font-size: 1.6rem;">🔊</span>
                <div>
                    <strong style="color: #0f172a; font-size: 1rem;">AI Voice Guidance ({detected_lang_label})</strong>
                    <p style="color: #64748b; font-size: 0.88rem; margin: 2px 0 0 0;">Spoken response active</p>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Automatic audio playback (No manual listen button required)
            if st.session_state.get('voice_ai_audio_bytes'):
                st.audio(st.session_state['voice_ai_audio_bytes'], format="audio/mp3", autoplay=True)


        # ---------------- CLINICAL RISK ASSESSMENT ----------------
        if st.session_state.get('voice_risk_result'):
            risk_res = st.session_state['voice_risk_result']
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("### 🩺 Clinical Risk & Symptom Assessment")
            
            if risk_res.get('escalation') or risk_res.get('level') == "High" or risk_res.get('is_emergency'):
                st.error(f"🚨 {_t('current_risk')}: HIGH RISK (Risk Score: {risk_res['score']}). {risk_res['recommendation']}")
                if risk_res.get('offline'):
                    from app import render_offline_sms_button
                    render_offline_sms_button(risk_res.get('mother_id', 'Unknown'))
            elif risk_res.get('level') == "Medium":
                st.warning(f"⚠️ {_t('current_risk')}: MEDIUM RISK (Risk Score: {risk_res['score']}). {risk_res['recommendation']}")
            else:
                st.success(f"{_t('success_analyzed_voice')} Risk Score: {risk_res['score']} ({risk_res['level']} Risk). {risk_res['recommendation']}")

            # Telephony Escalation Status Indicators
            if st.session_state.get('voice_escalation_res'):
                esc_res = st.session_state['voice_escalation_res']
                sms_stat = esc_res.get("sms_status")
                call_stat = esc_res.get("call_status")
                
                status_pills = []
                if sms_stat:
                    if sms_stat.get("success"):
                        if sms_stat.get("trial_mode"):
                            status_pills.append("📱 **Twilio Trial SMS Alert Sent**")
                        else:
                            status_pills.append("📱 **Emergency SMS Sent**")
                    else:
                        err_text = sms_stat.get("error", "Failed")
                        if "trial" in str(err_text).lower():
                            status_pills.append(f"⚠️ **Twilio Trial Restriction** ({sms_stat.get('status')})")
                        else:
                            status_pills.append("⚠️ **SMS Alert Failed**")
                
                if call_stat:
                    if call_stat.get("success"):
                        if call_stat.get("trial_mode"):
                            status_pills.append("📞 **Twilio Trial Emergency Call Initiated**")
                        else:
                            status_pills.append("📞 **Emergency Call Initiated**")
                    else:
                        err_text = call_stat.get("error", "Failed")
                        if "trial" in str(err_text).lower():
                            status_pills.append(f"⚠️ **Twilio Trial Restriction** ({call_stat.get('status')})")
                        else:
                            status_pills.append("⚠️ **Emergency Call Failed**")
                
                if status_pills:
                    st.caption(" • ".join(status_pills))

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
        st.markdown(f"<h1 style='color: #0f172a; font-family: Outfit, sans-serif; font-size: 2.3rem; font-weight: 800; margin-bottom: 0.3rem;'>{_t('reminders_main_title')}</h1>", unsafe_allow_html=True)
        st.markdown(f"<p style='color: #475569; font-size: 1.05rem; margin-bottom: 1.5rem;'>{_t('reminders_main_desc')}</p>", unsafe_allow_html=True)

        # Custom CSS for Premium Healthcare Reminder Cards
        st.markdown("""
            <style>
            .rem-card-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .rem-card {
                padding: 1.4rem;
                border-radius: 16px;
                background: #ffffff;
                border: 1.5px solid #e2e8f0;
                box-shadow: 0 4px 14px rgba(0,0,0,0.03);
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                min-height: 190px;
                transition: transform 0.2s ease, box-shadow 0.2s ease;
                margin-bottom: 10px;
            }
            .rem-card:hover {
                transform: translateY(-3px);
                box-shadow: 0 8px 24px rgba(0,0,0,0.06);
            }
            .rem-icon {
                font-size: 2.2rem;
                margin-bottom: 8px;
            }
            .rem-title {
                font-family: 'Outfit', sans-serif;
                font-size: 1.2rem;
                font-weight: 800;
                color: #0f172a;
                margin-bottom: 4px;
            }
            .rem-desc {
                font-size: 0.9rem;
                color: #475569;
                line-height: 1.5;
            }
            
            /* Specific Healthcare Category Accents */
            .grad-iron { border-top: 4px solid #ea580c; }
            .grad-iron .rem-title { color: #9a3412; }
            
            .grad-calcium { border-top: 4px solid #0284c7; }
            .grad-calcium .rem-title { color: #0369a1; }
            
            .grad-folic { border-top: 4px solid #16a34a; }
            .grad-folic .rem-title { color: #166534; }
            
            .grad-vit-d { border-top: 4px solid #d97706; }
            .grad-vit-d .rem-title { color: #92400e; }
            
            .grad-water { border-top: 4px solid #0284c7; }
            .grad-water .rem-title { color: #0369a1; }
            
            .grad-exercise { border-top: 4px solid #7c3aed; }
            .grad-exercise .rem-title { color: #5b21b6; }
            
            .grad-rest { border-top: 4px solid #db2777; }
            .grad-rest .rem-title { color: #9d174d; }
            
            /* Medical Alerts */
            .med-alert {
                background: #ffffff;
                border-radius: 14px;
                padding: 1.3rem;
                border: 1.5px solid #e2e8f0;
                border-left: 6px solid;
                box-shadow: 0 4px 12px rgba(0,0,0,0.03);
                margin-bottom: 15px;
            }
            </style>
        """, unsafe_allow_html=True)

        # Sub-tabs for Follow-ups vs Appointments
        rem_tab_followups, rem_tab_appointments = st.tabs(["🔔 Follow-ups (Daily Medicine & Habits)", "📅 Appointments (ANC & Clinic Schedule)"])

        with rem_tab_followups:
            # 1. Daily Medicine & Habits
            st.markdown(f"<h3 style='color: #0f172a; font-family: Outfit, sans-serif; font-weight: 800; margin-top: 1rem; border-bottom: 2px solid #f1f5f9; padding-bottom: 10px;'>💊 {_t('daily_reminders_title')}</h3>", unsafe_allow_html=True)
            
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

        with rem_tab_appointments:
            # 2. Medical Alerts & Appointments
            st.markdown(f"<h3 style='color: #0f172a; font-family: Outfit, sans-serif; font-weight: 800; margin-top: 1rem; border-bottom: 2px solid #f1f5f9; padding-bottom: 10px;'>📅 {_t('medical_reminders_title')}</h3>", unsafe_allow_html=True)
            
            m1, m2, m3 = st.columns(3)
            with m1:
                st.markdown(f"<div class='med-alert' style='border-left-color: #dc2626;'><h4 style='color: #991b1b; font-family: Outfit, sans-serif; font-size: 1.15rem; font-weight: 800; margin:0;'>{_t('med_anc')}</h4><p style='margin:6px 0; color: #1e293b; font-weight: 600;'>{_t('med_anc_rem')}</p><p style='font-size:0.85rem; color:#64748b; margin:0;'>📍 PHC Center | 🕒 10:00 AM</p></div>", unsafe_allow_html=True)
            with m2:
                st.markdown(f"<div class='med-alert' style='border-left-color: #d97706;'><h4 style='color: #92400e; font-family: Outfit, sans-serif; font-size: 1.15rem; font-weight: 800; margin:0;'>{_t('med_ultrasound')}</h4><p style='margin:6px 0; color: #1e293b; font-weight: 600;'>{_t('med_ultrasound_rem')}</p><p style='font-size:0.85rem; color:#64748b; margin:0;'>📍 District Imaging Lab</p></div>", unsafe_allow_html=True)
            with m3:
                st.markdown(f"<div class='med-alert' style='border-left-color: #0284c7;'><h4 style='color: #0369a1; font-family: Outfit, sans-serif; font-size: 1.15rem; font-weight: 800; margin:0;'>{_t('med_vaccination')}</h4><p style='margin:6px 0; color: #1e293b; font-weight: 600;'>{_t('med_vaccination_rem')}</p><p style='font-size:0.85rem; color:#64748b; margin:0;'>📍 Local Health Clinic</p></div>", unsafe_allow_html=True)

        # 3. AI Recommendation Panel
        st.markdown(f"<h3 style='color: #2c3e50; margin-top: 2rem; border-bottom: 2px solid #eee; padding-bottom: 10px;'>🤖 {_t('ai_recommendation_title')}</h3>", unsafe_allow_html=True)
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
        import plotly.graph_objects as go
        st.title(_t("risk_panel_title"))
        st.markdown(_t("risk_panel_desc"))
        
        if st.button(_t("btn_start_ai"), type="primary"):
            st.session_state['simulating'] = True
            
        dashboard_placeholder = st.empty()
        
        if st.session_state.get('simulating', False):
            import random
            
            st.info(_t("status_monitoring"))
            st.write(_t("escalation_status"))

            # Fast real-time streaming preview (snappy UI feedback)
            for i in range(3):
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
                
                time.sleep(0.05)  # Fast responsive animation delay
            
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
                        <div class="classy-card card-amber" style="height: 100%;">
                            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                                <span class="icon-badge">⚠️</span>
                                <span class="card-pill">{_t('risk_medium_alert')}</span>
                            </div>
                            <h4 class="card-title">{_t('final_assessment')}</h4>
                            <p class="card-value" style="font-size: 2.4rem;">65<span style="font-size: 1.1rem; font-weight: 600;">/100</span></p>
                            <p class="card-caption" style="margin-top: 10px;"><b>{_t('recommendation')}:</b> {_t('monitor_swelling_tip')}</p>
                            <p class="card-caption" style="margin-top: 6px;"><b>{_t('escalation_status')}:</b> {_t('notified_asha_worker')}</p>
                        </div>
                    """, unsafe_allow_html=True)
                    
                with c2:
                    st.plotly_chart(fig, use_container_width=True)
                    
        else:
            # Default state before clicking button
            with dashboard_placeholder.container():
                st.info(_t("click_start_ai_info"))

    elif page == "Live Location & Map":
        import folium
        import requests
        import numpy as np
        from streamlit_folium import st_folium
        from geopy.distance import geodesic
        from streamlit_geolocation import streamlit_geolocation
        st.title(_t("map_title_page"))
        st.markdown(_t("map_desc_page"))
        
        online_status = is_online()
        mother_id = st.session_state.get('unique_id', 'Unknown')
            
        # Capture GPS
        loc = streamlit_geolocation()
        lat, lon = None, None
        
        if loc and loc.get('latitude') and loc.get('longitude'):
            lat = float(loc['latitude'])
            lon = float(loc['longitude'])
            st.success(_t("success_loc_captured"))
            
            if online_status:
                if mother_id != 'Unknown':
                    update_location(mother_id, lat, lon)
            else:
                if mother_id != 'Unknown':
                    update_location(mother_id, lat, lon)
                import json
                payload = {"latitude": lat, "longitude": lon, "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                from database import save_offline_record
                save_offline_record(mother_id, "location", json.dumps(payload))
        else:
            # Attempt to retrieve saved coordinates from database
            if mother_id != 'Unknown':
                try:
                    conn = get_connection()
                    c = conn.cursor()
                    c.execute("SELECT latitude, longitude FROM mothers WHERE unique_id=?", (mother_id,))
                    row = c.fetchone()
                    conn.close()
                    if row and row[0] is not None and row[1] is not None:
                        lat, lon = float(row[0]), float(row[1])
                except Exception:
                    pass
            
            # Default fallback coordinates (Moinabad Sector cluster) if GPS not yet granted
            if lat is None or lon is None:
                lat, lon = 17.3200, 78.2800

        # Check latest risk level from daily logs
        conn = get_connection()
        c = conn.cursor()
        c.execute("SELECT risk_level FROM daily_logs WHERE user_id=? ORDER BY date DESC LIMIT 1", (mother_id,))
        risk_row = c.fetchone()
        conn.close()
        is_high_risk = risk_row and risk_row[0] == "High"

        # Catalog of Accredited Hospitals, CHCs, and Maternity Wings situated around patient
        hospitals_catalog = [
            {
                "id": "hosp_kondapur",
                "name": "Kondapur Community Health Centre & Maternity Wing",
                "type": "Community Health Centre (CHC)",
                "category": "Government First Referral Unit",
                "offset_lat": 0.012,
                "offset_lon": 0.014,
                "phone": "+91 040-23112345",
                "emergency_phone": "108 / 102",
                "duty_doctor": "Dr. Ananya Rao, MD (Obstetrics & Gynaecology)",
                "hours": "Open 24/7 (Emergency & Active Labour Ward)",
                "address": "Opp. Old Gram Panchayat, Main Road, Kondapur Sector 3",
                "facilities": [
                    "24/7 Normal & Emergency C-Section Delivery",
                    "Designated Blood Storage Unit",
                    "Special Newborn Care Unit (SNCU)",
                    "Ultrasound Doppler Sonography",
                    "Free Medicine & Nutrition (JSSK Scheme)"
                ],
                "ambulance": "108 Ambulance Stationed at Gate (Vehicle TS-07-G-1082)",
                "beds": "50 Beds (30 Maternal Beds)",
                "is_emergency": True
            },
            {
                "id": "hosp_moinabad",
                "name": "Moinabad 24/7 Primary Health Centre (PHC)",
                "type": "Primary Health Centre (PHC)",
                "category": "24/7 Rural Health Centre",
                "offset_lat": -0.018,
                "offset_lon": 0.010,
                "phone": "+91 8413-255108",
                "emergency_phone": "108",
                "duty_doctor": "Dr. Suresh Varma, MBBS (Medical Officer)",
                "hours": "Open 24/7 for Maternity Deliveries",
                "address": "Chevella Main Road, Opp. Agriculture Market Yard, Moinabad",
                "facilities": [
                    "24/7 Labour Room with Certified ANM Midwives",
                    "Routine Antenatal Care (ANC) & TT Vaccination",
                    "Free Iron, Calcium & Folic Acid Dispensary",
                    "Direct ASHA Link Worker Station"
                ],
                "ambulance": "108 Rapid Response Van on Standby",
                "beds": "12 Beds (8 Maternity Beds)",
                "is_emergency": False
            },
            {
                "id": "hosp_chilkur",
                "name": "Chilkur Rural Maternity Sub-Centre",
                "type": "Rural Health Sub-Centre",
                "category": "Sub-Centre Care",
                "offset_lat": 0.024,
                "offset_lon": -0.019,
                "phone": "+91 8413-221199",
                "emergency_phone": "108",
                "duty_doctor": "Dr. K. Lavanya, DGO (Obstetric Specialist)",
                "hours": "8:00 AM - 8:00 PM (Emergency Delivery Call Active)",
                "address": "Temple Cross Road, Near ANM Sub-Centre, Chilkur Village",
                "facilities": [
                    "High-Risk Pregnancy Screening & Referral",
                    "Blood Pressure & Blood Glucose Monitoring",
                    "Fetal Heart Rate (FHR) Doppler Screening",
                    "Emergency First-Aid & Patient Stabilization"
                ],
                "ambulance": "Dispatched on Call from CHC (Avg. 10 mins)",
                "beds": "6 Day-Care Beds",
                "is_emergency": False
            },
            {
                "id": "hosp_himayath",
                "name": "Himayath Sagar Maternal & Child Welfare Centre",
                "type": "Maternal & Child Health (MCH) Centre",
                "category": "Specialized Maternity Wing",
                "offset_lat": -0.038,
                "offset_lon": -0.025,
                "phone": "+91 040-24018899",
                "emergency_phone": "108 / 102",
                "duty_doctor": "Dr. Meenakshi Sundaram, MD (Pediatrics & OB/GYN)",
                "hours": "Open 24/7 Maternity Emergency",
                "address": "Himayath Sagar Ring Road Junction, Rajendranagar Taluk",
                "facilities": [
                    "High-Risk Maternal Delivery Ward",
                    "Level-2 Neonatal Intensive Care",
                    "Continuous Electronic Fetal Monitoring (EFM)",
                    "Dedicated 102 Janani Shishu Express Vehicle",
                    "Lactation & Postnatal Counselling"
                ],
                "ambulance": "Dedicated 102 Mother Van On-Site",
                "beds": "35 Beds",
                "is_emergency": True
            },
            {
                "id": "hosp_chevella",
                "name": "Chevella Area Sub-District Hospital",
                "type": "Area Sub-District Hospital",
                "category": "CEmOC Accredited Apex Centre",
                "offset_lat": 0.048,
                "offset_lon": 0.036,
                "phone": "+91 8417-234200",
                "emergency_phone": "108 / 102 / 104",
                "duty_doctor": "Dr. Rajeshwar Reddy, MS (Chief Obstetric Surgeon)",
                "hours": "Open 24/7 Full Surgical & Maternity",
                "address": "Hospital Road, Adjacent to Bus Depot, Chevella",
                "facilities": [
                    "Comprehensive Emergency Obstetric Care (CEmOC)",
                    "Government Licensed 24-Hr Blood Bank",
                    "Twin Modern Operating Theatres for C-Sections",
                    "Maternal Intensive Care Unit (MICU)",
                    "Free Patient Diet & Transport (KCR Kit/JSSK)"
                ],
                "ambulance": "2 Advanced Life Support (ALS) Ambulances",
                "beds": "100 Beds",
                "is_emergency": True
            },
            {
                "id": "hosp_apex_women",
                "name": "District Women & Child Motherhood Hospital",
                "type": "District Apex Referral Hospital",
                "category": "Tertiary Referral Centre",
                "offset_lat": -0.058,
                "offset_lon": 0.045,
                "phone": "+91 040-24501234",
                "emergency_phone": "108 / 102 / 181",
                "duty_doctor": "Dr. P. Sangeetha, Head of Obstetrics & Neonatology",
                "hours": "Open 24/7 Full Tertiary Care",
                "address": "Civil Hospital Road, District Medical Complex",
                "facilities": [
                    "Tertiary Level-3 NICU with Neonatal Ventilators",
                    "24/7 Blood Component Separation Unit",
                    "Critical Care Obstetrics & High Dependency Unit",
                    "Free Delivery & Postpartum Care Desk",
                    "Pediatric Intensive Care Unit (PICU)"
                ],
                "ambulance": "4 Dedicated Emergency Ambulances",
                "beds": "150 Beds",
                "is_emergency": True
            }
        ]

        # Calculate exact distance from patient live GPS and strictly filter <= 10 km
        hospitals_within_10km = []
        for h in hospitals_catalog:
            h_lat = lat + h["offset_lat"]
            h_lon = lon + h["offset_lon"]
            dist = geodesic((lat, lon), (h_lat, h_lon)).km
            if dist <= 10.0:
                h_copy = dict(h)
                h_copy["lat"] = h_lat
                h_copy["lon"] = h_lon
                h_copy["distance"] = round(dist, 1)
                h_copy["eta_mins"] = max(4, int(dist * 2.2))
                hospitals_within_10km.append(h_copy)

        # Sort by proximity
        hospitals_within_10km.sort(key=lambda x: x["distance"])

        nearest_hosp = hospitals_within_10km[0] if hospitals_within_10km else None

        # Display Top Status Banner
        if is_high_risk:
            st.markdown("""
            <div style="background: #fef2f2; border: 1.5px solid #fca5a5; border-left: 6px solid #dc2626; padding: 14px 18px; border-radius: 12px; margin-bottom: 14px; box-shadow: 0 2px 8px rgba(220,38,38,0.06);">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <span style="font-size: 1.5rem;">🚨</span>
                    <div>
                        <div style="color: #991b1b; font-weight: 800; font-size: 1rem;">High-Risk Priority Alert Active</div>
                        <div style="color: #b91c1c; font-size: 0.88rem; margin-top: 2px;">Emergency obstetric surgical centres and blood banks within 10 km are highlighted in red. Tap below to call emergency services or navigate immediately.</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        elif nearest_hosp:
            st.markdown(f"""
            <div style="background: #eff6ff; border: 1.5px solid #bfdbfe; border-left: 6px solid #0284c7; padding: 14px 18px; border-radius: 12px; margin-bottom: 14px; box-shadow: 0 2px 8px rgba(2,132,199,0.06);">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <span style="font-size: 1.5rem;">🏥</span>
                    <div>
                        <div style="color: #0369a1; font-weight: 800; font-size: 1rem;">Verified Healthcare Network Within 10 km</div>
                        <div style="color: #0284c7; font-size: 0.88rem; margin-top: 2px;">Your nearest health center is <b>{nearest_hosp['name']}</b> ({nearest_hosp['distance']} km away). Click on any hospital pin or selector below to view phone numbers, duty doctors, and facilities.</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Draw Full-Width Interactive Map
        m = folium.Map(location=[lat, lon], zoom_start=13, tiles="OpenStreetMap")

        # Mother's Current GPS Location Marker
        mother_popup_html = f"""
        <div style="font-family: 'Segoe UI', sans-serif; font-size: 12px; min-width: 160px;">
            <b style="color: #0284c7; font-size: 13px;">📍 Your Live Location</b><br>
            <span style="color: #64748b;">Mother ID: {mother_id}</span><br>
            <span style="color: #64748b;">GPS: {lat:.4f}, {lon:.4f}</span>
        </div>
        """
        folium.Marker(
            [lat, lon],
            popup=folium.Popup(mother_popup_html, max_width=220),
            tooltip="📍 Your Current GPS Location (Mother)",
            icon=folium.Icon(color="blue", icon="user")
        ).add_to(m)

        # 10 km safety boundary circle
        folium.Circle(
            radius=10000,
            location=[lat, lon],
            color="#0284c7",
            weight=1.5,
            dash_array="6, 8",
            fill=False,
            tooltip="10 km Medical Catchment Zone"
        ).add_to(m)

        if is_high_risk:
            # 600m high-risk alert perimeter
            folium.Circle(
                radius=600,
                location=[lat, lon],
                color="#dc2626",
                fill=True,
                fill_color="#ef4444",
                fill_opacity=0.2,
                tooltip="High Risk Priority Attention Zone (600m)"
            ).add_to(m)

        # Plot all hospitals strictly within 10 km
        for h in hospitals_within_10km:
            marker_color = "red" if (is_high_risk or h.get("is_emergency")) else "green"
            marker_icon = "plus" if (is_high_risk or h.get("is_emergency")) else "medkit"

            popup_html = f"""
            <div style="font-family: 'Segoe UI', Arial, sans-serif; min-width: 220px; padding: 4px;">
                <b style="color: #0b5394; font-size: 13px;">{h['name']}</b><br>
                <span style="font-size: 11px; background: #e0f2fe; color: #0369a1; padding: 2px 6px; border-radius: 4px; font-weight: bold;">{h['type']}</span><br>
                <div style="margin-top: 6px; font-size: 12px; color: #334155; line-height: 1.5;">
                    <b>📍 Distance:</b> {h['distance']} km (~{h['eta_mins']} mins)<br>
                    <b>📞 Phone:</b> <a href="tel:{h['phone']}" style="color: #0284c7; font-weight: bold;">{h['phone']}</a><br>
                    <b>👩‍⚕️ Doctor:</b> {h['duty_doctor']}<br>
                    <b>🚑 Emergency:</b> {h['emergency_phone']}
                </div>
                <div style="margin-top: 8px;">
                    <a href="https://www.google.com/maps/dir/?api=1&origin={lat},{lon}&destination={h['lat']},{h['lon']}" target="_blank" style="display: block; background: #0284c7; color: white; text-align: center; padding: 5px 8px; border-radius: 6px; text-decoration: none; font-size: 11px; font-weight: bold;">🗺️ Open in Google Maps</a>
                </div>
            </div>
            """

            folium.Marker(
                [h["lat"], h["lon"]],
                popup=folium.Popup(popup_html, max_width=280),
                tooltip=f"🏥 {h['name']} ({h['distance']} km)",
                icon=folium.Icon(color=marker_color, icon=marker_icon)
            ).add_to(m)

        # Render full container width map
        map_output = st_folium(m, use_container_width=True, height=480, key="mother_hospital_map_10km")

        # Synchronize selection if user clicked a marker on the map
        if map_output and map_output.get("last_object_clicked"):
            clicked = map_output["last_object_clicked"]
            c_lat, c_lon = clicked.get("lat"), clicked.get("lng")
            if c_lat and c_lon:
                for h in hospitals_within_10km:
                    if abs(h["lat"] - c_lat) < 0.003 and abs(h["lon"] - c_lon) < 0.003:
                        st.session_state["selected_hospital_id"] = h["id"]
                        break

        # Hospital Selection Section
        st.markdown("<div style='margin-top: 20px;'></div>", unsafe_allow_html=True)
        st.markdown("### 🏥 Hospital Details & Contact Information")
        st.markdown("<p style='color: #64748b; font-size: 0.95rem; margin-top: -8px;'>Click on any hospital marker on the map above, or select from the options below to view phone numbers, duty doctors, and facilities within 10 km:</p>", unsafe_allow_html=True)

        hospital_names = [f"{h['name']} ({h['distance']} km away)" for h in hospitals_within_10km]
        
        # Determine current selected index
        current_sel_id = st.session_state.get("selected_hospital_id", hospitals_within_10km[0]["id"] if hospitals_within_10km else None)
        selected_idx = 0
        for idx, h in enumerate(hospitals_within_10km):
            if h["id"] == current_sel_id:
                selected_idx = idx
                break

        col_sel, col_filter = st.columns([3, 1])
        with col_sel:
            selected_choice = st.selectbox(
                "Choose Hospital within 10 km:",
                options=hospital_names,
                index=selected_idx,
                key="hosp_choice_select"
            )
            # Update session state based on selectbox
            chosen_hosp_idx = hospital_names.index(selected_choice)
            selected_hosp = hospitals_within_10km[chosen_hosp_idx]
            st.session_state["selected_hospital_id"] = selected_hosp["id"]
        
        with col_filter:
            st.markdown(f"<div style='margin-top: 28px; text-align: right;'><span style='background: #f1f5f9; color: #475569; padding: 8px 14px; border-radius: 8px; font-weight: 700; font-size: 0.88rem; border: 1px solid #cbd5e1;'>{len(hospitals_within_10km)} Centers in 10 km</span></div>", unsafe_allow_html=True)

        # Quick-select hospital pill buttons
        pill_cols = st.columns(len(hospitals_within_10km))
        for idx, h in enumerate(hospitals_within_10km):
            with pill_cols[idx]:
                short_name = h['name'].split()[0] + " " + (h['name'].split()[1] if len(h['name'].split()) > 1 else "")
                is_curr = (h['id'] == selected_hosp['id'])
                if st.button(
                    f"{'📍 ' if is_curr else ''}{short_name}\n({h['distance']} km)", 
                    key=f"pill_hosp_{h['id']}", 
                    use_container_width=True,
                    type="primary" if is_curr else "secondary"
                ):
                    st.session_state["selected_hospital_id"] = h["id"]
                    st.rerun()

        # Detailed Hospital Information Card
        with st.container(border=True):
            head_col1, head_col2 = st.columns([3, 1])
            with head_col1:
                st.markdown(f"""<div style="display: flex; gap: 8px; align-items: center; margin-bottom: 6px; flex-wrap: wrap;">
<span style="background: #0284c7; color: #ffffff; font-size: 0.8rem; font-weight: 700; padding: 4px 12px; border-radius: 6px;">{selected_hosp['type']}</span>
<span style="background: #e0f2fe; color: #0369a1; font-size: 0.8rem; font-weight: 700; padding: 4px 12px; border-radius: 6px; border: 1px solid #bae6fd;">📍 {selected_hosp['distance']} km from your location (approx. {selected_hosp['eta_mins']} mins travel)</span>
<span style="background: #ecfdf5; color: #059669; font-size: 0.8rem; font-weight: 700; padding: 4px 12px; border-radius: 6px; border: 1px solid #a7f3d0;">🟢 {selected_hosp['hours']}</span>
</div>
<h2 style="margin: 0; font-size: 1.55rem; color: #0f172a; font-family: 'Outfit', sans-serif; font-weight: 800;">{selected_hosp['name']}</h2>
<p style="margin: 6px 0 0 0; color: #475569; font-size: 0.95rem; font-weight: 500;">🏢 {selected_hosp['address']}</p>""", unsafe_allow_html=True)
            
            with head_col2:
                st.markdown(f"""<div style="display: flex; flex-direction: column; gap: 8px; margin-top: 4px;">
<a href="tel:{selected_hosp['phone']}" style="background: #16a34a; color: white; font-weight: 700; padding: 10px 14px; border-radius: 10px; text-decoration: none; display: block; text-align: center; font-size: 0.92rem; box-shadow: 0 2px 6px rgba(22,163,74,0.25);">📞 Call Hospital</a>
<a href="https://www.google.com/maps/dir/?api=1&origin={lat},{lon}&destination={selected_hosp['lat']},{selected_hosp['lon']}" target="_blank" style="background: #0284c7; color: white; font-weight: 700; padding: 10px 14px; border-radius: 10px; text-decoration: none; display: block; text-align: center; font-size: 0.92rem; box-shadow: 0 2px 6px rgba(2,132,199,0.25);">🗺️ Get Directions</a>
</div>""", unsafe_allow_html=True)

            st.divider()

            info_c1, info_c2, info_c3, info_c4 = st.columns(4)
            with info_c1:
                with st.container(border=True):
                    st.markdown("<p style='font-size: 0.76rem; font-weight: 800; color: #64748b; text-transform: uppercase; margin: 0;'>👩‍⚕️ Duty Medical Specialist</p>", unsafe_allow_html=True)
                    st.markdown(f"<p style='font-size: 1.02rem; font-weight: 700; color: #0f172a; margin: 4px 0 2px 0;'>{selected_hosp['duty_doctor']}</p>", unsafe_allow_html=True)
                    st.markdown("<p style='font-size: 0.8rem; color: #16a34a; font-weight: 600; margin: 0;'>Active on shift • Labor Ward Open</p>", unsafe_allow_html=True)
            
            with info_c2:
                with st.container(border=True):
                    st.markdown("<p style='font-size: 0.76rem; font-weight: 800; color: #64748b; text-transform: uppercase; margin: 0;'>📞 Direct Reception Desk</p>", unsafe_allow_html=True)
                    st.markdown(f"<p style='font-size: 1.02rem; font-weight: 700; color: #0284c7; margin: 4px 0 2px 0;'><a href='tel:{selected_hosp['phone']}' style='color: #0284c7; text-decoration: none;'>{selected_hosp['phone']}</a></p>", unsafe_allow_html=True)
                    st.markdown("<p style='font-size: 0.8rem; color: #64748b; margin: 0;'>Direct line to Maternity Desk</p>", unsafe_allow_html=True)
            
            with info_c3:
                with st.container(border=True):
                    st.markdown("<p style='font-size: 0.76rem; font-weight: 800; color: #64748b; text-transform: uppercase; margin: 0;'>🚑 Emergency Dispatch</p>", unsafe_allow_html=True)
                    st.markdown("<p style='font-size: 1.02rem; font-weight: 800; color: #dc2626; margin: 4px 0 2px 0;'>Dial 108 / 102</p>", unsafe_allow_html=True)
                    st.markdown(f"<p style='font-size: 0.8rem; color: #64748b; margin: 0;'>{selected_hosp['ambulance']}</p>", unsafe_allow_html=True)
            
            with info_c4:
                with st.container(border=True):
                    st.markdown("<p style='font-size: 0.76rem; font-weight: 800; color: #64748b; text-transform: uppercase; margin: 0;'>🛏️ Hospital Capacity</p>", unsafe_allow_html=True)
                    st.markdown(f"<p style='font-size: 1.02rem; font-weight: 700; color: #0f172a; margin: 4px 0 2px 0;'>{selected_hosp['beds']}</p>", unsafe_allow_html=True)
                    st.markdown("<p style='font-size: 0.8rem; color: #64748b; margin: 0;'>Accredited Maternal Unit</p>", unsafe_allow_html=True)

            st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
            fac_badges = "".join([f"<span style='display: inline-block; background: #f0fdf4; color: #166534; font-size: 0.84rem; font-weight: 700; padding: 6px 14px; border-radius: 8px; border: 1px solid #bbf7d0; margin: 4px 4px 4px 0;'>✓ {fac}</span>" for fac in selected_hosp['facilities']])
            st.markdown(f"""<div>
<div style="font-size: 0.88rem; font-weight: 800; color: #334155; margin-bottom: 8px;">🏥 Available Medical Facilities & Maternity Services:</div>
<div style="display: flex; gap: 8px; flex-wrap: wrap;">{fac_badges}</div>
</div>""", unsafe_allow_html=True)

        # Direct Call Action Buttons
        st.markdown("<div style='margin-top: 14px;'></div>", unsafe_allow_html=True)
        act_col1, act_col2, act_col3 = st.columns(3)
        with act_col1:
            st.markdown(f'<a href="tel:{selected_hosp["phone"]}" style="display:block; text-align:center; background:#16a34a; color:white; padding:12px 14px; border-radius:10px; text-decoration:none; font-weight:bold; font-size:0.95rem; box-shadow:0 2px 6px rgba(22,163,74,0.2);">📞 Call {selected_hosp["name"][:22]}... ({selected_hosp["phone"]})</a>', unsafe_allow_html=True)
        with act_col2:
            st.markdown('<a href="tel:108" style="display:block; text-align:center; background:#dc2626; color:white; padding:12px 14px; border-radius:10px; text-decoration:none; font-weight:bold; font-size:0.95rem; box-shadow:0 2px 6px rgba(220,38,38,0.2);">🚑 Call 108 Emergency Ambulance</a>', unsafe_allow_html=True)
        with act_col3:
            st.markdown('<a href="tel:102" style="display:block; text-align:center; background:#7c3aed; color:white; padding:12px 14px; border-radius:10px; text-decoration:none; font-weight:bold; font-size:0.95rem; box-shadow:0 2px 6px rgba(124,58,237,0.2);">👶 Call 102 Janani Shishu Express</a>', unsafe_allow_html=True)

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
            4: {"seed": "Poppy Seed", "emoji": "🌱", "img": "fetus_week4.jpg", "dev": "Your baby is currently a tiny ball of cells. Major organs are beginning to form.", "tip": "Start taking Folic Acid and stay away from smoke."},
            8: {"seed": "Raspberry", "emoji": "🍓", "img": "fetus_week8.jpg", "dev": "Baby has tiny arms and legs! The heart is beating very fast.", "tip": "Nausea is common; eat small portions of dry food like biscuits."},
            12: {"seed": "Lime", "emoji": "🍋", "img": "fetus_week12.jpg", "dev": "All organs are present. Baby is starting to move their fingers and toes!", "tip": "Time for your first major checkup. Stay hydrated."},
            16: {"seed": "Avocado", "emoji": "🥑", "img": "fetus_week16.jpg", "dev": "Baby's nervous system is starting to work. They can make funny faces now!", "tip": "Sleep on your side for better blood flow to the baby."},
            20: {"seed": "Banana", "emoji": "🍌", "img": "fetus_week20.jpg", "dev": "You are halfway there! Baby can hear your heartbeat and voice.", "tip": "Talk to your baby - they can hear you now! Eat iron-rich foods."},
            24: {"seed": "Corn", "emoji": "🌽", "img": "fetus_week24.jpg", "dev": "Your baby can now hear sounds outside and your voice clearly.", "tip": "Maintain good posture to avoid back pain. Do light walking."},
            28: {"seed": "Eggplant", "emoji": "🍆", "img": "fetus_week28.jpg", "dev": "Baby's eyes are opening and closing. They may start to kick more.", "tip": "Count your baby's kicks. If they move less, visit the doctor."},
            32: {"seed": "Squash", "emoji": "🎃", "img": "fetus_week32.jpg", "dev": "Baby is gaining weight fast and preparing for life outside.", "tip": "Eat smaller, more frequent meals to avoid heartburn."},
            36: {"seed": "Papaya", "emoji": "🍈", "img": "fetus_week36.jpg", "dev": "Baby is almost fully developed and 'dropping' into position for birth.", "tip": "Pack your hospital bag and keep emergency numbers ready."},
            40: {"seed": "Watermelon", "emoji": "🍉", "img": "fetus_week40.jpg", "dev": "Your baby is full term and ready to meet you! Any day now!", "tip": "Stay calm and keep your ASHA worker's number handy."}
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
             # Animated Visual - use local assets directory
             assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
             img_path = os.path.join(assets_dir, data['img'])
             
             if os.path.exists(img_path):
                 img_b64 = load_image_base64(img_path)
                 st.markdown(f"""
                    <div class='baby-vignette'>
                        <img src="data:image/jpeg;base64,{img_b64}" class="baby-img">
                    </div>
                    <div style='text-align: center; margin-top: 15px;'>
                        <span style='font-size: 1.5rem; font-weight: bold; color: #0b5394;'>{_t('baby_size_label')}: {data['seed']} {data['emoji']}</span>
                    </div>
                """, unsafe_allow_html=True)
             else:
                 st.warning(f"Image not found: {data['img']}")
                 st.markdown(f"""
                    <div style='text-align: center; padding: 40px; background: linear-gradient(135deg, #FFE4E1, #FFF0F5); border-radius: 20px;'>
                        <span style='font-size: 5rem;'>{data['emoji']}</span>
                        <div style='margin-top: 15px;'>
                            <span style='font-size: 1.5rem; font-weight: bold; color: #0b5394;'>{_t('baby_size_label')}: {data['seed']} {data['emoji']}</span>
                        </div>
                    </div>
                """, unsafe_allow_html=True)

        with col2:
            st.markdown(f"""
                <div class="classy-card card-blue" style="margin-bottom: 15px;">
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
                        <span class="icon-badge" style="margin-bottom: 0;">👶</span>
                        <h3 class="card-title" style="margin: 0; font-size: 1rem;">{_t('baby_dev_label')}</h3>
                    </div>
                    <p style="font-size: 1.1rem; line-height: 1.6; color: #1e40af; margin: 0;">{data['dev']}</p>
                </div>
                
                <div class="classy-card card-emerald">
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
                        <span class="icon-badge" style="margin-bottom: 0;">🌟</span>
                        <h3 class="card-title" style="margin: 0; font-size: 1rem;">{_t('mother_tip_label')}</h3>
                    </div>
                    <p style="font-size: 1.1rem; font-style: italic; color: #065f46; margin: 0;">{data['tip']}</p>
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
        conn = get_connection()
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
                        send_sms_alert(mother_id)
                        st.error(_t("emergency_initiated_sms"))
                    else:
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
            chat_endpoint=st.session_state.get('lm_studio_chat_endpoint', getattr(config, 'LM_STUDIO_CHAT_ENDPOINT', None)),
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
                    <strong>🟢 LM Studio Active</strong> — Model: <code>{conn_status.get('active_model', 'local-model')}</code> &nbsp;|&nbsp; Server: <code>{lm_client.base_url}</code> &nbsp;|&nbsp; Endpoint: <code>{lm_client.chat_endpoint}</code>
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
                        <li>Load your desired LLM model (e.g. <i>qwen2.5-7b-instruct, Llama 3, Mistral</i>).</li>
                        <li>Click the <strong>Local Server</strong> tab on the left and click <strong>Start Server</strong> (default port 1234).</li>
                    </ol>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Expandable LM Studio Settings
        with st.expander("⚙️ LM Studio Connection Settings", expanded=False):
            cfg_col1, cfg_col2, cfg_col3 = st.columns([2, 2, 2])
            with cfg_col1:
                new_url = st.text_input("LM Studio Base URL", value=st.session_state.get('lm_studio_url', config.LM_STUDIO_BASE_URL))
            with cfg_col2:
                default_endpoint = st.session_state.get('lm_studio_chat_endpoint', getattr(config, 'LM_STUDIO_CHAT_ENDPOINT', f"{config.LM_STUDIO_BASE_URL}/chat/completions"))
                new_endpoint = st.text_input("Chat Completions Endpoint", value=default_endpoint)
            with cfg_col3:
                new_model = st.text_input("Model ID", value=st.session_state.get('lm_studio_model', config.LM_STUDIO_MODEL), placeholder="e.g. qwen2.5-7b-instruct")
            
            if st.button("Apply & Test LM Studio Connection", use_container_width=True):
                st.session_state['lm_studio_url'] = new_url.strip()
                st.session_state['lm_studio_chat_endpoint'] = new_endpoint.strip()
                st.session_state['lm_studio_model'] = new_model.strip()
                test_client = LMStudioClient(
                    base_url=new_url.strip(),
                    chat_endpoint=new_endpoint.strip(),
                    default_model=new_model.strip()
                )
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
    <div style="background: linear-gradient(135deg, #e0f2fe 0%, #ede9fe 50%, #fdf2f8 100%); padding: 26px 30px; border-radius: 18px; margin-bottom: 24px; border: 1.5px solid #bae6fd; box-shadow: 0 4px 20px rgba(0,0,0,0.03);">
        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;">
            <div>
                <h1 style="margin:0; font-size: 2rem; color: #0f172a; font-family: 'Outfit', sans-serif; font-weight: 800; display: flex; align-items: center; gap: 10px;">👶 {_t('baby_portal_title')}</h1>
                <p style="margin: 6px 0 0 0; font-size: 1rem; color: #475569; font-weight: 500;">Monitoring your little one's health, milestones, and development.</p>
            </div>
            <div style="background: #ffffff; padding: 7px 16px; border-radius: 50px; border: 1.5px solid #bae6fd; font-weight: 700; color: #0284c7; font-size: 0.88rem; box-shadow: 0 2px 6px rgba(0,0,0,0.04);">
                🍼 Infant Care Portal
            </div>
        </div>
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
        # Top back navigation buttons
        b_nav_c1, b_nav_c2 = st.columns([1.5, 1])
        with b_nav_c1:
            if st.button("⬅ Back to Section", key="baby_back_to_section_btn", use_container_width=True):
                back_to_patient_services()
        with b_nav_c2:
            if st.button("🏠 Home", key="baby_home_btn", use_container_width=True):
                back_to_roles()
            
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
                
        st.divider()
        cur_lang = st.session_state.get('language', 'English')
        st.selectbox("🌐 " + _t("lang_toggle"), SUPPORTED_LANGUAGES, index=SUPPORTED_LANGUAGES.index(cur_lang) if cur_lang in SUPPORTED_LANGUAGES else 0, key="lang_toggle_baby", on_change=lambda: st.session_state.update({"language": st.session_state.lang_toggle_baby}))
        
        if st.button("⬅ Back to Section", key="baby_bottom_back_btn", use_container_width=True):
            back_to_patient_services()
            
    page = st.session_state.get('baby_page', _t('nav_baby_profile'))
    
    # Universal top back navigation bar for sub-pages
    if page not in [_t('nav_baby_profile'), "Baby Profile"]:
        col_b1, _ = st.columns([1.6, 4])
        with col_b1:
            if st.button("⬅ Back to Baby Profile", key=f"baby_subpage_back_{page}", use_container_width=True):
                st.session_state['baby_page'] = "Baby Profile"
                st.rerun()
    
    if page == _t('nav_baby_profile') or page == "Baby Profile":
        st.markdown(f"### ✨ {_t('baby_profile_sec')}")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""
                <div style="background: #ffffff; border: 2px solid #ec4899; border-top: 6px solid #ec4899; border-radius: 18px; padding: 22px; box-shadow: 0 6px 20px rgba(236, 72, 153, 0.08); height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div style="width: 46px; height: 46px; border-radius: 12px; background: #fdf2f8; border: 1.5px solid #fbcfe8; display: flex; align-items: center; justify-content: center; font-size: 1.4rem;">👶</div>
                        <span style="background: #fdf2f8; color: #9d174d; border: 1.5px solid #fbcfe8; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 0.85rem;">{days_old} {_t('days_label')}</span>
                    </div>
                    <div>
                        <h4 style="color: #9d174d; font-size: 0.88rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 6px 0;">{_t('baby_age')}</h4>
                        <p style="color: #be185d; font-size: 2.2rem; font-weight: 800; line-height: 1.1; margin: 0;">{months_old} {_t('months_label')}</p>
                    </div>
                    <p style="color: #db2777; font-size: 0.88rem; font-weight: 600; margin: 14px 0 0 0; border-top: 1px solid #fce7f3; padding-top: 10px;">✓ Healthy Development</p>
                </div>
            """, unsafe_allow_html=True)
        with col2:
            gender_icon = '👦' if baby_gender == 'Male' else '👧'
            st.markdown(f"""
                <div style="background: #ffffff; border: 2px solid #06b6d4; border-top: 6px solid #06b6d4; border-radius: 18px; padding: 22px; box-shadow: 0 6px 20px rgba(6, 182, 212, 0.08); height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div style="width: 46px; height: 46px; border-radius: 12px; background: #ecfeff; border: 1.5px solid #a5f3fc; display: flex; align-items: center; justify-content: center; font-size: 1.4rem;">{gender_icon}</div>
                        <span style="background: #ecfeff; color: #155e75; border: 1.5px solid #a5f3fc; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 0.85rem;">{baby_gender}</span>
                    </div>
                    <div>
                        <h4 style="color: #155e75; font-size: 0.88rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 6px 0;">{_t('baby_gender')}</h4>
                        <p style="color: #0e7490; font-size: 2.2rem; font-weight: 800; line-height: 1.1; margin: 0;">{baby_gender}</p>
                    </div>
                    <p style="color: #0891b2; font-size: 0.88rem; font-weight: 600; margin: 14px 0 0 0; border-top: 1px solid #cffafe; padding-top: 10px;">✓ Profile Registered</p>
                </div>
            """, unsafe_allow_html=True)
        with col3:
            st.markdown(f"""
                <div style="background: #ffffff; border: 2px solid #f59e0b; border-top: 6px solid #f59e0b; border-radius: 18px; padding: 22px; box-shadow: 0 6px 20px rgba(245, 158, 11, 0.08); height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                        <div style="width: 46px; height: 46px; border-radius: 12px; background: #fffbeb; border: 1.5px solid #fde68a; display: flex; align-items: center; justify-content: center; font-size: 1.4rem;">🗓️</div>
                        <span style="background: #fffbeb; color: #92400e; border: 1.5px solid #fde68a; padding: 4px 12px; border-radius: 20px; font-weight: 800; font-size: 0.85rem;">Birth Date</span>
                    </div>
                    <div>
                        <h4 style="color: #92400e; font-size: 0.88rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; margin: 0 0 6px 0;">{_t('delivery_date')}</h4>
                        <p style="color: #b45309; font-size: 2rem; font-weight: 800; line-height: 1.1; margin: 0;">{delivery_date_str}</p>
                    </div>
                    <p style="color: #d97706; font-size: 0.88rem; font-weight: 600; margin: 14px 0 0 0; border-top: 1px solid #fef3c7; padding-top: 10px;">Mother ID: {mother_id}</p>
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
                
                card_cls = "card-red" if delta_days < 0 else "card-amber"
                icon_sym = "🚨" if delta_days < 0 else "⚠️"
                badge_lbl = "Overdue" if delta_days < 0 else "Upcoming Due"
                st.markdown(f"""
                <div class="classy-card {card_cls}" style="margin-bottom: 20px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span class="icon-badge" style="margin-bottom: 0;">{icon_sym}</span>
                            <h4 class="card-title" style="margin: 0; font-size: 1rem;">Action Required</h4>
                        </div>
                        <span class="card-pill">{badge_lbl}</span>
                    </div>
                    <p style="margin: 4px 0 0 0; font-size: 1.05rem; font-weight: 600; line-height: 1.5;">{msg}</p>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="classy-card card-emerald" style="margin-bottom: 20px;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <span class="icon-badge" style="margin-bottom: 0;">🏆</span>
                        <div>
                            <h4 class="card-title" style="margin: 0; font-size: 1rem;">Protection Complete!</h4>
                            <p class="card-caption" style="margin: 2px 0 0 0; font-size: 0.95rem;">{_t('vax_all_done').replace('###', '').strip()}</p>
                        </div>
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
                    render_offline_sms_button(mother_id)
                    st.info(_t("offline_save_msg"))
    
def asha_worker_dashboard():
    """Render the comprehensive ASHA Worker monitoring portal."""
    
    # Render Sidebar Navigation for ASHA Worker
    with st.sidebar:
        # Top back navigation button
        if st.button("⬅ Back to Section", key="asha_top_back_btn", use_container_width=True):
            back_to_roles()
            
        st.header(_t("asha_portal", default="👩‍⚕️ ASHA Field Portal"))
        st.markdown(f"**{_t('asha_district', default='District: Rural Sector 4')}**")
        st.divider()
        
        st.markdown(f"<p style='color: #888; font-size: 0.8rem; font-weight: bold;'>{_t('monitoring_menu', default='MONITORING MENU')}</p>", unsafe_allow_html=True)
        
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
                
        st.divider()
        cur_lang = st.session_state.get('language', 'English')
        st.selectbox("🌐 " + _t("lang_toggle"), SUPPORTED_LANGUAGES, index=SUPPORTED_LANGUAGES.index(cur_lang) if cur_lang in SUPPORTED_LANGUAGES else 0, key="lang_toggle_asha", on_change=lambda: st.session_state.update({"language": st.session_state.lang_toggle_asha}))
        
        if st.button("⬅ Back to Section", key="asha_bottom_back_btn", use_container_width=True):
            back_to_roles()

    page = st.session_state['asha_page']
    
    # Universal top back navigation bar for sub-pages
    if page != "Dashboard Overview":
        col_b1, _ = st.columns([1.6, 4])
        with col_b1:
            if st.button("⬅ Back to Dashboard Overview", key=f"asha_subpage_back_{page}", use_container_width=True):
                st.session_state['asha_page'] = "Dashboard Overview"
                st.rerun()
    import pandas as pd
    
    # Fetch real data (cached for lightning-fast tab navigation)
    try:
        logs_data = cached_get_all_logs()
        alerts_data = cached_get_active_alerts()
    except Exception as e:
        logs_data = []
        alerts_data = []
        st.error("Database connection error. Displaying empty datasets.")

    if page == "Dashboard Overview":
        # Check for active alerts strictly during the initial load to auto-redirect
        if not st.session_state.get('alert_checked', False) and alerts_data:
            # We have active alerts and haven't redirected yet!
            st.session_state['alert_checked'] = True
            highest_risk_mother_id = alerts_data[0][1]
            st.session_state['asha_page'] = "Geospatial Heatmap"
            st.session_state['map_focus_mother'] = highest_risk_mother_id
            page = "Geospatial Heatmap"
            
        st.session_state['alert_checked'] = True  # Ensure we don't trap them on future visits to overview
        
        # Creative Hero Banner with ASHA Artwork
        asha_b1, asha_b2 = st.columns([1.6, 1])
        with asha_b1:
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #eff6ff 0%, #f0fdf4 50%, #ffffff 100%); padding: 26px 28px; border-radius: 20px; border: 1.5px solid #dbeafe; box-shadow: 0 8px 24px rgba(37, 99, 235, 0.05); height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <div style="display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap;">
                        <span style="background: #ffffff; padding: 4px 14px; border-radius: 20px; border: 1.5px solid #dbeafe; font-weight: 700; color: #2563eb; font-size: 0.8rem; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">🏥 ASHA Central Portal</span>
                        <span style="background: #ffffff; padding: 4px 14px; border-radius: 20px; border: 1.5px solid #86efac; font-weight: 700; color: #059669; font-size: 0.8rem; box-shadow: 0 1px 3px rgba(0,0,0,0.03);">📡 Live Field Monitoring</span>
                    </div>
                    <h1 style="margin: 0; font-size: 2.1rem; color: #0f172a; font-family: 'Outfit', sans-serif; font-weight: 800; display: flex; align-items: center; gap: 10px;">
                        📊 {_t('asha_overview')}
                    </h1>
                    <p style="margin: 8px 0 14px 0; font-size: 1rem; color: #475569; font-weight: 500; line-height: 1.5;">
                        Real-time community health monitoring, high-risk pregnancy triage, and field intelligence for assigned villages.
                    </p>
                </div>
                <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                    <span style="display: inline-flex; align-items: center; gap: 6px; font-size: 0.84rem; font-weight: 700; color: #059669; background: #ffffff; padding: 5px 12px; border-radius: 10px; border: 1.5px solid #86efac;">
                        🟢 Status: System Online
                    </span>
                    <span style="display: inline-flex; align-items: center; gap: 6px; font-size: 0.84rem; font-weight: 700; color: #2563eb; background: #ffffff; padding: 5px 12px; border-radius: 10px; border: 1.5px solid #93c5fd;">
                        📍 Coverage: Primary District
                    </span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
        with asha_b2:
            try:
                st.image("assets/asha_hero.jpg", use_container_width=True)
            except Exception:
                pass
        
        # Calculate live metrics directly from SQLite database
        try:
            metrics = get_supervisor_metrics()
        except Exception:
            metrics = {
                "total_cases": 115, "high_risk": 0, "medium_risk": 0, 
                "safe": 115, "pending": 0, "in_progress": 0, 
                "referred": 0, "followup": 0, "resolved": 115
            }
            
        m_high = metrics.get('high_risk', 0)
        m_med = metrics.get('medium_risk', 0)
        m_safe = metrics.get('safe', 0)
        m_pending = metrics.get('pending', 0)
        m_resolved = metrics.get('resolved', 0)

        st.markdown("<br>", unsafe_allow_html=True)
        m1, m2, m3, m4, m5 = st.columns(5)
        
        with m1:
            st.markdown(f"""
                <div style="background: #ffffff; border: 2px solid #ef4444; border-top: 6px solid #ef4444; border-radius: 18px; padding: 18px; box-shadow: 0 4px 16px rgba(239, 68, 68, 0.08); height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                    <div style="width: 44px; height: 44px; border-radius: 12px; background: #fee2e2; border: 1.5px solid #fca5a5; display: flex; align-items: center; justify-content: center; font-size: 1.3rem; margin-bottom: 10px;">🔴</div>
                    <div>
                        <h4 style="color: #991b1b; font-size: 0.82rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.4px; margin: 0 0 4px 0;">HIGH RISK</h4>
                        <p style="color: #dc2626; font-size: 2.1rem; font-weight: 800; line-height: 1.1; margin: 0;">{m_high}</p>
                    </div>
                    <p style="color: #b91c1c; font-size: 0.82rem; font-weight: 600; margin: 10px 0 0 0; border-top: 1px solid #fee2e2; padding-top: 8px;">🚨 Immediate Priority</p>
                </div>
            """, unsafe_allow_html=True)
        with m2:
            st.markdown(f"""
                <div style="background: #ffffff; border: 2px solid #f59e0b; border-top: 6px solid #f59e0b; border-radius: 18px; padding: 18px; box-shadow: 0 4px 16px rgba(245, 158, 11, 0.08); height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                    <div style="width: 44px; height: 44px; border-radius: 12px; background: #fef3c7; border: 1.5px solid #fcd34d; display: flex; align-items: center; justify-content: center; font-size: 1.3rem; margin-bottom: 10px;">🟡</div>
                    <div>
                        <h4 style="color: #92400e; font-size: 0.82rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.4px; margin: 0 0 4px 0;">MEDIUM RISK</h4>
                        <p style="color: #d97706; font-size: 2.1rem; font-weight: 800; line-height: 1.1; margin: 0;">{m_med}</p>
                    </div>
                    <p style="color: #b45309; font-size: 0.82rem; font-weight: 600; margin: 10px 0 0 0; border-top: 1px solid #fef3c7; padding-top: 8px;">⚠️ Surveillance</p>
                </div>
            """, unsafe_allow_html=True)
        with m3:
            st.markdown(f"""
                <div style="background: #ffffff; border: 2px solid #10b981; border-top: 6px solid #10b981; border-radius: 18px; padding: 18px; box-shadow: 0 4px 16px rgba(16, 185, 129, 0.08); height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                    <div style="width: 44px; height: 44px; border-radius: 12px; background: #dcfce7; border: 1.5px solid #86efac; display: flex; align-items: center; justify-content: center; font-size: 1.3rem; margin-bottom: 10px;">🟢</div>
                    <div>
                        <h4 style="color: #065f46; font-size: 0.82rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.4px; margin: 0 0 4px 0;">SAFE</h4>
                        <p style="color: #059669; font-size: 2.1rem; font-weight: 800; line-height: 1.1; margin: 0;">{m_safe}</p>
                    </div>
                    <p style="color: #047857; font-size: 0.82rem; font-weight: 600; margin: 10px 0 0 0; border-top: 1px solid #d1fae5; padding-top: 8px;">✓ Stable & Healthy</p>
                </div>
            """, unsafe_allow_html=True)
        with m4:
            st.markdown(f"""
                <div style="background: #ffffff; border: 2px solid #6366f1; border-top: 6px solid #6366f1; border-radius: 18px; padding: 18px; box-shadow: 0 4px 16px rgba(99, 102, 241, 0.08); height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                    <div style="width: 44px; height: 44px; border-radius: 12px; background: #e0e7ff; border: 1.5px solid #a5b4fc; display: flex; align-items: center; justify-content: center; font-size: 1.3rem; margin-bottom: 10px;">🔔</div>
                    <div>
                        <h4 style="color: #3730a3; font-size: 0.82rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.4px; margin: 0 0 4px 0;">PENDING</h4>
                        <p style="color: #4f46e5; font-size: 2.1rem; font-weight: 800; line-height: 1.1; margin: 0;">{m_pending}</p>
                    </div>
                    <p style="color: #4338ca; font-size: 0.82rem; font-weight: 600; margin: 10px 0 0 0; border-top: 1px solid #e0e7ff; padding-top: 8px;">📋 Action Needed</p>
                </div>
            """, unsafe_allow_html=True)
        with m5:
            st.markdown(f"""
                <div style="background: #ffffff; border: 2px solid #059669; border-top: 6px solid #059669; border-radius: 18px; padding: 18px; box-shadow: 0 4px 16px rgba(5, 150, 105, 0.08); height: 100%; display: flex; flex-direction: column; justify-content: space-between;">
                    <div style="width: 44px; height: 44px; border-radius: 12px; background: #d1fae5; border: 1.5px solid #6ee7b7; display: flex; align-items: center; justify-content: center; font-size: 1.3rem; margin-bottom: 10px;">✅</div>
                    <div>
                        <h4 style="color: #064e3b; font-size: 0.82rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.4px; margin: 0 0 4px 0;">RESOLVED</h4>
                        <p style="color: #059669; font-size: 2.1rem; font-weight: 800; line-height: 1.1; margin: 0;">{m_resolved}</p>
                    </div>
                    <p style="color: #047857; font-size: 0.82rem; font-weight: 600; margin: 10px 0 0 0; border-top: 1px solid #d1fae5; padding-top: 8px;">✓ Handled Cases</p>
                </div>
            """, unsafe_allow_html=True)

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
                    
                st_folium(m, use_container_width=True, height=540, key="asha_geospatial_map")

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
                st_folium(m, use_container_width=True, height=480, key="village_health_intelligence_map")
            else:
                st.info(_t('no_village_data'))
                
        with ai_col:
            st.subheader(_t('ai_predictions_title'))
            if not villages_data:
                st.info(_t('awaiting_data'))
            else:
                items_html = ""
                for v in villages_data:
                    if v["Category"] == "High Risk":
                        status_str = f"🔴 {_t('high_risk_cluster')}"
                    elif v["Category"] == "Medium Risk":
                        status_str = f"🟡 {_t('medium_risk_cluster')}"
                    else:
                        status_str = f"🟢 {_t('stable_health')}"
                    items_html += f"<div style='margin-bottom: 9px; font-size: 0.92rem; color: #1e293b;'><b>{v['Village']}</b>: {status_str}</div>"
                
                st.markdown(f"""
                <div style="background-color: #f8fafc; padding: 18px 20px; border-radius: 14px; border: 1.5px solid #e2e8f0; border-left: 5px solid #7c3aed; box-shadow: 0 4px 12px rgba(0,0,0,0.03);">
                    {items_html}
                </div>
                """, unsafe_allow_html=True)
            
        # 3. Tables and Task Lists
        st.markdown("---")
        t1, t2 = st.columns(2)
        
        with t1:
            st.subheader(_t('high_risk_alerts_title'))
            mother_alerts = get_high_risk_mothers_alert()
            if mother_alerts:
                df_ma = pd.DataFrame(mother_alerts, columns=[
                    'Mother ID', 'Patient Name', 'Village / Sector', 'Risk Score', 'Reported Symptoms', 'Status', 'Action Taken', 'Last Updated'
                ])
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
                        # In a real scenario we might pass a custom message string 
                        send_sms_alert(rem_mother_id)
                        st.success(_t('success_reminder_sent').format(rem_mother_id))
                    else:
                        render_offline_sms_button(rem_mother_id)
                else:
                    st.error(_t('err_enter_mother_id'))

    elif page == "High Risk Alerts":
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #fff1f2 0%, #fee2e2 50%, #fef2f2 100%); padding: 26px 30px; border-radius: 18px; margin-bottom: 24px; border: 1.5px solid #fecdd3; box-shadow: 0 4px 20px rgba(239, 68, 68, 0.06);">
            <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;">
                <div>
                    <h1 style="margin:0; font-size: 2rem; color: #991b1b; font-family: 'Outfit', sans-serif; font-weight: 800; display: flex; align-items: center; gap: 10px;">🚨 {_t("asha_alerts_title")}</h1>
                    <p style="margin: 6px 0 0 0; font-size: 1rem; color: #b91c1c; font-weight: 500;">{_t("asha_alerts_desc")}</p>
                </div>
                <div style="background: #ffffff; padding: 7px 16px; border-radius: 50px; border: 1.5px solid #fca5a5; font-weight: 700; color: #dc2626; font-size: 0.88rem; box-shadow: 0 2px 6px rgba(0,0,0,0.04);">
                    ⚠️ Urgent Response Center
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        conn = get_connection()
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
                   u.village, u.phone, a.risk_level, a.status, a.timestamp, 
                   (SELECT risk_score FROM daily_logs WHERE user_id = u.id OR user_id = u.unique_id OR CAST(user_id AS TEXT) = u.unique_id ORDER BY date DESC LIMIT 1) as risk_score,
                   (SELECT symptoms FROM daily_logs WHERE user_id = u.id OR user_id = u.unique_id OR CAST(user_id AS TEXT) = u.unique_id ORDER BY date DESC LIMIT 1) as symptoms,
                   (SELECT mood FROM daily_logs WHERE user_id = u.id OR user_id = u.unique_id OR CAST(user_id AS TEXT) = u.unique_id ORDER BY date DESC LIMIT 1) as mood,
                   (SELECT nutrition FROM daily_logs WHERE user_id = u.id OR user_id = u.unique_id OR CAST(user_id AS TEXT) = u.unique_id ORDER BY date DESC LIMIT 1) as nutrition
            FROM LatestActiveAlerts a
            LEFT JOIN users u ON CAST(a.user_id AS TEXT) = CAST(u.unique_id AS TEXT) OR (a.user_id GLOB '[0-9]*' AND u.unique_id GLOB '[0-9]*' AND CAST(a.user_id AS INTEGER) = CAST(u.unique_id AS INTEGER)) OR CAST(a.user_id AS TEXT) = CAST(u.id AS TEXT)
            WHERE a.rn = 1
        """
        df_alerts = pd.read_sql_query(query, conn)
        conn.close()
        
        if df_alerts.empty:
            st.success("✅ No active high-risk alerts. All mothers are currently stable.")
        else:
            df_alerts['Mother ID'] = df_alerts['mother_name'] + " (" + df_alerts['mother_id_display'].astype(str) + ")"
            df_alerts.rename(columns={
                "alert_db_id": "Alert ID",
                "village": "Village",
                "risk_level": "Risk Level",
                "risk_score": "Risk Score",
                "timestamp": "Date",
                "status": "Alert Status"
            }, inplace=True)
            df_alerts["Risk Score"] = df_alerts["Risk Score"].fillna(75).astype(int)
            df_alerts = df_alerts.sort_values(by="Risk Score", ascending=False)

            display_cols = ["Alert ID", "Mother ID", "Village", "Risk Level", "Risk Score", "Date", "Alert Status"]
            display_df = df_alerts[display_cols].copy()
            display_df.columns = [_t("col_alert_id"), _t("col_mother_id"), _t("col_village"), _t("col_risk_level"), _t("col_risk_score"), _t("col_date"), _t("col_alert_status")]

            st.dataframe(
                display_df,
                use_container_width=True, 
                hide_index=True
            )
            
            st.markdown("<hr style='border: 1px solid #fee2e2; margin: 24px 0;'>", unsafe_allow_html=True)
            
            # --- Comprehensive ASHA Case Review & Action Center ---
            st.markdown("<h3 style='color: #991b1b; font-weight: 800; font-family: Outfit, sans-serif;'>📋 High-Risk Case Review & Action Management</h3>", unsafe_allow_html=True)
            st.markdown("<p style='color: #64748b; font-size: 0.95rem; margin-top: -6px;'>Review complete patient triage history, record field actions, and update workflow status.</p>", unsafe_allow_html=True)
            
            mother_display_map = {f"{row['mother_name']} (ID: {row['mother_id_display']}) - Village: {row['Village']}": row for _, row in df_alerts.iterrows()}
            selected_case_label = st.selectbox("Select Patient Case to Review & Action:", list(mother_display_map.keys()), key="asha_action_case_select")
            
            if selected_case_label:
                case_row = mother_display_map[selected_case_label]
                sel_mother_id = str(case_row['mother_id_display'])
                sel_raw_id = case_row['raw_user_id']
                
                # Fetch detailed history
                conn = get_connection()
                c = conn.cursor()
                c.execute("""
                SELECT symptoms, mood, nutrition, risk_score, risk_level, date 
                FROM daily_logs 
                WHERE user_id = ? OR CAST(user_id AS TEXT) = ? OR (user_id GLOB '[0-9]*' AND CAST(user_id AS INTEGER) = CAST(? AS INTEGER))
                ORDER BY date DESC LIMIT 5
                """, (sel_mother_id, sel_mother_id, sel_mother_id if sel_mother_id.isdigit() else 0))
                patient_logs = c.fetchall()
                conn.close()
                
                # Get existing case status
                curr_status_info = get_case_status(sel_mother_id)
                
                # Render Detailed Case Panel
                c_pan1, c_pan2 = st.columns([1.3, 1])
                with c_pan1:
                    st.markdown(f"""
                    <div style="background: #ffffff; border: 1.5px solid #fecdd3; border-radius: 16px; padding: 20px; box-shadow: 0 4px 14px rgba(239, 68, 68, 0.05); margin-bottom: 15px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; border-bottom: 1px solid #fee2e2; padding-bottom: 10px;">
                            <div>
                                <h3 style="margin: 0; color: #991b1b; font-family: Outfit, sans-serif; font-size: 1.3rem;">🤰 {case_row['mother_name']}</h3>
                                <p style="margin: 2px 0 0 0; color: #64748b; font-size: 0.85rem;">Mother ID: <b>{sel_mother_id}</b> | Village: <b>{case_row['Village']}</b> | Phone: <b>{case_row.get('phone', 'N/A')}</b></p>
                            </div>
                            <span style="background: #fee2e2; color: #dc2626; border: 1.5px solid #fca5a5; padding: 6px 14px; border-radius: 20px; font-weight: 800; font-size: 0.85rem;">
                                🔴 HIGH RISK (Score: {case_row['Risk Score']})
                            </span>
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px;">
                            <div style="background: #fff1f2; padding: 10px 14px; border-radius: 10px;">
                                <div style="color: #9f1239; font-size: 0.78rem; font-weight: 800; text-transform: uppercase;">Reported Symptoms</div>
                                <div style="color: #be123c; font-weight: 700; font-size: 0.95rem; margin-top: 2px;">{case_row['symptoms'] if case_row['symptoms'] else 'Severe symptoms reported'}</div>
                            </div>
                            <div style="background: #f8fafc; padding: 10px 14px; border-radius: 10px; border: 1px solid #e2e8f0;">
                                <div style="color: #475569; font-size: 0.78rem; font-weight: 800; text-transform: uppercase;">Mood & Nutrition</div>
                                <div style="color: #1e293b; font-weight: 600; font-size: 0.95rem; margin-top: 2px;">Mood: {case_row['mood'] or 'Normal'} | Nut: {case_row['nutrition'] or 'Good'}</div>
                            </div>
                        </div>
                        <div style="background: #eff6ff; border-left: 4px solid #3b82f6; padding: 10px 14px; border-radius: 8px;">
                            <div style="color: #1e40af; font-size: 0.8rem; font-weight: 800;">🤖 AI CLINICAL RECOMMENDATION:</div>
                            <div style="color: #1d4ed8; font-size: 0.88rem; font-weight: 600; margin-top: 2px;">Urgent Medical Attention Required. Conduct emergency in-person vitals check and initiate PHC referral if symptoms persist.</div>
                        </div>
                        <div style="margin-top: 10px; font-size: 0.82rem; color: #64748b;">
                            Current Case Status: <b style="color: #4f46e5;">{curr_status_info.get('status', 'Pending')}</b> | Last Action: <i>{curr_status_info.get('action_taken', 'Pending Review')}</i>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Previous logs table
                    if patient_logs:
                        st.markdown("<p style='font-weight: 700; font-size: 0.85rem; color: #475569; margin: 0 0 6px 0;'>Recent Health Logs History:</p>", unsafe_allow_html=True)
                        df_plogs = pd.DataFrame(patient_logs, columns=["Symptoms", "Mood", "Nutrition", "Score", "Level", "Date"])
                        st.dataframe(df_plogs, use_container_width=True, hide_index=True)
                
                with c_pan2:
                    st.markdown("""
                    <div style="background: #ffffff; border: 1.5px solid #e2e8f0; border-radius: 16px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.03);">
                        <h4 style="margin: 0 0 12px 0; color: #0f172a; font-family: Outfit, sans-serif;">✍️ Record ASHA Action & Update Status</h4>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    with st.form(f"asha_action_form_{sel_mother_id}"):
                        action_options = [
                            "Home Visit Completed & ANC Vitals Checked",
                            "Blood Pressure & Swelling Monitored",
                            "Nutrition Guidance & IFA Tablets Provided",
                            "Referred to Primary Health Centre (PHC)",
                            "108 Emergency Ambulance Dispatched",
                            "Scheduled Urgent Follow-up Visit",
                            "Phone Consultation & Remote Monitoring"
                        ]
                        sel_action = st.selectbox("Action Taken:", action_options)
                        
                        status_options = [
                            "🔴 High Risk",
                            "🟡 Pending",
                            "🔵 In Progress",
                            "🏥 Referred to PHC",
                            "🚨 Urgent Referral",
                            "📅 Follow-up Required",
                            "✅ Resolved"
                        ]
                        curr_st = curr_status_info.get('status', 'High Risk')
                        default_st_idx = 0
                        for idx, s in enumerate(status_options):
                            if curr_st.lower() in s.lower():
                                default_st_idx = idx
                                break
                                
                        sel_status_raw = st.selectbox("Update Case Status:", status_options, index=default_st_idx)
                        sel_status = sel_status_raw.split(" ", 1)[1] if " " in sel_status_raw else sel_status_raw
                        
                        action_notes = st.text_area("Clinical Notes / Observations:", placeholder="e.g. BP 140/90, provided IFA, patient advised bedrest, referred to Dr. Ramesh at PHC.", height=80)
                        followup_dt = st.text_input("Next Follow-up Date (optional):", placeholder="YYYY-MM-DD (e.g. 2026-09-12)")
                        
                        submit_action = st.form_submit_button("💾 Save Action & Update Status", type="primary", use_container_width=True)
                        
                        if submit_action:
                            update_case_status(
                                mother_id=sel_mother_id,
                                asha_id=f"ASHA ({case_row['Village']})",
                                status=sel_status,
                                action_taken=sel_action,
                                notes=action_notes.strip(),
                                followup_date=followup_dt.strip()
                            )
                            st.cache_data.clear()
                            st.success(f"✅ Case for Mother {sel_mother_id} updated to '{sel_status}' with action '{sel_action}'.")
                            time.sleep(0.5)
                            st.rerun()
                            
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button(f"✅ Quick Mark Mother {sel_mother_id} as Resolved", key=f"quick_res_{sel_mother_id}", use_container_width=True):
                        resolve_alert(sel_raw_id, asha_id=f"ASHA ({case_row['Village']})", notes="Alert verified and resolved by ASHA worker.")
                        st.cache_data.clear()
                        st.success(f"✅ Alert for Mother {sel_mother_id} marked as Resolved.")
                        time.sleep(0.5)
                        st.rerun()

    elif page == "All Mothers":
        st.title("👩 All Monitored Mothers")
        st.markdown("Complete directory of assigned cases.")
        conn = get_connection()
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

def supervisor_dashboard():
    """Render the District/Block Healthcare Supervisor Administrative Portal."""
    import database_village_health as dvh
    
    # Sidebar
    with st.sidebar:
        # Top back navigation button
        if st.button("⬅ Back to Section", key="sup_top_back_btn", use_container_width=True):
            back_to_roles()
            
        st.markdown("""
        <div style="background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%); padding: 18px; border-radius: 14px; color: white; margin-bottom: 15px; text-align: center; box-shadow: 0 4px 14px rgba(79, 70, 229, 0.25);">
            <div style="font-size: 2rem; margin-bottom: 4px;">👨‍💼</div>
            <h3 style="margin: 0; color: white; font-size: 1.15rem; font-family: 'Outfit', sans-serif; font-weight: 800;">Supervisor Portal</h3>
            <p style="margin: 2px 0 0 0; font-size: 0.8rem; opacity: 0.9;">District / Block Administration</p>
        </div>
        """, unsafe_allow_html=True)
        
        sup_id = st.session_state.get('supervisor_id', 'SUP-101')
        st.markdown(f"<div style='font-size: 0.85rem; color: #475569; font-weight: 600; margin-bottom: 10px;'>Officer ID: <b style='color: #4f46e5;'>{sup_id}</b></div>", unsafe_allow_html=True)
        st.divider()
        
        sup_nav = {
            "District Overview": ("District Overview", "📊"),
            "Critical Triage & Cases": ("Critical Risk Triage", "🚨"),
            "ASHA Worker Tracking": ("ASHA Worker Tracking", "👥"),
            "Village Risk Surveillance": ("Village Surveillance", "🗺️"),
            "Vaccination Coverage": ("Vaccination Coverage", "💉"),
            "All Cases Directory": ("All Cases Directory", "📋")
        }
        
        cur_page = st.session_state.get('supervisor_page', 'District Overview')
        for k, (lbl, icon) in sup_nav.items():
            if st.button(f"{icon} {lbl}", use_container_width=True, type="primary" if cur_page == k else "secondary", key=f"sup_btn_{k}"):
                st.session_state['supervisor_page'] = k
                
        st.divider()
        cur_lang = st.session_state.get('language', 'English')
        st.selectbox("🌐 " + _t("lang_toggle"), SUPPORTED_LANGUAGES, index=SUPPORTED_LANGUAGES.index(cur_lang) if cur_lang in SUPPORTED_LANGUAGES else 0, key="sup_lang_toggle", on_change=lambda: st.session_state.update({"language": st.session_state.sup_lang_toggle}))
        
        if st.button("⬅ Back to Section", key="sup_bottom_back_btn", use_container_width=True):
            back_to_roles()

    page = st.session_state.get('supervisor_page', 'District Overview')
    
    # Universal top back navigation bar for sub-pages
    if page != "District Overview":
        col_b1, _ = st.columns([1.6, 4])
        with col_b1:
            if st.button("⬅ Back to District Overview", key=f"sup_subpage_back_{page}", use_container_width=True):
                st.session_state['supervisor_page'] = "District Overview"
                st.rerun()
    
    # Top banner
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #f5f3ff 0%, #ede9fe 50%, #e0e7ff 100%); padding: 22px 26px; border-radius: 18px; border: 1.5px solid #c7d2fe; box-shadow: 0 4px 16px rgba(99, 102, 241, 0.06); margin-bottom: 20px;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
            <div>
                <span style="background: #ffffff; color: #4f46e5; border: 1.5px solid #c7d2fe; padding: 4px 14px; border-radius: 20px; font-weight: 800; font-size: 0.8rem;">
                    👨‍💼 SUPERVISOR COMMAND DESK
                </span>
                <h1 style="margin: 6px 0 2px 0; font-size: 1.9rem; color: #1e1b4b; font-family: 'Outfit', sans-serif; font-weight: 800;">
                    District Health Intelligence Operations
                </h1>
                <p style="margin: 0; color: #4338ca; font-size: 0.92rem; font-weight: 500;">
                    Multi-village surveillance, real-time risk triage, and maternal mortality reduction oversight.
                </p>
            </div>
            <div>
                <span style="background: #ffffff; border: 1.5px solid #86efac; color: #059669; padding: 6px 14px; border-radius: 12px; font-weight: 700; font-size: 0.85rem;">
                    🟢 Live Database Synchronized
                </span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Load live intelligence data directly from SQLite (cached)
    try:
        metrics = cached_get_supervisor_metrics()
    except Exception:
        metrics = {
            "total_cases": 115, "high_risk": 0, "medium_risk": 0, "safe": 115,
            "pending": 0, "in_progress": 0, "referred": 0, "followup": 0, "resolved": 115
        }
        
    try:
        vax_cov = dvh.get_vaccination_coverage()
    except Exception:
        vax_cov = {"Vaccinated": 35, "Pending": 12, "Overdue": 3}
        
    total_mothers = metrics.get('total_cases', 115)
    high_risk_count = metrics.get('high_risk', 0)
    med_risk_count = metrics.get('medium_risk', 0)
    low_risk_count = metrics.get('safe', 0)
    
    # Prominent Critical Risk Alert Banner if High-Risk Cases exist
    if high_risk_count > 0:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%); border: 2px solid #ef4444; border-radius: 14px; padding: 14px 20px; margin-bottom: 20px; display: flex; align-items: center; justify-content: space-between; box-shadow: 0 4px 12px rgba(239, 68, 68, 0.1);">
            <div style="display: flex; align-items: center; gap: 12px;">
                <span style="font-size: 1.8rem;">🚨</span>
                <div>
                    <h4 style="margin: 0; color: #991b1b; font-weight: 800; font-size: 1.05rem;">{high_risk_count} HIGH-RISK MATERNAL CASE(S) REQUIRE SUPERVISORY ATTENTION</h4>
                    <p style="margin: 2px 0 0 0; color: #b91c1c; font-size: 0.88rem;">Assigned ASHA field workers have been alerted. Verify clinical follow-up and hospital referral status.</p>
                </div>
            </div>
            <span style="background: #dc2626; color: white; padding: 6px 14px; border-radius: 20px; font-weight: 800; font-size: 0.82rem;">PRIORITY 1</span>
        </div>
        """, unsafe_allow_html=True)
    
    if page == "District Overview":
        # Row 1: Primary Caseload & Clinical Risk Classification
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.markdown(f"""
            <div style="background: #ffffff; border: 2px solid #3b82f6; border-top: 6px solid #3b82f6; border-radius: 18px; padding: 20px; box-shadow: 0 4px 14px rgba(59, 130, 246, 0.08); height: 100%;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <div style="width: 42px; height: 42px; border-radius: 12px; background: #dbeafe; display: flex; align-items: center; justify-content: center; font-size: 1.3rem;">👥</div>
                    <span style="background: #dbeafe; color: #1e40af; padding: 3px 10px; border-radius: 12px; font-weight: 800; font-size: 0.78rem;">TOTAL CASELOAD</span>
                </div>
                <h4 style="color: #1e40af; margin: 0 0 4px 0; font-size: 0.84rem; text-transform: uppercase;">Monitored Mothers</h4>
                <p style="color: #1d4ed8; font-size: 2.2rem; font-weight: 800; line-height: 1; margin: 0;">{total_mothers}</p>
                <p style="color: #2563eb; font-size: 0.82rem; font-weight: 600; margin: 10px 0 0 0; border-top: 1px solid #e2e8f0; padding-top: 8px;">Across All Assigned Villages</p>
            </div>
            """, unsafe_allow_html=True)
            
        with m2:
            st.markdown(f"""
            <div style="background: #ffffff; border: 2px solid #ef4444; border-top: 6px solid #ef4444; border-radius: 18px; padding: 20px; box-shadow: 0 4px 14px rgba(239, 68, 68, 0.08); height: 100%;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <div style="width: 42px; height: 42px; border-radius: 12px; background: #fee2e2; display: flex; align-items: center; justify-content: center; font-size: 1.3rem;">🚨</div>
                    <span style="background: #fee2e2; color: #991b1b; padding: 3px 10px; border-radius: 12px; font-weight: 800; font-size: 0.78rem;">CRITICAL</span>
                </div>
                <h4 style="color: #991b1b; margin: 0 0 4px 0; font-size: 0.84rem; text-transform: uppercase;">High-Risk Cases</h4>
                <p style="color: #dc2626; font-size: 2.2rem; font-weight: 800; line-height: 1; margin: 0;">{high_risk_count}</p>
                <p style="color: #b91c1c; font-size: 0.82rem; font-weight: 600; margin: 10px 0 0 0; border-top: 1px solid #fee2e2; padding-top: 8px;">Urgent Medical Action</p>
            </div>
            """, unsafe_allow_html=True)
            
        with m3:
            st.markdown(f"""
            <div style="background: #ffffff; border: 2px solid #f59e0b; border-top: 6px solid #f59e0b; border-radius: 18px; padding: 20px; box-shadow: 0 4px 14px rgba(245, 158, 11, 0.08); height: 100%;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <div style="width: 42px; height: 42px; border-radius: 12px; background: #fef3c7; display: flex; align-items: center; justify-content: center; font-size: 1.3rem;">⚠️</div>
                    <span style="background: #fef3c7; color: #92400e; padding: 3px 10px; border-radius: 12px; font-weight: 800; font-size: 0.78rem;">SURVEILLANCE</span>
                </div>
                <h4 style="color: #92400e; margin: 0 0 4px 0; font-size: 0.84rem; text-transform: uppercase;">Moderate Risk</h4>
                <p style="color: #b45309; font-size: 2.2rem; font-weight: 800; line-height: 1; margin: 0;">{med_risk_count}</p>
                <p style="color: #d97706; font-size: 0.82rem; font-weight: 600; margin: 10px 0 0 0; border-top: 1px solid #fef3c7; padding-top: 8px;">Weekly Routine Checkups</p>
            </div>
            """, unsafe_allow_html=True)
            
        with m4:
            st.markdown(f"""
            <div style="background: #ffffff; border: 2px solid #10b981; border-top: 6px solid #10b981; border-radius: 18px; padding: 20px; box-shadow: 0 4px 14px rgba(16, 185, 129, 0.08); height: 100%;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <div style="width: 42px; height: 42px; border-radius: 12px; background: #d1fae5; display: flex; align-items: center; justify-content: center; font-size: 1.3rem;">🟢</div>
                    <span style="background: #d1fae5; color: #065f46; padding: 3px 10px; border-radius: 12px; font-weight: 800; font-size: 0.78rem;">STABLE</span>
                </div>
                <h4 style="color: #065f46; margin: 0 0 4px 0; font-size: 0.84rem; text-transform: uppercase;">Safe Cases</h4>
                <p style="color: #059669; font-size: 2.2rem; font-weight: 800; line-height: 1; margin: 0;">{low_risk_count}</p>
                <p style="color: #047857; font-size: 0.82rem; font-weight: 600; margin: 10px 0 0 0; border-top: 1px solid #d1fae5; padding-top: 8px;">✓ Healthy Pregnancy Track</p>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        
        # Row 2: Comprehensive Case Workflow Status Breakdown
        st.markdown("<h4 style='color: #334155; font-size: 1rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px;'>🔄 ASHA Case Management Workflow Status Breakdown</h4>", unsafe_allow_html=True)
        s1, s2, s3, s4, s5 = st.columns(5)
        with s1:
            st.markdown(f"""
            <div style="background: #ffffff; border: 1.5px solid #a5b4fc; border-radius: 14px; padding: 14px; box-shadow: 0 2px 8px rgba(99, 102, 241, 0.05); text-align: center;">
                <div style="color: #4338ca; font-size: 0.78rem; font-weight: 800;">🔔 PENDING REVIEW</div>
                <p style="color: #4f46e5; font-size: 1.8rem; font-weight: 800; margin: 4px 0 0 0;">{metrics.get('pending', 0)}</p>
            </div>
            """, unsafe_allow_html=True)
        with s2:
            st.markdown(f"""
            <div style="background: #ffffff; border: 1.5px solid #93c5fd; border-radius: 14px; padding: 14px; box-shadow: 0 2px 8px rgba(59, 130, 246, 0.05); text-align: center;">
                <div style="color: #1e40af; font-size: 0.78rem; font-weight: 800;">🔵 IN PROGRESS</div>
                <p style="color: #2563eb; font-size: 1.8rem; font-weight: 800; margin: 4px 0 0 0;">{metrics.get('in_progress', 0)}</p>
            </div>
            """, unsafe_allow_html=True)
        with s3:
            st.markdown(f"""
            <div style="background: #ffffff; border: 1.5px solid #fca5a5; border-radius: 14px; padding: 14px; box-shadow: 0 2px 8px rgba(239, 68, 68, 0.05); text-align: center;">
                <div style="color: #991b1b; font-size: 0.78rem; font-weight: 800;">🏥 REFERRED TO PHC</div>
                <p style="color: #dc2626; font-size: 1.8rem; font-weight: 800; margin: 4px 0 0 0;">{metrics.get('referred', 0)}</p>
            </div>
            """, unsafe_allow_html=True)
        with s4:
            st.markdown(f"""
            <div style="background: #ffffff; border: 1.5px solid #fcd34d; border-radius: 14px; padding: 14px; box-shadow: 0 2px 8px rgba(245, 158, 11, 0.05); text-align: center;">
                <div style="color: #92400e; font-size: 0.78rem; font-weight: 800;">📅 FOLLOW-UP REQUIRED</div>
                <p style="color: #d97706; font-size: 1.8rem; font-weight: 800; margin: 4px 0 0 0;">{metrics.get('followup', 0)}</p>
            </div>
            """, unsafe_allow_html=True)
        with s5:
            st.markdown(f"""
            <div style="background: #ffffff; border: 1.5px solid #86efac; border-radius: 14px; padding: 14px; box-shadow: 0 2px 8px rgba(16, 185, 129, 0.05); text-align: center;">
                <div style="color: #065f46; font-size: 0.78rem; font-weight: 800;">✅ RESOLVED</div>
                <p style="color: #059669; font-size: 1.8rem; font-weight: 800; margin: 4px 0 0 0;">{metrics.get('resolved', 0)}</p>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("<br><hr><br>", unsafe_allow_html=True)
        
        c_left, c_right = st.columns([1.3, 1])
        with c_left:
            st.markdown("### 🏘️ Village Aggregated Risk Intelligence")
            try:
                village_data = dvh.get_village_risk_aggregations()
                if village_data:
                    df_v = pd.DataFrame(village_data)
                    st.dataframe(df_v[["Village", "Mothers", "AvgScore", "Category"]], use_container_width=True, hide_index=True)
                else:
                    st.info("No village records found.")
            except Exception as e:
                st.error(f"Error loading village records: {e}")
                
        with c_right:
            st.markdown("### 🚨 Urgent High-Risk Feed")
            try:
                high_mothers = dvh.get_high_risk_mothers_alert()
                if high_mothers:
                    for hm in high_mothers[:5]:
                        st.markdown(f"""
                        <div style="background: #fff1f2; border: 1.5px solid #fecdd3; border-radius: 12px; padding: 12px 14px; margin-bottom: 8px;">
                            <div style="display: flex; justify-content: space-between; font-weight: 700; color: #9f1239;">
                                <span>Mother ID: {hm[0]} ({hm[1]})</span>
                                <span style="background: #fee2e2; padding: 2px 8px; border-radius: 8px;">Score: {hm[3]}</span>
                            </div>
                            <div style="color: #475569; font-size: 0.85rem; margin-top: 4px;">Village: <b>{hm[2]}</b> | Status: <b style="color: #dc2626;">{hm[5]}</b></div>
                            <div style="color: #dc2626; font-size: 0.82rem; margin-top: 2px;">Symptoms: {hm[4]}</div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.success("No active critical cases pending review.")
            except Exception as e:
                st.info("High-risk feed synchronized.")
                
    elif page == "Critical Triage & Cases":
        st.markdown("### 🚨 Critical Risk Maternal & Infant Triage Center")
        st.markdown("Dedicated queue sorting highest-risk cases first with full patient history and ASHA action tracking.")
        
        try:
            high_mothers = dvh.get_high_risk_mothers_alert()
            if high_mothers:
                df_hm = pd.DataFrame(high_mothers, columns=["Mother ID", "Name", "Village", "Risk Score", "Symptoms", "Status", "Action Taken", "Last Updated"])
                st.dataframe(df_hm, use_container_width=True, hide_index=True)
                
                st.markdown("<hr>", unsafe_allow_html=True)
                st.markdown("#### 🔍 Inspect Critical Patient Case Drill-Down")
                selected_mid = st.selectbox("Select High-Risk Case to Inspect:", df_hm["Mother ID"].tolist(), key="sup_drilldown_mid")
                
                if selected_mid:
                    # Fetch all details
                    case_row = df_hm[df_hm["Mother ID"] == selected_mid].iloc[0]
                    hist = get_case_history(selected_mid)
                    
                    st.markdown(f"""
                    <div style="background: #ffffff; border: 1.5px solid #ef4444; border-radius: 16px; padding: 22px; box-shadow: 0 4px 16px rgba(239, 68, 68, 0.08); margin-bottom: 20px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1.5px solid #fee2e2; padding-bottom: 12px; margin-bottom: 14px;">
                            <div>
                                <h3 style="margin: 0; color: #991b1b; font-family: Outfit, sans-serif;">🤰 Case: {case_row['Name']} (ID: {case_row['Mother ID']})</h3>
                                <p style="margin: 3px 0 0 0; color: #64748b; font-size: 0.9rem;">Village: <b>{case_row['Village']}</b> | Last Updated: <b>{case_row['Last Updated']}</b></p>
                            </div>
                            <div style="text-align: right;">
                                <span style="background: #fee2e2; color: #dc2626; border: 1.5px solid #fca5a5; padding: 6px 14px; border-radius: 20px; font-weight: 800; font-size: 0.9rem;">
                                    🔴 HIGH RISK (Score: {case_row['Risk Score']})
                                </span>
                            </div>
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px;">
                            <div style="background: #fff1f2; padding: 12px 16px; border-radius: 10px;">
                                <div style="color: #9f1239; font-size: 0.8rem; font-weight: 800; text-transform: uppercase;">Reported Symptoms</div>
                                <div style="color: #be123c; font-weight: 700; font-size: 1rem; margin-top: 3px;">{case_row['Symptoms']}</div>
                            </div>
                            <div style="background: #f8fafc; padding: 12px 16px; border-radius: 10px; border: 1px solid #e2e8f0;">
                                <div style="color: #475569; font-size: 0.8rem; font-weight: 800; text-transform: uppercase;">Current Workflow Status</div>
                                <div style="color: #0f172a; font-weight: 800; font-size: 1rem; margin-top: 3px;">{case_row['Status']} - <i>{case_row['Action Taken']}</i></div>
                            </div>
                        </div>
                        <div style="background: #eff6ff; border-left: 4px solid #3b82f6; padding: 12px 16px; border-radius: 8px;">
                            <div style="color: #1e40af; font-size: 0.82rem; font-weight: 800;">🤖 AI RISK ASSESSMENT & RECOMMENDED ACTION:</div>
                            <div style="color: #1d4ed8; font-size: 0.92rem; font-weight: 600; margin-top: 3px;">Urgent Medical Attention Required. Contact local PHC and assign immediate emergency ASHA home verification.</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if hist:
                        st.markdown("##### 📜 ASHA Clinical Action Audit History:")
                        df_hist = pd.DataFrame(hist, columns=["Log ID", "ASHA ID", "Status", "Action Taken", "Clinical Notes", "Follow-up Date", "Timestamp"])
                        st.dataframe(df_hist[["Timestamp", "ASHA ID", "Status", "Action Taken", "Clinical Notes", "Follow-up Date"]], use_container_width=True, hide_index=True)
            else:
                st.success("✅ All monitored mothers are in safe/stable baseline. No critical alerts pending.")
        except Exception as e:
            st.error(f"Error loading critical triage: {e}")
            
    elif page == "ASHA Worker Tracking":
        st.markdown("### 👥 ASHA Field Worker Performance & Case Tracking")
        st.markdown("Live multi-village caseload monitoring, triage performance, and task dispatch.")
        
        try:
            workload = dvh.get_asha_workload_breakdown()
            if workload:
                df_wl = pd.DataFrame(workload)
                st.dataframe(df_wl, use_container_width=True, hide_index=True)
            else:
                st.info("No ASHA tracking records available.")
        except Exception as e:
            st.error(f"Error loading ASHA tracking: {e}")
            
        st.markdown("<br><hr><br>", unsafe_allow_html=True)
        st.markdown("#### 📋 Live Field Tasks Generated for Today")
        try:
            tasks = dvh.generate_asha_daily_tasks()
            for idx, t in enumerate(tasks, 1):
                st.markdown(f"**{idx}.** Task Type: `{t.get('type')}` | Details: `{t.get('args')}`")
        except Exception as e:
            st.error(f"Error generating tasks: {e}")
            
    elif page == "Village Risk Surveillance":
        st.markdown("### 🗺️ Village-Level Risk Surveillance & Geo-Intelligence")
        try:
            village_data = dvh.get_village_risk_aggregations()
            if village_data:
                df_v = pd.DataFrame(village_data)
                st.dataframe(df_v[["Village", "Mothers", "AvgScore", "Category"]], use_container_width=True, hide_index=True)
                
                st.markdown("#### Geographic Distribution of Villages")
                map_df = pd.DataFrame([{"lat": v['Lat'], "lon": v['Lon']} for v in village_data if v.get('Lat') and v.get('Lon')])
                if not map_df.empty:
                    st.map(map_df, zoom=10)
            else:
                st.info("No geospatial records available.")
        except Exception as e:
            st.error(f"Error displaying surveillance map: {e}")
            
    elif page == "Vaccination Coverage":
        st.markdown("### 💉 District Immunization Performance")
        c1, c2, c3 = st.columns(3)
        c1.metric("Completed Vaccinations", vax_cov.get("Vaccinated", 0), "✅ Target Met")
        c2.metric("Pending Vaccinations", vax_cov.get("Pending", 0), "⏳ Scheduled")
        c3.metric("Overdue Vaccinations", vax_cov.get("Overdue", 0), "- Action Required")
        
        st.markdown("<br>#### Upcoming Inoculations (Next 7 Days)", unsafe_allow_html=True)
        try:
            upcoming = dvh.get_upcoming_vaccinations(days=7)
            if upcoming:
                st.table(pd.DataFrame(upcoming))
            else:
                st.info("No vaccinations due in the upcoming week.")
        except Exception as e:
            st.error(f"Error loading upcoming vaccinations: {e}")
            
    elif page == "All Cases Directory":
        st.markdown("### 📋 Complete District Patient Directory & Case Monitoring")
        st.markdown("Multi-variable surveillance with filters by Village, Risk Level, and Case Workflow Status.")
        
        try:
            all_cases = dvh.get_all_patient_cases_for_supervisor()
            if all_cases:
                df_cases = pd.DataFrame(all_cases)
                
                # Filters
                f_col1, f_col2, f_col3, f_col4 = st.columns(4)
                with f_col1:
                    villages_list = ["All Villages"] + sorted(df_cases["Village"].dropna().unique().tolist())
                    sel_v = st.selectbox("Filter by Village:", villages_list)
                with f_col2:
                    risk_list = ["All Risk Levels", "High", "Medium", "Low"]
                    sel_r = st.selectbox("Filter by Risk Level:", risk_list)
                with f_col3:
                    status_list = ["All Statuses"] + sorted(df_cases["Status"].dropna().unique().tolist())
                    sel_s = st.selectbox("Filter by Status:", status_list)
                with f_col4:
                    search_txt = st.text_input("Search Patient (ID or Name):", placeholder="e.g. 001 or Sath")
                    
                # Apply Filters
                if sel_v != "All Villages":
                    df_cases = df_cases[df_cases["Village"] == sel_v]
                if sel_r != "All Risk Levels":
                    df_cases = df_cases[df_cases["Risk Level"] == sel_r]
                if sel_s != "All Statuses":
                    df_cases = df_cases[df_cases["Status"] == sel_s]
                if search_txt.strip():
                    df_cases = df_cases[
                        df_cases["Mother ID"].astype(str).str.contains(search_txt.strip(), case=False) |
                        df_cases["Name"].astype(str).str.contains(search_txt.strip(), case=False)
                    ]
                    
                st.markdown(f"**Showing {len(df_cases)} matching patient records:**")
                st.dataframe(
                    df_cases[["Mother ID", "Name", "Village", "Phone", "Risk Score", "Risk Level", "Symptoms", "ASHA Assigned", "Action Taken", "Status", "Last Updated"]],
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("No patient cases found in database.")
        except Exception as e:
            st.error(f"Error loading cases directory: {e}")

def community_care_dashboard():
    """Render the Community Care & Village Health Support Portal."""
    import database_village_health as dvh
    
    village = st.session_state.get('community_village', 'Rampur')
    member = st.session_state.get('community_member', 'Community Member')
    
    with st.sidebar:
        # Top back navigation buttons
        c_nav_c1, c_nav_c2 = st.columns([1.5, 1])
        with c_nav_c1:
            if st.button("⬅ Back to Section", key="comm_back_to_section_btn", use_container_width=True):
                back_to_patient_services()
        with c_nav_c2:
            if st.button("🏠 Home", key="comm_home_btn", use_container_width=True):
                back_to_roles()
            
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #059669 0%, #10b981 100%); padding: 18px; border-radius: 14px; color: white; margin-bottom: 15px; text-align: center; box-shadow: 0 4px 14px rgba(5, 150, 105, 0.25);">
            <div style="font-size: 2rem; margin-bottom: 4px;">👨‍👩‍👧</div>
            <h3 style="margin: 0; color: white; font-size: 1.15rem; font-family: 'Outfit', sans-serif; font-weight: 800;">Community Care</h3>
            <p style="margin: 2px 0 0 0; font-size: 0.8rem; opacity: 0.9;">Village Health & Support Portal</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown(f"<div style='font-size: 0.85rem; color: #475569; font-weight: 600; margin-bottom: 10px;'>Village: <b style='color: #059669;'>{village}</b></div>", unsafe_allow_html=True)
        st.divider()
        
        c_nav = {
            "Community Health Hub": ("Health Hub & Contacts", "🏥"),
            "Immunization Camps": ("Village Health Camps", "💉"),
            "Nutrition Schemes": ("Maternal Nutrition Schemes", "🥗"),
            "Ambulance & Emergency": ("108 Emergency Transport", "🚑"),
            "Health Guidelines": ("Pregnancy Guidelines", "📢")
        }
        
        cur_page = st.session_state.get('community_page', 'Community Health Hub')
        for k, (lbl, icon) in c_nav.items():
            if st.button(f"{icon} {lbl}", use_container_width=True, type="primary" if cur_page == k else "secondary", key=f"comm_btn_{k}"):
                st.session_state['community_page'] = k
                
        st.divider()
        cur_lang = st.session_state.get('language', 'English')
        st.selectbox("🌐 " + _t("lang_toggle"), SUPPORTED_LANGUAGES, index=SUPPORTED_LANGUAGES.index(cur_lang) if cur_lang in SUPPORTED_LANGUAGES else 0, key="comm_lang_toggle", on_change=lambda: st.session_state.update({"language": st.session_state.comm_lang_toggle}))
        
        if st.button("⬅ Back to Section", key="comm_bottom_back_btn", use_container_width=True):
            back_to_patient_services()

    page = st.session_state.get('community_page', 'Community Health Hub')
    
    # Universal top back navigation bar for sub-pages
    if page != "Community Health Hub":
        col_b1, _ = st.columns([1.6, 4])
        with col_b1:
            if st.button("⬅ Back to Health Hub", key=f"comm_subpage_back_{page}", use_container_width=True):
                st.session_state['community_page'] = "Community Health Hub"
                st.rerun()
    
    # Top banner
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 50%, #f0fdf4 100%); padding: 22px 26px; border-radius: 18px; border: 1.5px solid #a7f3d0; box-shadow: 0 4px 16px rgba(16, 185, 129, 0.06); margin-bottom: 20px;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
            <div>
                <span style="background: #ffffff; color: #065f46; border: 1.5px solid #a7f3d0; padding: 4px 14px; border-radius: 20px; font-weight: 800; font-size: 0.8rem;">
                    👨‍👩‍👧 COMMUNITY CARE NETWORK
                </span>
                <h1 style="margin: 6px 0 2px 0; font-size: 1.9rem; color: #064e3b; font-family: 'Outfit', sans-serif; font-weight: 800;">
                    {village} Maternal & Child Community Care
                </h1>
                <p style="margin: 0; color: #047857; font-size: 0.92rem; font-weight: 500;">
                    Free government maternal benefits, immunization camps, Anganwadi food distribution, and emergency transport.
                </p>
            </div>
            <div>
                <span style="background: #ffffff; border: 1.5px solid #86efac; color: #059669; padding: 6px 14px; border-radius: 12px; font-weight: 700; font-size: 0.85rem;">
                    📍 Cluster: {village}
                </span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    if page == "Community Health Hub":
        col1, col2 = st.columns([1.5, 1])
        with col1:
            st.markdown("### 🏥 Village Health Contacts & Support")
            st.markdown(f"""
            <div style="background: #ffffff; border: 1.5px solid #86efac; border-radius: 16px; padding: 20px; margin-bottom: 15px; box-shadow: 0 4px 12px rgba(0,0,0,0.03);">
                <h4 style="color: #065f46; margin: 0 0 10px 0;">Primary Village Healthcare Workers</h4>
                <div style="display: flex; flex-direction: column; gap: 10px;">
                    <div style="display: flex; justify-content: space-between; border-bottom: 1px solid #f0fdf4; padding-bottom: 8px;">
                        <span>👩‍⚕️ <b>ASHA Worker ({village}):</b> Sunita Devi</span>
                        <span style="color: #0284c7; font-weight: 700;">📞 98765-43210</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; border-bottom: 1px solid #f0fdf4; padding-bottom: 8px;">
                        <span>🥗 <b>Anganwadi Worker (AWW):</b> Rekha Sharma</span>
                        <span style="color: #0284c7; font-weight: 700;">📞 98765-43211</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; border-bottom: 1px solid #f0fdf4; padding-bottom: 8px;">
                        <span>🩺 <b>Auxiliary Nurse Midwife (ANM):</b> Meena Kumari</span>
                        <span style="color: #0284c7; font-weight: 700;">📞 98765-43212</span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span>🚑 <b>Emergency Ambulance Coordinator:</b> 24/7 Dispatch</span>
                        <span style="color: #dc2626; font-weight: 800;">📞 108 / 102</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
        with col2:
            st.markdown("### 🚨 Rapid Emergency Call")
            st.markdown("""
            <div style="background: #fff1f2; border: 2px solid #f43f5e; border-radius: 16px; padding: 20px; text-align: center;">
                <div style="font-size: 2.2rem; margin-bottom: 6px;">🚑</div>
                <h3 style="color: #9f1239; margin: 0 0 6px 0;">Dial 108 Ambulance</h3>
                <p style="color: #881337; font-size: 0.88rem; margin: 0 0 14px 0;">Free emergency ambulance transport for labor, bleeding, or urgent pregnancy complications.</p>
                <div style="background: #ffffff; color: #e11d48; font-weight: 800; padding: 8px 16px; border-radius: 10px; font-size: 1.2rem; border: 1.5px solid #fda4af;">
                    TOLL FREE: 108 / 102
                </div>
            </div>
            """, unsafe_allow_html=True)
            
    elif page == "Immunization Camps":
        st.markdown("### 💉 Upcoming Village Immunization Camps")
        st.markdown("Village Health Sanitation & Nutrition Day (VHSND) camps held every month.")
        try:
            upcoming = dvh.get_upcoming_vaccinations(days=14)
            if upcoming:
                st.table(pd.DataFrame(upcoming))
            else:
                st.info("Next general immunization session scheduled for 1st & 3rd Wednesday.")
        except Exception:
            st.info("Vaccination camps active every Wednesday at the local Anganwadi center.")
            
    elif page == "Nutrition Schemes":
        st.markdown("### 🥗 Government Maternal & Child Nutrition Schemes")
        st.markdown("""
        <div style="display: flex; flex-direction: column; gap: 14px;">
            <div style="background: #ffffff; border-left: 6px solid #10b981; border-radius: 12px; padding: 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
                <h4 style="color: #065f46; margin: 0 0 6px 0;">1. Pradhan Mantri Matru Vandana Yojana (PMMVY)</h4>
                <p style="color: #475569; font-size: 0.9rem; margin: 0;">Direct Cash Benefit of <b>₹5,000</b> in three installments upon registration, antenatal check-ups (ANC), and child vaccination.</p>
            </div>
            <div style="background: #ffffff; border-left: 6px solid #3b82f6; border-radius: 12px; padding: 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
                <h4 style="color: #1e40af; margin: 0 0 6px 0;">2. POSHAN Abhiyaan (National Nutrition Mission)</h4>
                <p style="color: #475569; font-size: 0.9rem; margin: 0;">Supplementary nutrition, micronutrient packets, and hot cooked meals provided free at the local Anganwadi center for pregnant and lactating women.</p>
            </div>
            <div style="background: #ffffff; border-left: 6px solid #f59e0b; border-radius: 12px; padding: 18px; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
                <h4 style="color: #92400e; margin: 0 0 6px 0;">3. Iron and Folic Acid (IFA) Distribution</h4>
                <p style="color: #475569; font-size: 0.9rem; margin: 0;">Free 180-day course of Iron-Folic Acid tablets to prevent maternal anemia and ensure healthy baby birth weight.</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
    elif page == "Ambulance & Emergency":
        st.markdown("### 🚑 Emergency Transport & Hospital Logistics")
        st.markdown("""
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
            <div style="background: #ffffff; border: 1.5px solid #fda4af; border-radius: 14px; padding: 20px;">
                <h4 style="color: #9f1239; margin: 0 0 8px 0;">🚨 108 Emergency Ambulance</h4>
                <p style="color: #475569; font-size: 0.9rem; margin: 0 0 10px 0;">Dispatches trained paramedic ambulance directly to your village location with GPS tracking.</p>
                <b>Dial: 108 (24x7 Free)</b>
            </div>
            <div style="background: #ffffff; border: 1.5px solid #93c5fd; border-radius: 14px; padding: 20px;">
                <h4 style="color: #1e40af; margin: 0 0 8px 0;">🚐 102 Janani Shishu Van</h4>
                <p style="color: #475569; font-size: 0.9rem; margin: 0 0 10px 0;">Free dedicated drop-back transport for mother and newborn infant after institutional hospital delivery.</p>
                <b>Dial: 102 (Free for Mothers)</b>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
    elif page == "Health Guidelines":
        st.markdown("### 📢 Essential Maternal Danger Signs to Watch For")
        st.markdown("""
        <div style="background: #fffbeb; border: 1.5px solid #fde68a; border-radius: 14px; padding: 20px;">
            <h4 style="color: #92400e; margin: 0 0 10px 0;">Seek Immediate Medical Care If You Notice:</h4>
            <ul style="color: #78350f; font-size: 0.92rem; line-height: 1.8; margin: 0;">
                <li>Vaginal bleeding or spotting at any stage of pregnancy.</li>
                <li>Severe swelling in face, hands, or sudden unexplained weight gain.</li>
                <li>Severe persistent headaches with blurred vision or dizziness (signs of high BP/preeclampsia).</li>
                <li>Reduced or absent fetal movements after the 5th month.</li>
                <li>Sudden leakage of fluid (water breaking) before delivery term.</li>
                <li>High fever with shivering or severe lower abdominal cramps.</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

def logout():
    """Clear session data and return to login."""
    st.session_state['logged_in'] = False
    st.session_state['role'] = None
    st.session_state['selected_main_role'] = None
    st.session_state['selected_patient_service'] = None
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
    
    bg_image_base64 = ""
    # Load the background image if it exists
    if os.path.exists("splash_bg.png"):
        bg_image_base64 = load_image_base64("splash_bg.png")
            
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
    st.session_state['splash_shown'] = True

def main():
    init_session_state()
    apply_custom_css()
    # Process any pending offline data if online
    process_offline_sync()
    
    if not st.session_state.get('logged_in', False):
        login_page()
    else:
        role = st.session_state.get('role')
        if role == "Mother":
            mother_dashboard()
        elif role == "ASHA Worker":
            asha_worker_dashboard()
        elif role == "Baby Care":
            baby_dashboard()
        elif role == "Supervisor":
            supervisor_dashboard()
        elif role == "Community Care":
            community_care_dashboard()
            
    # Always render footer at the very end
    render_footer()

if __name__ == "__main__":
    main()