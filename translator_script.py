import os
import time
import pprint
from deep_translator import GoogleTranslator

english_translations = {
    "app_title": "MAATRI SURAKSHA AI",
    "app_subtitle": "AI-Powered Rural Maternal Health Companion",
    "emergency_badge": "🚑 Emergency: 108",
    "secure_portal_heading": "Secure Patient Portal",
    "select_role": "👥 Select Role",
    "role_mother": "Mother",
    "role_asha": "ASHA Worker",
    "unique_id_label": "🆔 Unique ID",
    "unique_id_placeholder": "Enter your ASHA assigned ID (e.g. M-001)",
    "full_name_label": "👤 Full Name",
    "full_name_placeholder": "Enter your registered name",
    "phone_number": "📱 Phone Number",
    "password": "🔒 Password",
    "login_btn": "Login",
    "logout_btn": "🔓 Logout",
    "lang_toggle": "🌐 Language Toggle",
    "main_menu": "MAIN MENU",
    "monitoring_menu": "MONITORING MENU",
    "error_id_name_missing": "⚠️ Please enter both Unique ID and Name.",
    
    # Mother Dashboard
    "mother_portal": "🤰 Mother's Portal",
    "nav_overview": "Dashboard Overview",
    "nav_log": "Daily Health Log",
    "nav_voice": "Voice Input",
    "nav_food": "Food & Nutrition",
    "nav_planner": "AI Food Planner",
    "nav_mood": "Mood Tracker",
    "nav_risk": "AI Risk Panel",
    "nav_map": "Live Location & Map",
    "nav_emergency": "Emergency Help",
    "nav_reminders": "Health Reminders",
    "nav_journey": "Pregnancy Journey",
    
    # Pregnancy Journey
    "journey_title": "Pregnancy Journey Tracker",
    "journey_desc": "Track your baby's growth and development week by week.",
    "select_week_label": "Select Pregnancy Week",
    "baby_size_label": "Baby's Size",
    "baby_dev_label": "Baby's Development",
    "mother_tip_label": "Mother Care Tip",
    "week_label": "Week",
    
    # Health Reminders
    "reminders_main_title": "Smart Pregnancy Health Reminders",
    "reminders_main_desc": "AI-assisted reminders to support safe pregnancy habits and regular medical care.",
    "daily_reminders_title": "Daily Health Reminders",
    "medical_reminders_title": "Upcoming Medical Reminders",
    "ai_recommendation_title": "AI Recommendation Panel",
    "rem_iron": "Iron Tablets",
    "rem_iron_desc": "Take your iron supplement after lunch for better absorption.",
    "rem_calcium": "Calcium Tablets",
    "rem_calcium_desc": "Take Calcium in the evening. Avoid taking with Iron.",
    "rem_folic": "Folic Acid",
    "rem_folic_desc": "Essential for baby's neural development.",
    "rem_vit_d": "Vitamin D",
    "rem_vit_d_desc": "Supports bone health for both you and the baby.",
    "rem_water": "Hydration",
    "rem_water_desc": "Drink at least 8-10 glasses of water daily.",
    "rem_food": "Nutritious Food",
    "rem_food_desc": "Eat iron-rich foods like spinach and lentils.",
    "rem_exercise": "Light Exercise",
    "rem_exercise_desc": "Light walking or gentle exercise for 20 minutes.",
    "rem_rest": "Rest & Stress Control",
    "rem_rest_desc": "Maintain proper rest and keep stress levels low.",
    "med_anc": "ANC Checkup",
    "med_anc_rem": "ANC Checkup Tomorrow",
    "med_ultrasound": "Ultrasound Scan",
    "med_ultrasound_rem": "Ultrasound Scan in 3 Days",
    "med_vaccination": "Vaccination",
    "med_vaccination_rem": "Vaccination Due Next Week",
    "ai_rec_panel_msg": "Based on your recent health logs, maintaining hydration and taking iron supplements regularly will help maintain healthy hemoglobin levels.",
    "btn_taken": "Taken Iron Tablet",
    "btn_remind": "Remind Later",
    "rem_completed_msg": "✅ Reminder marked as completed.",
    
    "welcome_back": "Namaste! Here is your daily health summary.",
    "current_risk": "Current Risk Level",
    "last_log": "Last Health Log",
    "ai_suggestion": "💡 AI Health Suggestion",
    "risk_low": "🟢 Low Risk",
    "risk_med": "🟡 Medium Risk",
    "risk_high": "🔴 High Risk",
    "normal_today": "Everything looks normal today.",
    "logged_auto": "Logged Automatically",
    "hydration_tip": "Stay hydrated! Drink at least 8 glasses of water today to help with your mild headache.",
    
    # Health Log
    "log_title": "📝 Daily Health Log",
    "log_desc": "Please select any symptoms you are feeling today.",
    "sym_headache": "🤕 Headache",
    "sym_swelling": "🦶 Swelling in hands/feet",
    "sym_dizziness": "💫 Dizziness",
    "sym_fetal": "👶 Reduced fetal movement",
    "sym_bleeding": "🩸 Bleeding or Spotting",
    "other_symptoms": "Any other symptoms?",
    "other_symptoms_placeholder": "Type anything else you are worried about here...",
    "submit_log": "Submit Health Log",
    "success_analyzed_low": "✅ Log saved successfully! AI Analysis: Your risk remains LOW.",
    
    # Voice Input
    "voice_input_title": "🎤 Voice Input",
    "voice_desc": "Find it hard to type? Just speak your symptoms to us.",
    "audio_input_label": "Record your symptoms here:",
    "transcription_label": "Live Transcription",
    "btn_send_ai": "Send to AI Engine",
    "err_record_first": "Please record audio first.",
    "success_analyzed_voice": "✅ Symptoms analyzed successfully.",
    "processing_audio": "Processing audio with AI...",
    "err_audio_fail": "Audio could not be understood. Please try again.",
    
    # Food & Nutrition
    "food_title": "🍎 Food & Nutrition",
    "food_desc": "Keep track of your meals and hydration.",
    "nutri_reminder": "👩‍⚕️ Reminder: Include ample iron-rich (spinach, beans) and protein-rich (eggs, lentils) foods!",
    "water_intake_sub": "💧 Water Intake",
    "water_slider_label": "Glasses of water today:",
    "food_intake_sub": "🍽️ Food Intake",
    "food_placeholder": "E.g., 2 rotis with dal and spinach...",
    "btn_save_nutri": "Save Nutrition Log",
    "err_low_water": "⚠️ Warning: You only drank {0} glasses. Please drink at least 8-10 glasses!",
    "success_nutri": "✅ Nutrition logged! Great job drinking {0} glasses of water.",
    
    # Food Planner
    "ai_planner_title": "🥗 Personalized Nutrition AI",
    "ai_planner_desc": "Smart meal plans tailored for your maternal health journey.",
    "planner_title": "🤖 AI Food Planner",
    "planner_desc": "Personalized weekly nutrition schedule.",
    "diet_pref_label": "Select Diet Preference:",
    "veg": "Vegetarian",
    "non_veg": "Non-Vegetarian",
    "day_select_label": "Select Day to View:",
    "morning_routine": "🌅 Morning Routine",
    "afternoon_lunch": "☀️ Afternoon Lunch",
    "night_dinner": "🌙 Night Dinner",
    "warm_water": "Warm water with lemon",
    "prenatal_vits": "Prenatal Vitamins",
    "fresh_greens": "Fresh Greens (Iron focus)",
    "curd": "Curd (Calcium)",
    "easy_digest": "Easily digestible side",
    "warm_milk": "Warm Milk before sleep",
    
    "day_monday": "Monday",
    "day_tuesday": "Tuesday",
    "day_wednesday": "Wednesday",
    "day_thursday": "Thursday",
    "day_friday": "Friday",
    "day_saturday": "Saturday",
    "day_sunday": "Sunday",
    
    "meal_oatmeal_almonds": "Oatmeal & Almonds",
    "meal_dal_roti_spinach": "Dal, Roti, Spinach",
    "meal_khichdi_veg": "Khichdi & Mixed Veg",
    "meal_boiled_eggs_toast": "Boiled Eggs & Toast",
    "meal_chicken_curry_rice": "Chicken Curry & Rice",
    "meal_light_soup_salad": "Light Soup & Salad",
    "meal_poha_peanut": "Poha & Peanut",
    "meal_rajma_rice": "Rajma & Brown Rice",
    "meal_paneer_sabzi_roti": "Paneer Sabzi & Roti",
    "meal_omelette_roti": "Omelette & Roti",
    "meal_fish_curry_quinoa": "Fish Curry & Quinoa",
    "meal_grilled_chicken_salad": "Grilled Chicken Salad",
    "meal_idli_sambar": "Idli & Sambar",
    "meal_chana_masala_roti": "Chana Masala & Roti",
    "meal_veg_pulao_raita": "Veg Pulao with Raita",
    "meal_egg_bhurji": "Egg Bhurji",
    "meal_mutton_stew": "Mutton Stew",
    "meal_chicken_clear_soup": "Chicken Clear Soup",
    "meal_upma_veggies": "Upma & Veggies",
    "meal_kadhi_pakora_rice": "Kadhi Pakora & Rice",
    "meal_dalia": "Dalia (Cracked Wheat)",
    "meal_egg_curry_rice": "Egg Curry & Rice",
    "meal_grilled_fish": "Grilled Fish",
    "meal_besan_chilla": "Besan Chilla",
    "meal_aloo_gobi_roti": "Aloo Gobi & Roti",
    "meal_lentil_soup": "Lentil Soup",
    "meal_chicken_sausages": "Chicken Sausages",
    "meal_chicken_biryani": "Chicken Biryani (Light)",
    "meal_mutton_soup": "Mutton Soup",
    "meal_stuffed_paratha": "Stuffed Paratha (Light)",
    "meal_mushroom_curry": "Mushroom Curry",
    "meal_veg_stew": "Vegetable Stew",
    "meal_scrambled_eggs": "Scrambled Eggs",
    "meal_fish_fry": "Fish Fry (shallow)",
    "meal_chicken_salad": "Chicken Salad",
    "meal_smoothie_bowl": "Fruit Smoothie Bowl",
    "meal_paneer_biryani": "Special Paneer Biryani",
    "meal_tomato_soup": "Light Tomato Soup",
    "meal_egg_sandwich": "Egg Sandwich",
    "meal_sunday_chicken": "Sunday Special Chicken",
    
    # Mood Tracker
    "mood_title": "😊 Mood Tracker",
    "mood_desc": "How are you feeling mentally today?",
    "mood_select_label": "Select Current Mood",
    "happy": "Happy",
    "normal": "Normal",
    "stressed": "Stressed",
    "very_sad": "Very Sad",
    "msg_happy": "We are so glad you are feeling well! Keep up the positive energy.",
    "msg_stressed": "It's completely normal to feel stressed. Try taking 5 deep breaths.",
    "msg_sad": "We're sorry you're feeling down. Please reach out to your ASHA worker.",
    
    # AI Risk Panel
    "risk_panel_title": "📊 AI Risk Result Panel",
    "risk_panel_desc": "Simulate real-time sensor processing and see how the AI engine analyzes metrics.",
    "btn_start_ai": "🔴 Start Live AI Risk Analysis",
    "msg_simulate_vitals": "Click 'Start Live AI Risk Analysis' to simulate vitals monitoring.",
    "status_monitoring": "Monitoring: Actively reading sensors... 🔄",
    "escalation_status": "Escalation Status: Analyzing condition...",
    "bp_label": "Blood Pressure",
    "swelling_label": "Swelling",
    "fetal_label": "Fetal Movement",
    "stress_label": "Stress",
    "final_assessment_title": "Final Assessment: {0}",
    "final_score": "Score: {0}/100",
    "final_recommendation": "Recommendation: {0}",
    "final_escalation_low": "Escalation Status: Not Escalated - Notified local ASHA worker.",
    
    # Map
    "map_title_page": "📍 Live Location & Nearest PHC",
    "map_desc_page": "Share your live location to see the nearest Primary Health Center (PHC).",
    "success_loc_captured": "Location captured successfully!",
    "nearest_phc_info": "🏥 Your Nearest Health Center is **{0}** ({1:.1f} km away)",
    "err_high_risk_map": "🚨 HIGH RISK ALERT: Please seek immediate medical attention.",
    "map_user_loc": "Your Location",
    "err_loc_permission": "Please allow location access to continue.",
    
    # Emergency
    "emergency_title": "🚨 Emergency Help",
    "emergency_desc": "⚠️ Press only in case of serious symptoms (Severe bleeding, extreme pain).",
    "btn_trigger_emergency": "🆘 TRIGGER EMERGENCY HELP NOW",
    "emergency_initiated_sms": "✅ Emergency SMS Alert dispatched to your ASHA worker.",
    
    # ASHA Dashboard
    "asha_district": "District: Rural Sector 4",
    "asha_overview": "Dashboard Overview",
    "asha_heatmap": "Geospatial Heatmap",
    "asha_register": "Register Mother",
    "asha_alerts": "High Risk Alerts",
    "asha_all": "All Mothers",
    "asha_trends": "Risk Trends",
    "asha_search": "Search Mother",
    "asha_heatmap_title": "🌍 Geospatial Heatmap & Tracking",
    "asha_heatmap_desc": "Live interactive map of all mothers showing risk levels.",
    "fetching_geodata": "Fetching latest geospatial data...",
    "err_no_mothers": "No mothers found in database. Please register first.",
    "err_no_locations": "No mothers have shared their location yet.",
    "popup_village": "Village",
    "popup_risk": "Risk Level",
    "popup_score": "Risk Score",
    "popup_updated": "Last Updated",
    "map_focus_msg": "📍 Map is focus on Mother ID: {0}",
    "btn_clear_focus": "Clear Focus",
    
    "asha_alerts_title": "🚨 High Risk Alerts",
    "asha_alerts_desc": "ACTION REQUIRED: Visit or contact these mothers immediately.",
    "col_alert_id": "Alert ID",
    "col_mother_id": "Mother ID",
    "col_village": "Village",
    "col_risk_level": "Risk Level",
    "col_risk_score": "Risk Score",
    "col_date": "Date",
    "col_alert_status": "Alert Status",
    "select_focus_mother": "Select High-Risk Mother:",
    "btn_view_map": "🌍 View on Heatmap",
    "col_view_map": "View Map",
    "btn_see_map": "📍 See Map",
    "help_see_map": "Click to open full Geospatial Heatmap",
    "btn_open_full_map": "🌍 Open Full Geospatial Heatmap",
    "resolve_alerts_sub": "### Resolve Alerts",
    "select_resolve_id": "Select Mother ID to mark as resolved:",
    "btn_mark_resolved": "✅ Mark as Resolved",
    "success_resolved": "Alert for {0} marked as resolved. Database updated.",
    
    "asha_all_mothers_title": "👩 All Monitored Mothers",
    "asha_all_mothers_desc": "Complete directory of assigned cases.",
    "err_no_mothers_reg": "No mothers registered yet.",
    "filter_risk_label": "Filter by Risk Level:",
    "show_all": "Show All",
    "sort_order_label": "Sort Order:",
    "high_first": "Highest Risk First",
    "low_first": "Lowest Risk First",
    
    "asha_trends_title": "📈 Risk Score Trends",
    "asha_trends_desc": "View historical risk data for a specific mother.",
    "enter_mother_id": "Enter Mother ID (e.g., M-8042):",
    "btn_gen_chart": "Generate Trend Chart",
    "chart_title_trend": "14-Day Risk Trend for {0}",
    "xaxis_date": "Date",
    "yaxis_score": "Risk Score (0-100)",
    "med_threshold": "Medium Risk Threshold",
    "high_threshold": "High Risk Threshold",
    
    "asha_search_title": "🔍 Search Mother Record",
    "scan_id_placeholder": "M-XXXX",
    "scan_id_label": "Scan or Enter Mother ID:",
    "btn_fetch_records": "Fetch Records",
    "err_enter_id": "Please enter an ID.",
    "fetching_db": "Querying database...",
    "record_found": "Record found for {0}",
    "recent_summary_sub": "📝 Most Recent Health Summary",
    "last_checked": "Last Checked",
    "ai_note_label": "AI Note",
    "search_risk_score": "Current Risk Score",
    "search_symptoms": "Reported Symptoms",
    
    "asha_register_title": "📝 Register New Mother",
    "asha_register_desc": "Create a new patient record with a Unique ID.",
    "new_id_label": "🆔 Assign Unique ID *",
    "new_id_placeholder": "e.g. M-001 (Must be unique)",
    "new_name_label": "👤 Full Name *",
    "new_name_placeholder": "Mother's name",
    "new_phone_label": "📱 Phone Number",
    "new_phone_placeholder": "10-digit mobile number",
    "new_village_label": "🏘️ Village *",
    "new_village_placeholder": "Village name",
    "btn_register_mother": "Register Mother",
    "err_fill_all_req": "⚠️ Please fill in all required fields marked with *.",
    "success_reg_mother": "✅ Successfully registered {0} with ID {1}!",
    "err_id_taken_msg": "❌ ID '{0}' is already taken. Please assign a different ID.",
    
    "footer_rights": "© 2026 MAATRI SURAKSHA AI. All Rights Reserved.",
    "footer_privacy": "Privacy Policy",
    "footer_terms": "Terms of Service",
    "footer_help": "Help Center",
    "offline_save_msg": "📡 No internet connection detected. Your data has been saved offline and will be synchronized when the network is available.",
    "sync_success_msg": "✅ Offline data successfully synchronized with the central health monitoring system.",
    "offline_feature_warning": "📡 This feature requires internet. It will be executed once connectivity is restored.",
    "allow_location_warning": "⚠️ Please allow location access in your browser to use this feature."
}

languages = {
    "Tamil": "ta", "Kannada": "kn", "Malayalam": "ml",
    "Bengali": "bn", "Marathi": "mr", "Urdu": "ur",
    "Gujarati": "gu", "Odia": "or", "Punjabi": "pa"
}
    
all_translations = {}

def chunk_list(l, n):
    for i in range(0, len(l), n):
        yield l[i:i + n]

for lang_name, lang_code in languages.items():
    print(f"Translating {lang_name}...")
    translated_dict = {}
    translator = GoogleTranslator(source='en', target=lang_code)
    
    keys = list(english_translations.keys())
    values = list(english_translations.values())
    
    # Process in chunks of 50 to avoid hanging
    for i in range(0, len(values)):
        try:
            val = translator.translate(values[i])
            if val:
                val = val.replace(' {0}', '{0}').replace('{ 0 }', '{0}').replace('{0} ', '{0}')
                translated_dict[keys[i]] = val
            else:
                translated_dict[keys[i]] = values[i]
        except Exception as e:
            print(f"Error translating {keys[i]} in {lang_name}: {e}")
            translated_dict[keys[i]] = values[i]
        
        # print progress after every 50
        if i % 50 == 0:
            print(f"  Processed {i}/{len(values)}")
            
    all_translations[lang_name] = translated_dict
    time.sleep(1)

with open("new_translations_generated.py", "w", encoding="utf-8") as f:
    f.write("NEW_TRANSLATIONS = ")
    f.write(pprint.pformat(all_translations, indent=4, width=120))
    f.write("\n")

print("Done translating all.")
