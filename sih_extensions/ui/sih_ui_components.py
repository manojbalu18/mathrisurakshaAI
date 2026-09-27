import streamlit as st
import pandas as pd
import json
import datetime
import math

from ..facility_directory import FacilityDirectory, haversine_distance
from ..appointment_service import AppointmentService
from ..queue_service import QueueService
from ..referral_service import ReferralService
from ..teleconsultation_service import TeleconsultationService
from ..medicine_service import MedicineService
from ..diagnostic_service import DiagnosticService
from ..patient_timeline_service import PatientTimelineService
from ..fhir_mapper import FHIRMapper

def render_sih_page(page: str, role: str):
    """Router for all Health UI pages."""
    st.markdown(f"## {page}")
    
    if page == "Facility Directory":
        render_facilities()
    elif page == "Appointments":
        render_appointments(role)
    elif page == "Queue Management":
        render_queue(role)
    elif page == "Referrals":
        render_referrals(role)
    elif page == "Teleconsultations":
        render_consultations(role)
    elif page == "Availability":
        render_availability(role)
    elif page == "Patient Timeline":
        render_timeline(role)
    elif page == "FHIR Export":
        render_fhir(role)

import plotly.express as px
import plotly.graph_objects as go

FACILITY_CATEGORIES = [
    "Primary Health Centre (PHC)",
    "Community Health Centre (CHC)",
    "District Hospital",
    "Government Maternity Hospital",
    "Emergency Care Centre",
    "Diagnostic Laboratory",
    "Pharmacy"
]

CATEGORY_COLORS = {
    "Primary Health Centre (PHC)": "#0d9488",
    "Community Health Centre (CHC)": "#0284c7",
    "District Hospital": "#7c3aed",
    "Government Maternity Hospital": "#e11d48",
    "Emergency Care Centre": "#dc2626",
    "Diagnostic Laboratory": "#d97706",
    "Pharmacy": "#059669"
}

CATEGORY_ICONS = {
    "Primary Health Centre (PHC)": "🏥",
    "Community Health Centre (CHC)": "🏥",
    "District Hospital": "🏛️",
    "Government Maternity Hospital": "🤱",
    "Emergency Care Centre": "🚨",
    "Diagnostic Laboratory": "🔬",
    "Pharmacy": "💊"
}

def render_facilities():
    # Make sure clean facility data is populated
    FacilityDirectory.seed_demo_data()
    
    # Custom styling for Facility Directory cards & components
    st.markdown("""
        <style>
        .fac-header-banner {
            background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 50%, #fdf2f8 100%);
            border: 1px solid #bae6fd;
            border-radius: 14px;
            padding: 18px 22px;
            margin-bottom: 22px;
        }
        .fac-header-title {
            font-family: 'Outfit', sans-serif;
            font-size: 1.45rem;
            font-weight: 700;
            color: #0f172a;
            margin-bottom: 4px;
        }
        .fac-header-sub {
            font-size: 0.92rem;
            color: #475569;
            line-height: 1.45;
        }
        .fac-card {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 14px;
            padding: 18px;
            margin-bottom: 16px;
            box-shadow: 0 4px 14px rgba(15, 23, 42, 0.04);
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        .fac-card:hover {
            box-shadow: 0 8px 20px rgba(15, 23, 42, 0.08);
            border-color: #cbd5e1;
        }
        .fac-badge-type {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.78rem;
            font-weight: 700;
            letter-spacing: 0.02em;
        }
        .fac-badge-dist {
            display: inline-block;
            background: #f1f5f9;
            color: #334155;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.78rem;
            font-weight: 600;
        }
        .fac-badge-emerg {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 9999px;
            font-size: 0.76rem;
            font-weight: 700;
        }
        .fac-service-tag {
            display: inline-block;
            background: #f8fafc;
            color: #475569;
            border: 1px solid #e2e8f0;
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 0.74rem;
            margin-right: 4px;
            margin-bottom: 4px;
            font-weight: 500;
        }
        .fac-btn-link {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            text-decoration: none !important;
            padding: 8px 14px;
            border-radius: 8px;
            font-size: 0.82rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s ease;
            text-align: center;
        }
        .fac-btn-call {
            background-color: #0284c7;
            color: #ffffff !important;
        }
        .fac-btn-call:hover {
            background-color: #0369a1;
            color: #ffffff !important;
        }
        .fac-btn-dir {
            background-color: #f1f5f9;
            color: #0f172a !important;
            border: 1px solid #cbd5e1;
        }
        .fac-btn-dir:hover {
            background-color: #e2e8f0;
            color: #0f172a !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # Top Header & Sample Data Notice
    st.markdown("""
        <div class="fac-header-banner">
            <div class="fac-header-title">🏥 Healthcare Facility Directory</div>
            <div class="fac-header-sub">
                Explore verified maternal health centres, community hospitals, emergency care units, diagnostic laboratories, and pharmacies.
                <br><b>ℹ️ [SAMPLE DATA]</b> Structured for rural mothers, families, and ASHA field workers. For medical emergencies, always dial <b>108</b> (Ambulance) or <b>102</b> (Janani Shishu Suraksha).
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Determine reference user location for accurate distance calculation
    user_lat = 17.3850
    user_lon = 78.4867
    
    # If user has a location in session state, prioritize it
    user_obj = st.session_state.get('user', {})
    if isinstance(user_obj, dict):
        if user_obj.get('latitude') and user_obj.get('longitude'):
            try:
                user_lat = float(user_obj['latitude'])
                user_lon = float(user_obj['longitude'])
            except (ValueError, TypeError):
                pass

    # Retrieve all facilities from directory service
    all_facilities = FacilityDirectory.list_facilities(active_only=True)
    if not all_facilities:
        st.warning("No healthcare facilities found in directory.")
        return

    # Compute distances for all facilities
    for f in all_facilities:
        f['distance_km'] = round(FacilityDirectory.haversine_distance(user_lat, user_lon, f['latitude'], f['longitude']), 1)

    # --- Search & Filter Controls ---
    f_col1, f_col2 = st.columns([3, 2])
    with f_col1:
        search_query = st.text_input(
            "🔍 Search Facilities",
            placeholder="Search by facility name, address, village, or service (e.g., Ultrasound, Delivery, Jan Aushadhi)...",
            label_visibility="collapsed"
        )
    with f_col2:
        sort_choice = st.selectbox(
            "Sort Order",
            ["📍 Distance (Nearest First)", "🔤 Facility Name (A-Z)", "🚨 24/7 Emergency First"],
            label_visibility="collapsed"
        )

    # Category Selector Pills / Filter
    type_options = ["All Categories (7)"] + FACILITY_CATEGORIES
    selected_type = st.selectbox("Filter by Facility Category", type_options)

    # Secondary Filters Row
    f_sub1, f_sub2 = st.columns([3, 2])
    with f_sub1:
        service_keywords = [
            "All Services",
            "Antenatal Care (ANC)",
            "Normal Delivery",
            "C-Section / Surgery",
            "High-Risk Pregnancy",
            "Ultrasound / Imaging",
            "NICU / SNCU",
            "Blood Bank",
            "Lab Diagnostics",
            "Essential Medicines",
            "Routine Immunization",
            "Ambulance"
        ]
        selected_service = st.selectbox("Filter by Available Service", service_keywords)
    with f_sub2:
        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
        emergency_only = st.checkbox("🚨 24/7 Emergency Facilities Only", value=False)

    # --- Apply Filtering Logic ---
    filtered_facilities = []
    for fac in all_facilities:
        # Category filter
        if selected_type != "All Categories (7)" and fac['type'] != selected_type:
            continue
            
        # Emergency filter
        if emergency_only and not fac.get('emergency_available', False):
            continue
            
        # Service keyword filter
        if selected_service != "All Services":
            srv_term = selected_service.split(" / ")[0].split(" (")[0].lower()
            if srv_term not in fac.get('services', '').lower():
                continue
                
        # Search query across Name, Address, Type, Services
        if search_query and search_query.strip():
            sq = search_query.strip().lower()
            haystack = f"{fac['name']} {fac['type']} {fac['address']} {fac['services']}".lower()
            if sq not in haystack:
                continue
                
        filtered_facilities.append(fac)

    # --- Apply Sorting ---
    if sort_choice == "📍 Distance (Nearest First)":
        filtered_facilities.sort(key=lambda x: x['distance_km'])
    elif sort_choice == "🔤 Facility Name (A-Z)":
        filtered_facilities.sort(key=lambda x: x['name'])
    elif sort_choice == "🚨 24/7 Emergency First":
        filtered_facilities.sort(key=lambda x: (not x.get('emergency_available', False), x['distance_km']))

    # --- Interactive Map Component ---
    st.markdown("#### 🗺️ Interactive Healthcare Facilities Map")
    if filtered_facilities:
        map_df = pd.DataFrame([
            {
                "Facility Name": f['name'],
                "Facility Type": f['type'],
                "Address": f['address'],
                "Distance (km)": f"{f['distance_km']} km",
                "Operating Hours": f['operating_hours'],
                "Emergency": "24/7 Available" if f['emergency_available'] else "Scheduled Hours",
                "Contact": f['contact_number'],
                "lat": f['latitude'],
                "lon": f['longitude'],
                "Category": f['type']
            }
            for f in filtered_facilities
        ])

        try:
            # Render interactive Plotly Map
            fig = px.scatter_map(
                map_df,
                lat="lat",
                lon="lon",
                hover_name="Facility Name",
                hover_data={
                    "Facility Type": True,
                    "Distance (km)": True,
                    "Operating Hours": True,
                    "Emergency": True,
                    "Contact": True,
                    "lat": False,
                    "lon": False
                },
                color="Category",
                color_discrete_map=CATEGORY_COLORS,
                zoom=10,
                map_style="open-street-map",
                height=380
            )
            fig.update_layout(
                margin={"r": 0, "t": 10, "l": 0, "b": 0},
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=-0.28,
                    xanchor="center",
                    x=0.5,
                    font=dict(size=11)
                )
            )
            st.plotly_chart(fig, use_container_width=True)
        except Exception:
            # Seamless fallback to st.map
            st.map(map_df[['lat', 'lon']], zoom=10)
    else:
        st.info("No facility markers to display for the current filter criteria.")

    st.markdown(f"**Showing {len(filtered_facilities)} healthcare facilities**")
    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

    # --- Facility Cards Grid ---
    if not filtered_facilities:
        st.warning("No healthcare facilities match your search or filter settings. Please adjust your criteria.")
        return

    # Render 2-column card grid
    for idx in range(0, len(filtered_facilities), 2):
        cols = st.columns(2)
        for c_idx, col in enumerate(cols):
            fac_idx = idx + c_idx
            if fac_idx < len(filtered_facilities):
                fac = filtered_facilities[fac_idx]
                with col:
                    cat_color = CATEGORY_COLORS.get(fac['type'], '#0284c7')
                    cat_icon = CATEGORY_ICONS.get(fac['type'], '🏥')
                    
                    # Status styling
                    is_emerg = fac.get('emergency_available', False)
                    emerg_bg = "#fef2f2" if is_emerg else "#f8fafc"
                    emerg_color = "#dc2626" if is_emerg else "#64748b"
                    emerg_border = "#fecaca" if is_emerg else "#e2e8f0"
                    emerg_label = "🚨 24/7 Emergency" if is_emerg else "⏳ Scheduled OPD"
                    
                    # Open status text
                    hours_text = fac.get('operating_hours', '24/7 Open')
                    status_indicator = "🟢 Open 24/7" if "24/7" in hours_text else f"🕒 {hours_text}"
                    
                    # Phone clean
                    clean_phone = fac.get('contact_number', '').split(' ')[0].split('/')[0].strip()
                    gmap_url = f"https://www.google.com/maps/dir/?api=1&destination={fac['latitude']},{fac['longitude']}"
                    
                    # Service tags
                    service_list = [s.strip() for s in fac.get('services', '').split(',') if s.strip()]
                    service_tags_html = "".join([f'<span class="fac-service-tag">{s}</span>' for s in service_list[:5]])
                    if len(service_list) > 5:
                        service_tags_html += f'<span class="fac-service-tag">+{len(service_list)-5} more</span>'

                    card_html = f"""
                    <div class="fac-card">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 8px;">
                            <span class="fac-badge-type" style="background-color: {cat_color}18; color: {cat_color}; border: 1px solid {cat_color}40;">
                                {cat_icon} {fac['type']}
                            </span>
                            <div style="display: flex; gap: 6px;">
                                <span class="fac-badge-dist">📍 {fac['distance_km']} km</span>
                                <span class="fac-badge-emerg" style="background: {emerg_bg}; color: {emerg_color}; border: 1px solid {emerg_border};">
                                    {emerg_label}
                                </span>
                            </div>
                        </div>
                        <div style="font-family: 'Outfit', sans-serif; font-size: 1.08rem; font-weight: 700; color: #0f172a; margin-bottom: 4px; line-height: 1.3;">
                            {fac['name']}
                        </div>
                        <div style="font-size: 0.83rem; color: #64748b; margin-bottom: 8px; line-height: 1.35;">
                            📍 <b>Location:</b> {fac['address']}
                        </div>
                        <div style="font-size: 0.82rem; color: #0284c7; font-weight: 600; margin-bottom: 10px;">
                            {status_indicator}
                        </div>
                        <div style="margin-bottom: 14px;">
                            <div style="font-size: 0.74rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; margin-bottom: 4px;">Main Services:</div>
                            {service_tags_html}
                        </div>
                        <div style="display: flex; gap: 8px; margin-top: 6px;">
                            <a href="tel:{clean_phone}" class="fac-btn-link fac-btn-call" style="flex: 1;">
                                📞 Call {clean_phone}
                            </a>
                            <a href="{gmap_url}" target="_blank" class="fac-btn-link fac-btn-dir" style="flex: 1;">
                                🗺️ Get Directions
                            </a>
                        </div>
                    </div>
                    """
                    st.markdown(card_html, unsafe_allow_html=True)
                    
                    # View Details Expander Button
                    with st.expander(f"ℹ️ View Details: {fac['name'].replace('[SAMPLE DATA] ', '')}"):
                        st.markdown(f"**Facility ID:** `{fac['facility_id']}`")
                        st.markdown(f"**Category:** `{fac['type']}`")
                        st.markdown(f"**Full Address:** {fac['address']}")
                        st.markdown(f"**Operating Schedule:** {fac['operating_hours']}")
                        st.markdown(f"**Contact & Helpline:** {fac['contact_number']}")
                        st.markdown(f"**Emergency Availability:** {'✅ 24/7 Emergency Care Ready' if is_emerg else '⏳ Regular OPD Hours Only'}")
                        st.markdown(f"**GPS Coordinates:** `Latitude: {fac['latitude']}, Longitude: {fac['longitude']}`")
                        st.markdown("**All Available Healthcare Services:**")
                        for s in service_list:
                            st.markdown(f"- {s}")
                        
                        # Direct navigation link inside details
                        st.markdown(f"[🔗 Open in Google Maps Navigation]({gmap_url})")


def render_appointments(role: str = "Mother"):
    # Ensure tables & clean facility seeds exist
    FacilityDirectory.seed_demo_data()
    
    # Custom CSS for Appointments UI
    st.markdown("""
        <style>
        .appt-header-banner {
            background: linear-gradient(135deg, #f0fdf4 0%, #e0f2fe 50%, #fdf2f8 100%);
            border: 1px solid #bbf7d0;
            border-radius: 14px;
            padding: 18px 22px;
            margin-bottom: 18px;
        }
        .appt-header-title {
            font-family: 'Outfit', sans-serif;
            font-size: 1.45rem;
            font-weight: 700;
            color: #0f172a;
            margin-bottom: 4px;
        }
        .appt-header-sub {
            font-size: 0.92rem;
            color: #475569;
            line-height: 1.45;
        }
        .appt-emergency-box {
            background: #fff1f2;
            border: 1px solid #fecdd3;
            border-left: 5px solid #e11d48;
            border-radius: 10px;
            padding: 12px 16px;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
        }
        .appt-context-pill {
            background: #f8fafc;
            border: 1px solid #cbd5e1;
            border-radius: 10px;
            padding: 10px 16px;
            margin-bottom: 18px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 0.88rem;
            color: #334155;
            font-weight: 600;
        }
        .appt-card {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 14px;
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04);
            transition: all 0.15s ease;
        }
        .appt-card:hover {
            border-color: #cbd5e1;
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.07);
        }
        .appt-status-badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 9999px;
            font-size: 0.76rem;
            font-weight: 700;
            letter-spacing: 0.02em;
        }
        .appt-status-confirmed { background: #dcfce7; color: #15803d; border: 1px solid #86efac; }
        .appt-status-scheduled { background: #e0f2fe; color: #0369a1; border: 1px solid #7dd3fc; }
        .appt-status-pending { background: #fef3c7; color: #b45309; border: 1px solid #fde68a; }
        .appt-status-rescheduled { background: #f3e8ff; color: #7e22ce; border: 1px solid #d8b4fe; }
        .appt-status-completed { background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }
        .appt-status-cancelled { background: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; }
        </style>
    """, unsafe_allow_html=True)

    # Top Header Banner
    st.markdown("""
        <div class="appt-header-banner">
            <div class="appt-header-title">📅 Maternal Healthcare Appointments & Teleconsultations</div>
            <div class="appt-header-sub">
                Book routine antenatal checkups (ANC), trimester growth ultrasound scans, and doctor consultations at verified healthcare centres.
                <br><b>ℹ️ [SAMPLE / DEMO WORKFLOW]</b> Integrated with Facility Directory & ASHA Maternal Register.
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Emergency Help Option for Urgent Situations
    st.markdown("""
        <div class="appt-emergency-box">
            <div>
                <b style="color: #9f1239;">🚨 Urgent Medical Concern or Emergency?</b>
                <div style="font-size: 0.85rem; color: #881337; margin-top: 2px;">
                    For severe bleeding, continuous high fever, water breaking, or sudden acute pain, <b>do not wait for an appointment</b>. Call emergency response immediately.
                </div>
            </div>
            <div style="display: flex; gap: 8px; flex-shrink: 0;">
                <a href="tel:108" style="background-color: #e11d48; color: #ffffff !important; padding: 6px 14px; border-radius: 8px; font-weight: 700; text-decoration: none; font-size: 0.82rem;">
                    🚑 Call 108 (Ambulance)
                </a>
                <a href="tel:102" style="background-color: #0284c7; color: #ffffff !important; padding: 6px 14px; border-radius: 8px; font-weight: 700; text-decoration: none; font-size: 0.82rem;">
                    🤱 Call 102 (Maternal)
                </a>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Determine Patient ID and Maternal Context
    patient_id = "001"
    mother_name = "Pregnant Mother"
    week = 24
    trimester = "2nd Trimester"

    user_info = st.session_state.get('user', {})
    if isinstance(user_info, dict):
        if user_info.get('unique_id'):
            patient_id = str(user_info['unique_id'])
        if user_info.get('name'):
            mother_name = str(user_info['name'])
    elif st.session_state.get('unique_id'):
        patient_id = str(st.session_state.get('unique_id'))
        mother_name = str(st.session_state.get('mother_name', 'Pregnant Mother'))

    # Gestational age dynamic calculation
    try:
        m_id = int(patient_id)
        if 1 <= m_id <= 40:
            week = 4 + ((m_id * 7) % 36)
        else:
            week = 24
    except ValueError:
        week = 24
    trimester = "1st Trimester" if week <= 12 else ("2nd Trimester" if week <= 27 else "3rd Trimester")

    # Patient Context Box
    if role == "Mother":
        st.markdown(f"""
            <div class="appt-context-pill">
                <span>🤰 <b>Patient:</b> {mother_name} (ID: <code>{patient_id}</code>)</span>
                <span>📅 <b>Current Pregnancy Stage:</b> Week {week} ({trimester})</span>
                <span>🔔 <b>SMS & Voice Reminders:</b> Enabled</span>
            </div>
        """, unsafe_allow_html=True)
    else:
        # ASHA Worker / Supervisor mode allows searching any mother
        c_pat1, c_pat2 = st.columns([2, 2])
        with c_pat1:
            searched_pat_id = st.text_input("Patient / Mother ID", value=patient_id, help="Enter Mother Unique ID for appointment booking")
            if searched_pat_id.strip():
                patient_id = searched_pat_id.strip()
        with c_pat2:
            st.markdown(f"<div style='margin-top: 28px; font-size: 0.88rem; color: #475569;'><b>Maternal Profile:</b> Week {week} ({trimester})</div>", unsafe_allow_html=True)

    # Load Patient Appointments for Tab Counters
    all_pat_appts = AppointmentService.list_patient_appointments(patient_id)
    upcoming_appts = [a for a in all_pat_appts if a['status'] in ['Confirmed', 'Scheduled', 'Pending', 'Rescheduled']]
    past_appts = [a for a in all_pat_appts if a['status'] in ['Completed', 'Cancelled', 'No-Show']]

    # Tabs
    tab_book, tab_upcoming, tab_history = st.tabs([
        "📅 Book Appointment",
        f"🕒 Upcoming Appointments ({len(upcoming_appts)})",
        f"📜 Past & Completed ({len(past_appts)})"
    ])

    # ---------------- TAB 1: BOOK APPOINTMENT FLOW ----------------
    with tab_book:
        st.markdown("### 📝 Schedule a New Consultation")
        
        # 1. Facility Selection (Connected to Facility Directory)
        facilities = FacilityDirectory.list_facilities(active_only=True)
        if not facilities:
            st.warning("No active facilities found in Facility Directory.")
            return

        fac_options = {f['facility_id']: f"{f['name']} ({f['type']})" for f in facilities}
        fac_ids = list(fac_options.keys())
        
        # Pre-select if passed from session state
        default_fac_id = st.session_state.get('selected_booking_facility', fac_ids[0])
        default_index = fac_ids.index(default_fac_id) if default_fac_id in fac_ids else 0

        selected_fac_id = st.selectbox(
            "1. Select Healthcare Facility (Connected to Facility Directory)",
            options=fac_ids,
            index=default_index,
            format_func=lambda x: fac_options.get(x, x),
            help="Choose verified healthcare facility from the directory"
        )

        selected_fac = FacilityDirectory.get_facility(selected_fac_id)
        if selected_fac:
            st.markdown(f"""
                <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px 14px; font-size: 0.82rem; color: #475569; margin-bottom: 12px;">
                    📍 <b>Address:</b> {selected_fac['address']} &nbsp;|&nbsp; 🕒 <b>Hours:</b> {selected_fac['operating_hours']} &nbsp;|&nbsp; 🚨 <b>Emergency:</b> {'24/7 Available' if selected_fac['emergency_available'] else 'Scheduled Hours'}
                </div>
            """, unsafe_allow_html=True)

        col_f1, col_f2 = st.columns(2)
        
        with col_f1:
            # 2. Select Doctor / Healthcare Provider
            providers = AppointmentService.get_providers_for_facility(selected_fac_id)
            provider_labels = [f"{p['name']} - {p['specialty']}" for p in providers]
            selected_provider_idx = st.selectbox(
                "2. Select Doctor / Specialist",
                range(len(providers)),
                format_func=lambda idx: provider_labels[idx] if idx < len(provider_labels) else "General Medical Officer"
            )
            selected_provider = providers[selected_provider_idx] if selected_provider_idx < len(providers) else {"id": "DOC-01", "name": "Doctor / Medical Officer"}

            # 3. Consultation Type
            consultation_type = st.radio(
                "3. Select Consultation Type",
                ["🏥 In-Person Consultation (At Centre)", "💻 Teleconsultation (Audio / Video Call)"],
                horizontal=True
            )
            clean_consult_type = "In-Person" if "In-Person" in consultation_type else "Teleconsultation"

        with col_f2:
            # 4. Select Date
            min_date = datetime.date.today()
            max_date = min_date + datetime.timedelta(days=60)
            selected_date = st.date_input("4. Select Consultation Date", min_value=min_date, max_value=max_date, value=min_date + datetime.timedelta(days=1))

            # 5. Show Available Time Slots
            time_slots = AppointmentService.get_time_slots()
            selected_slot = st.selectbox("5. Select Preferred Time Slot", time_slots)

        # 6. Select Appointment Reason
        reasons = [
            "Routine Antenatal Care (ANC Checkup)",
            "Trimester Ultrasound & Fetal Growth Scan",
            "High-Risk Pregnancy Evaluation (BP / Blood Sugar / Anemia)",
            "Postnatal & Newborn Health Follow-up",
            "Maternal Nutrition & Diet Counseling",
            "Tetanus / Routine Immunization Dose",
            "General Maternal Wellness & Symptoms Assessment",
            "Other Consultation / General OPD"
        ]
        selected_reason = st.selectbox("6. Select Appointment Reason", reasons)
        additional_notes = st.text_input("Additional Symptoms or Notes (Optional)", placeholder="e.g. Mild headache, dietary questions, reviewing lab test reports...")

        # 7. Reminder Notification Toggle
        reminder_opt = st.checkbox("🔔 Send SMS & ASHA Voice Call Reminder 24 Hours Prior", value=True)

        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)
        
        # Summary Box
        st.markdown(f"""
            <div style="background: #f0fdfa; border: 1px solid #99f6e4; border-radius: 10px; padding: 14px 18px; margin-bottom: 14px;">
                <b style="color: #0f766e; font-size: 0.95rem;">📋 Appointment Summary:</b>
                <div style="font-size: 0.85rem; color: #115e59; margin-top: 4px; line-height: 1.5;">
                    • <b>Facility:</b> {selected_fac['name'] if selected_fac else selected_fac_id}<br>
                    • <b>Doctor:</b> {selected_provider['name']}<br>
                    • <b>Type:</b> {clean_consult_type} &nbsp;|&nbsp; <b>Date & Time:</b> {selected_date.strftime('%A, %d %b %Y')} ({selected_slot})<br>
                    • <b>Reason:</b> {selected_reason} &nbsp;|&nbsp; <b>Gestational Context:</b> Week {week} ({trimester})
                </div>
            </div>
        """, unsafe_allow_html=True)

        # Confirm Booking Button
        if st.button("✅ Confirm & Book Appointment", type="primary", use_container_width=True):
            appt_time_iso = f"{selected_date.strftime('%Y-%m-%d')} {selected_slot.split(' - ')[0]}"
            full_reason = f"{selected_reason} | {additional_notes}" if additional_notes.strip() else selected_reason

            res = AppointmentService.create_appointment(
                patient_id=patient_id,
                facility_id=selected_fac_id,
                appointment_time=appt_time_iso,
                doctor_id=selected_provider.get('id', 'DOC-01'),
                doctor_name=selected_provider.get('name', 'Doctor / Medical Officer'),
                consultation_type=clean_consult_type,
                reason=full_reason,
                time_slot=selected_slot,
                pregnancy_week=week,
                trimester=trimester,
                reminder_enabled=reminder_opt,
                status="Confirmed"
            )

            if res.get("success"):
                st.success(f"🎉 Appointment Successfully Booked! Appointment ID: **{res['appointment_id']}**")
                st.balloons()
                st.markdown(f"""
                    <div style="background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 10px; padding: 16px; margin-top: 10px;">
                        <b style="color: #065f46; font-size: 1rem;">✅ Booking Confirmation Details</b>
                        <div style="font-size: 0.88rem; color: #047857; margin-top: 6px; line-height: 1.6;">
                            <b>Appointment ID:</b> <code>{res['appointment_id']}</code><br>
                            <b>Patient ID:</b> {patient_id} ({mother_name})<br>
                            <b>Facility:</b> {res['facility_name']}<br>
                            <b>Consultant:</b> {res['doctor_name']}<br>
                            <b>Scheduled Date & Slot:</b> {selected_date.strftime('%d %B %Y')} at {res['time_slot']}<br>
                            <b>Notification:</b> {'🔔 SMS & Voice reminder confirmed for 24h prior' if reminder_opt else 'No reminder scheduled'}
                        </div>
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.error(res.get("error", "Failed to book appointment. Please check selected time slot."))

    # ---------------- TAB 2: UPCOMING APPOINTMENTS ----------------
    with tab_upcoming:
        st.markdown("### 🕒 Active & Upcoming Appointments")
        
        if not upcoming_appts:
            st.info(f"No upcoming appointments found for Patient ID: **{patient_id}**.")
        else:
            for appt in upcoming_appts:
                status_class = f"appt-status-{appt['status'].lower()}"
                
                with st.container():
                    st.markdown(f"""
                        <div class="appt-card">
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
                                <div>
                                    <span style="font-size: 0.78rem; font-weight: 700; color: #64748b; text-transform: uppercase;">Appointment ID:</span>
                                    <code style="font-weight: 700; font-size: 0.88rem; color: #0f172a;">{appt['appointment_id']}</code>
                                </div>
                                <span class="appt-status-badge {status_class}">
                                    ● {appt['status']}
                                </span>
                            </div>
                            <div style="font-size: 1.05rem; font-weight: 700; color: #0f172a; margin-bottom: 4px;">
                                {appt['doctor_name']}
                            </div>
                            <div style="font-size: 0.86rem; color: #0284c7; font-weight: 600; margin-bottom: 6px;">
                                🏥 {appt['facility_name']} ({appt['consultation_type']})
                            </div>
                            <div style="font-size: 0.84rem; color: #475569; margin-bottom: 6px;">
                                📅 <b>Date & Slot:</b> {appt['appointment_time']} ({appt['time_slot']}) &nbsp;|&nbsp; <b>Stage:</b> Week {appt.get('pregnancy_week', week) or week}
                            </div>
                            <div style="font-size: 0.82rem; color: #64748b; line-height: 1.4;">
                                🩺 <b>Reason:</b> {appt['reason']}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

                    # Action buttons for Reschedule / Cancel
                    act_col1, act_col2 = st.columns(2)
                    
                    with act_col1:
                        with st.expander(f"🔄 Reschedule Appointment ({appt['appointment_id']})"):
                            new_resched_date = st.date_input(
                                "Select New Date",
                                min_value=datetime.date.today(),
                                value=datetime.date.today() + datetime.timedelta(days=2),
                                key=f"resched_date_{appt['appointment_id']}"
                            )
                            new_resched_slot = st.selectbox(
                                "Select New Slot",
                                AppointmentService.get_time_slots(),
                                key=f"resched_slot_{appt['appointment_id']}"
                            )
                            if st.button("Confirm Reschedule", key=f"btn_resched_{appt['appointment_id']}", type="primary"):
                                new_time_iso = f"{new_resched_date.strftime('%Y-%m-%d')} {new_resched_slot.split(' - ')[0]}"
                                r_res = AppointmentService.reschedule_appointment(
                                    appt['appointment_id'],
                                    new_appointment_time=new_time_iso,
                                    new_time_slot=new_resched_slot
                                )
                                if r_res.get("success"):
                                    st.success(r_res["message"])
                                    st.rerun()
                                else:
                                    st.error(r_res.get("error", "Failed to reschedule."))

                    with act_col2:
                        with st.expander(f"❌ Cancel Appointment ({appt['appointment_id']})"):
                            st.warning("Are you sure you want to cancel this appointment?")
                            if st.button("Yes, Cancel Appointment", key=f"btn_cancel_{appt['appointment_id']}"):
                                c_res = AppointmentService.cancel_appointment(appt['appointment_id'])
                                if c_res.get("success"):
                                    st.success(c_res["message"])
                                    st.rerun()
                                else:
                                    st.error(c_res.get("error", "Failed to cancel."))

    # ---------------- TAB 3: PAST APPOINTMENTS ----------------
    with tab_history:
        st.markdown("### 📜 Past & Completed Consultations")
        
        if not past_appts:
            st.info(f"No past appointment records found for Patient ID: **{patient_id}**.")
        else:
            for appt in past_appts:
                status_class = f"appt-status-{appt['status'].lower()}"
                st.markdown(f"""
                    <div class="appt-card" style="opacity: 0.9;">
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
                            <div>
                                <span style="font-size: 0.78rem; font-weight: 700; color: #64748b; text-transform: uppercase;">ID:</span>
                                <code style="font-weight: 700; font-size: 0.86rem; color: #334155;">{appt['appointment_id']}</code>
                            </div>
                            <span class="appt-status-badge {status_class}">
                                ● {appt['status']}
                            </span>
                        </div>
                        <div style="font-size: 0.98rem; font-weight: 700; color: #334155; margin-bottom: 2px;">
                            {appt['doctor_name']} &nbsp;|&nbsp; <span style="font-weight: 500; font-size: 0.85rem; color: #64748b;">{appt['facility_name']}</span>
                        </div>
                        <div style="font-size: 0.82rem; color: #64748b; margin-bottom: 4px;">
                            📅 Date: {appt['appointment_time']} ({appt['time_slot']}) &nbsp;|&nbsp; Type: {appt['consultation_type']}
                        </div>
                        <div style="font-size: 0.82rem; color: #475569;">
                            🩺 Reason: {appt['reason']}
                        </div>
                    </div>
                """, unsafe_allow_html=True)


def render_queue(role):
    st.info("ℹ️ DEMO DATA - Sample information for demonstration purposes.")
    facs = FacilityDirectory.list_facilities()
    fac_options = {f['facility_id']: f['name'] for f in facs}
    
    fac_id = st.selectbox("Select Facility Queue", options=list(fac_options.keys()), format_func=lambda x: fac_options.get(x, x))
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("### Generate Token")
        with st.form("queue_form"):
            pat_id = st.text_input("Patient ID")
            dept = st.text_input("Department (e.g. OPD)")
            priority = st.selectbox("Priority", [0, 1, 2])
            if st.form_submit_button("Join Queue"):
                if pat_id and dept:
                    res = QueueService.add_patient(fac_id, pat_id, dept, priority=priority)
                    if res.get("success"):
                        st.success(f"Joined queue! Token: {res['token_number']}")
                    else:
                        st.error(res.get("error", "Failed to join queue"))
                else:
                    st.error("Required fields missing.")
                    
    with c2:
        st.markdown("### Call Next Patient")
        dept_call = st.text_input("Department to Call")
        if st.button("Call Next Patient"):
            if dept_call:
                res = QueueService.call_next(fac_id)
                if res:
                    st.success(f"Called Patient: {res['patient_id']} (Token: {res['token_number']})")
                else:
                    st.info("No pending patients in queue.")

def render_referrals(role):
    st.info("ℹ️ DEMO DATA - Sample information for demonstration purposes.")
    
    tabs = st.tabs(["Create Referral", "View Referrals"])
    with tabs[0]:
        with st.form("ref_form"):
            pat_id = st.text_input("Patient ID")
            facs = FacilityDirectory.list_facilities()
            fac_options = {f['facility_id']: f['name'] for f in facs}
            
            src_fac = st.selectbox("Source Facility", options=list(fac_options.keys()), format_func=lambda x: fac_options.get(x, x))
            dest_fac = st.selectbox("Destination Facility", options=list(fac_options.keys()), format_func=lambda x: fac_options.get(x, x))
            reason = st.text_area("Reason for Referral")
            priority = st.selectbox("Priority", [0, 1, 2])
            
            if st.form_submit_button("Create Referral"):
                if pat_id and reason:
                    res = ReferralService.create_referral(pat_id, src_fac, dest_fac, reason, priority=priority)
                    st.success(f"Referral Created! ID: {res['referral_id']}")
                else:
                    st.error("Missing fields")
                    
    with tabs[1]:
        pat_search = st.text_input("View Referrals for Facility ID")
        if pat_search:
            refs = ReferralService.list_incoming_referrals(pat_search)
            if refs:
                st.dataframe(pd.DataFrame(refs)[['referral_id', 'patient_id', 'source_facility', 'status', 'priority']], use_container_width=True)
            else:
                st.info("No referrals found.")

def render_consultations(role):
    st.warning("⚠️ DEMO TELECONSULTATION - This is a demonstration workflow. No real video connection is created.")
    
    with st.form("tc_form"):
        pat_id = st.text_input("Patient ID")
        prov_id = st.text_input("Provider ID")
        fac_id = st.text_input("Facility ID")
        
        if st.form_submit_button("Request Consultation"):
            if pat_id and prov_id and fac_id:
                res = TeleconsultationService.create_request(pat_id, prov_id, fac_id, "Demo Consult")
                if res.get("success"):
                    st.success(f"Consultation Requested! Session ID: {res['consultation_id']}")
                else:
                    st.error(res.get("error", "Failed to request consultation"))
            else:
                st.error("Patient ID, Provider ID, and Facility ID are required.")

def render_availability(role: str = "Mother"):
    # Ensure tables & default sample prescriptions/diagnostics exist
    MedicineService.seed_demo_data()
    DiagnosticService.seed_demo_data()

    # Custom styling for Medicines & Diagnostics UI
    st.markdown("""
        <style>
        .med-header-banner {
            background: linear-gradient(135deg, #ecfdf5 0%, #e0f2fe 50%, #fef3c7 100%);
            border: 1px solid #a7f3d0;
            border-radius: 14px;
            padding: 18px 22px;
            margin-bottom: 16px;
        }
        .med-header-title {
            font-family: 'Outfit', sans-serif;
            font-size: 1.45rem;
            font-weight: 700;
            color: #0f172a;
            margin-bottom: 4px;
        }
        .med-safety-alert {
            background: #fffbeb;
            border: 1px solid #fde68a;
            border-left: 5px solid #d97706;
            border-radius: 10px;
            padding: 12px 16px;
            margin-bottom: 18px;
            font-size: 0.84rem;
            color: #92400e;
            line-height: 1.45;
        }
        .med-summary-card {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 14px 18px;
            margin-bottom: 14px;
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04);
        }
        .med-card {
            background: #ffffff;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 14px;
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04);
            transition: all 0.15s ease;
        }
        .med-card:hover {
            border-color: #cbd5e1;
            box-shadow: 0 6px 16px rgba(15, 23, 42, 0.07);
        }
        .med-status-taken { background: #dcfce7; color: #15803d; border: 1px solid #86efac; }
        .med-status-missed { background: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; }
        .med-status-pending { background: #fef3c7; color: #b45309; border: 1px solid #fde68a; }
        .med-status-completed { background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }
        .diag-status-pending { background: #fef3c7; color: #b45309; border: 1px solid #fde68a; }
        .diag-status-scheduled { background: #e0f2fe; color: #0369a1; border: 1px solid #7dd3fc; }
        .diag-status-completed { background: #dcfce7; color: #15803d; border: 1px solid #86efac; }
        .med-badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 9999px;
            font-size: 0.76rem;
            font-weight: 700;
        }
        .med-tag {
            display: inline-block;
            background: #f8fafc;
            color: #475569;
            border: 1px solid #e2e8f0;
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 0.74rem;
            font-weight: 600;
            margin-right: 4px;
        }
        </style>
    """, unsafe_allow_html=True)

    # Top Header Banner
    st.markdown("""
        <div class="med-header-banner">
            <div class="med-header-title">💊 Prescribed Medicines & Diagnostic Laboratory Care</div>
            <div style="font-size: 0.92rem; color: #475569; line-height: 1.45;">
                Track current prescribed maternal medications, daily dosage reminders, intake logs, and recommended trimester diagnostic investigations.
                <br><b>ℹ️ [DEMO DATA]</b> Demonstration maternal prescriptions from verified public health protocols.
            </div>
        </div>
    """, unsafe_allow_html=True)

    # Mandatory Medical Safety Notice
    st.markdown("""
        <div class="med-safety-alert">
            <b>🛡️ IMPORTANT CLINICAL SAFETY NOTICE:</b>
            <br>Do NOT recommend, self-prescribe, alter, or discontinue prescribed maternal medications without direct consultation with an authorized Medical Officer or Obstetrician. All medicine records must originate from a verified doctor's prescription.
        </div>
    """, unsafe_allow_html=True)

    # Patient Context Determination
    patient_id = "001"
    mother_name = "Pregnant Mother"
    week = 24
    trimester = "2nd Trimester"

    user_info = st.session_state.get('user', {})
    if isinstance(user_info, dict):
        if user_info.get('unique_id'):
            patient_id = str(user_info['unique_id'])
        if user_info.get('name'):
            mother_name = str(user_info['name'])
    elif st.session_state.get('unique_id'):
        patient_id = str(st.session_state.get('unique_id'))
        mother_name = str(st.session_state.get('mother_name', 'Pregnant Mother'))

    try:
        m_id = int(patient_id)
        if 1 <= m_id <= 40:
            week = 4 + ((m_id * 7) % 36)
        else:
            week = 24
    except ValueError:
        week = 24
    trimester = "1st Trimester" if week <= 12 else ("2nd Trimester" if week <= 27 else "3rd Trimester")

    if role != "Mother":
        c_pat1, _ = st.columns([2, 3])
        with c_pat1:
            searched_pat_id = st.text_input("Patient / Mother ID", value=patient_id, help="Lookup prescriptions for Mother ID")
            if searched_pat_id.strip():
                patient_id = searched_pat_id.strip()

    # Load Patient Prescriptions & Diagnostics
    prescriptions = MedicineService.list_patient_prescriptions(patient_id)
    current_prescriptions = [p for p in prescriptions if p['is_current']]
    history_prescriptions = [p for p in prescriptions if not p['is_current']]
    
    diagnostics = DiagnosticService.list_patient_diagnostics(patient_id)
    pending_diagnostics = [d for d in diagnostics if d['status'] in ['Pending', 'Scheduled']]
    completed_diagnostics = [d for d in diagnostics if d['status'] == 'Completed']

    # Prominent Dashboard Summary Counters
    med_taken_count = sum(1 for p in current_prescriptions if p['taken_status'] == 'Taken')
    med_pending_count = sum(1 for p in current_prescriptions if p['taken_status'] == 'Pending')
    med_missed_count = sum(1 for p in current_prescriptions if p['taken_status'] == 'Missed')

    sum_col1, sum_col2, sum_col3 = st.columns(3)
    with sum_col1:
        st.metric("💊 Today's Medicines", f"{med_taken_count}/{len(current_prescriptions)} Taken", f"{med_pending_count} Pending")
    with sum_col2:
        st.metric("🔬 Diagnostic Tests", f"{len(pending_diagnostics)} Due / Scheduled", f"{len(completed_diagnostics)} Completed")
    with sum_col3:
        st.metric("🤰 Gestational Stage", f"Week {week}", trimester)

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

    # Main Tabs: Medicines & Diagnostics
    tab_meds, tab_diags = st.tabs([
        f"💊 Prescribed Medicines ({len(current_prescriptions)})",
        f"🔬 Diagnostic Tests & Reports ({len(diagnostics)})"
    ])

    # ---------------- TAB 1: MEDICINES SECTION ----------------
    with tab_meds:
        st.markdown("### 📋 Current Prescriptions & Daily Schedule")
        
        if not current_prescriptions:
            st.info(f"No active prescriptions found for Patient ID: **{patient_id}**.")
        else:
            for med in current_prescriptions:
                status = med['taken_status']
                status_class = f"med-status-{status.lower()}"
                
                with st.container():
                    st.markdown(f"""
                        <div class="med-card">
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
                                <div>
                                    <span style="font-size: 0.78rem; font-weight: 700; color: #64748b; text-transform: uppercase;">Prescription ID:</span>
                                    <code style="font-weight: 700; font-size: 0.86rem; color: #0f172a;">{med['prescription_id']}</code>
                                </div>
                                <span class="med-badge {status_class}">
                                    ● {status} Today
                                </span>
                            </div>
                            <div style="font-size: 1.12rem; font-weight: 700; color: #0f172a; margin-bottom: 4px;">
                                {med['medicine_name']}
                            </div>
                            <div style="font-size: 0.86rem; color: #0284c7; font-weight: 600; margin-bottom: 6px;">
                                🎯 <b>Indication:</b> {med['purpose']}
                            </div>
                            <div style="display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px;">
                                <span class="med-tag">💊 <b>Dosage:</b> {med['dosage']}</span>
                                <span class="med-tag">⏰ <b>Frequency:</b> {med['frequency']}</span>
                                <span class="med-tag">⏳ <b>Duration:</b> {med['duration']}</span>
                                <span class="med-tag">🕒 <b>Time:</b> {med['schedule_time']}</span>
                            </div>
                            <div style="background: #f8fafc; border-left: 3px solid #0284c7; padding: 6px 12px; font-size: 0.82rem; color: #334155; margin-bottom: 8px;">
                                🍽️ <b>Food Instruction:</b> {med['food_instruction']}
                            </div>
                            <div style="font-size: 0.78rem; color: #64748b;">
                                👨‍⚕️ <b>Prescribed by:</b> {med['doctor_name']} &nbsp;|&nbsp; 🏥 {med['facility_name']} (Date: {med['prescribed_date']})
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

                    # Interactive Intake Status Action Buttons
                    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 1])
                    with btn_col1:
                        if st.button("✅ Mark as Taken", key=f"btn_taken_{med['prescription_id']}", use_container_width=True):
                            MedicineService.update_taken_status(med['prescription_id'], "Taken")
                            st.success(f"Marked {med['medicine_name']} as Taken today!")
                            st.rerun()
                    with btn_col2:
                        if st.button("❌ Mark as Missed", key=f"btn_missed_{med['prescription_id']}", use_container_width=True):
                            MedicineService.update_taken_status(med['prescription_id'], "Missed")
                            st.warning(f"Marked {med['medicine_name']} as Missed today.")
                            st.rerun()
                    with btn_col3:
                        if st.button("🔄 Reset Status", key=f"btn_reset_{med['prescription_id']}", use_container_width=True):
                            MedicineService.update_taken_status(med['prescription_id'], "Pending")
                            st.rerun()

        # Prescription History Expander
        if history_prescriptions:
            st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
            with st.expander(f"📜 View Prescription History & Completed Courses ({len(history_prescriptions)})"):
                for p in history_prescriptions:
                    st.markdown(f"**{p['medicine_name']}** (`{p['dosage']}` - {p['frequency']})")
                    st.markdown(f"- **Purpose:** {p['purpose']}")
                    st.markdown(f"- **Prescribed by:** {p['doctor_name']} | Date: {p['prescribed_date']}")
                    st.markdown(f"- **Status:** Completed Course")
                    st.divider()

        # Public Health Facility Medicine Stock Checker
        st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
        with st.expander("🔍 Search Medicine Availability across Public Health Centres"):
            st.markdown("Check government drug inventory at nearby Primary & Community Health Centres:")
            med_q = st.text_input("Search Medicine Name (e.g., Paracetamol, Iron, Calcium, Oxytocin)", key="med_search_box")
            med_results = MedicineService.search_medicine(med_q.strip())
            if med_results:
                df_res = pd.DataFrame(med_results)
                st.dataframe(df_res[['item_id', 'item_name', 'generic_name', 'facility_id', 'quantity', 'status']], use_container_width=True, hide_index=True)
            else:
                st.info("No medicine stock records found.")

    # ---------------- TAB 2: DIAGNOSTICS SECTION ----------------
    with tab_diags:
        st.markdown("### 🔬 Recommended Diagnostic Investigations & Reports")
        
        # Pending & Scheduled Tests
        st.markdown("#### ⏳ Recommended & Scheduled Tests")
        if not pending_diagnostics:
            st.info("No pending diagnostic investigations. All recommended tests are up to date!")
        else:
            for diag in pending_diagnostics:
                d_status = diag['status']
                d_status_class = f"diag-status-{d_status.lower()}"
                
                with st.container():
                    st.markdown(f"""
                        <div class="med-card">
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
                                <div>
                                    <span style="font-size: 0.78rem; font-weight: 700; color: #64748b; text-transform: uppercase;">Test ID:</span>
                                    <code style="font-weight: 700; font-size: 0.86rem; color: #0f172a;">{diag['test_id']}</code>
                                </div>
                                <span class="med-badge {d_status_class}">
                                    ● {d_status}
                                </span>
                            </div>
                            <div style="font-size: 1.1rem; font-weight: 700; color: #0f172a; margin-bottom: 4px;">
                                {diag['test_name']}
                            </div>
                            <div style="font-size: 0.86rem; color: #0284c7; font-weight: 600; margin-bottom: 6px;">
                                🎯 <b>Clinical Reason:</b> {diag['reason']}
                            </div>
                            <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px;">
                                <span class="med-tag">📅 <b>Recommended Date:</b> {diag['recommended_date']}</span>
                                <span class="med-tag">👨‍⚕️ <b>Requested by:</b> {diag['doctor_name']}</span>
                                <span class="med-tag">🏥 <b>Designated Facility:</b> {diag['facility_name']}</span>
                            </div>
                            <div style="background: #f8fafc; border-left: 3px solid #0d9488; padding: 6px 12px; font-size: 0.82rem; color: #334155; margin-bottom: 6px;">
                                📋 <b>Status Details:</b> {diag['result_summary']}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

                    # Action row: Connect with Appointments & Upload Report
                    d_col1, d_col2 = st.columns(2)
                    with d_col1:
                        if st.button(f"📅 Book Appointment for {diag['test_id']}", key=f"btn_book_diag_{diag['test_id']}", use_container_width=True):
                            st.session_state['selected_booking_facility'] = diag['facility_id'] if diag.get('facility_id') else "FAC-CHC-001"
                            st.session_state['mother_page'] = "Appointments"
                            st.success(f"Navigating to Appointments with pre-selected facility: {diag['facility_name']}")
                            st.rerun()

                    with d_col2:
                        with st.expander(f"📤 Upload Lab Report ({diag['test_id']})"):
                            up_file = st.file_uploader("Upload Diagnostic Report (PDF / Image)", type=["pdf", "png", "jpg", "jpeg"], key=f"up_{diag['test_id']}")
                            summary_input = st.text_area("Doctor's Findings / Summary", value=diag['result_summary'], key=f"sum_{diag['test_id']}")
                            if st.button("Submit & Verify Report", key=f"btn_sub_{diag['test_id']}", type="primary"):
                                file_name = up_file.name if up_file else f"report_{diag['test_id']}.pdf"
                                DiagnosticService.upload_diagnostic_report(diag['test_id'], file_name, summary_input)
                                st.success("Diagnostic report uploaded and marked as Completed!")
                                st.rerun()

        # Completed Diagnostic Test Reports
        st.markdown("<div style='height: 14px;'></div>", unsafe_allow_html=True)
        st.markdown("#### 📜 Completed Diagnostic Test Reports")
        if not completed_diagnostics:
            st.info("No completed diagnostic reports recorded yet.")
        else:
            for diag in completed_diagnostics:
                with st.container():
                    st.markdown(f"""
                        <div class="med-card" style="border-left: 4px solid #10b981;">
                            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px;">
                                <div>
                                    <span style="font-size: 0.78rem; font-weight: 700; color: #64748b; text-transform: uppercase;">Test ID:</span>
                                    <code>{diag['test_id']}</code>
                                </div>
                                <span class="med-badge diag-status-completed">
                                    ✅ Completed ({diag['completed_date']})
                                </span>
                            </div>
                            <div style="font-size: 1.05rem; font-weight: 700; color: #0f172a; margin-bottom: 4px;">
                                {diag['test_name']}
                            </div>
                            <div style="font-size: 0.84rem; color: #475569; margin-bottom: 6px;">
                                🏥 <b>Facility:</b> {diag['facility_name']} &nbsp;|&nbsp; 👨‍⚕️ <b>Consultant:</b> {diag['doctor_name']}
                            </div>
                            <div style="background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 8px; padding: 10px 14px; font-size: 0.84rem; color: #065f46; margin-bottom: 8px;">
                                📊 <b>Test Result Summary:</b><br>{diag['result_summary']}
                            </div>
                            <div style="font-size: 0.8rem; color: #64748b;">
                                📄 <b>Attached File:</b> <code>{diag['report_file_name'] or 'verified_clinical_report.pdf'}</code>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)

        # Public Health Facility Diagnostic Services Directory
        st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
        with st.expander("🔍 Search Diagnostic Tests across Public Health Facilities"):
            st.markdown("Search diagnostic tests & equipment availability across District Hospitals and CHCs:")
            diag_q = st.text_input("Search Test or Scan (e.g., Ultrasound, CBC, Blood Group, MRI, X-Ray)", key="diag_search_box")
            diag_results = DiagnosticService.search_diagnostic(diag_q.strip())
            if diag_results:
                df_diag = pd.DataFrame(diag_results)
                st.dataframe(df_diag[['item_id', 'item_name', 'category', 'facility_id', 'status']], use_container_width=True, hide_index=True)
            else:
                st.info("No diagnostic services found.")


def render_timeline(role):
    st.info("Unified Patient Timeline combining Legacy data and new records.")
    
    pat_id = st.text_input("Enter Patient ID (e.g. 001)")
    if pat_id:
        try:
            timeline = PatientTimelineService.get_patient_timeline(pat_id)
            if timeline:
                df = pd.DataFrame(timeline)
                # Render beautifully
                for _, row in df.iterrows():
                    st.markdown(f"**{row['timestamp']}** | 🏷️ `{row['event_type']}` | 🏥 `{row['source']}`")
                    st.markdown(f"> {row['details']}")
                    st.divider()
            else:
                st.info("No timeline events found for this patient.")
        except Exception as e:
            st.error(f"Error fetching timeline: {e}")

def render_fhir(role):
    st.info("📄 FHIR-READY EXPORT - This generates a structured FHIR-ready record. It does not submit data to a live health-information network.")
    
    pat_id = st.text_input("Enter Patient ID for FHIR Export (e.g. 001)")
    if pat_id:
        if st.button("Generate FHIR Bundle"):
            try:
                bundle = FHIRMapper.generate_patient_bundle(pat_id)
                st.success("Successfully generated FHIR Bundle!")
                st.json(bundle)
                
                json_str = json.dumps(bundle, indent=2)
                st.download_button("Download FHIR JSON", data=json_str, file_name=f"fhir_bundle_{pat_id}.json", mime="application/json")
            except Exception as e:
                st.error(f"Error generating FHIR: {e}")
