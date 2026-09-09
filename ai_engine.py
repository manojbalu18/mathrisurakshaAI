from datetime import datetime

def calculate_risk(symptoms, mood, nutrition):

    risk_score = 0

    # ---------------- SYMPTOM SCORING ----------------
    severe_symptoms = ["bleeding", "reduced fetal movement"]
    moderate_symptoms = ["headache", "swelling", "dizziness"]

    for symptom in symptoms:
        if symptom.lower() in severe_symptoms:
            risk_score += 40
        elif symptom.lower() in moderate_symptoms:
            risk_score += 20

    # ---------------- MOOD SCORING ----------------
    if mood.lower() == "very sad":
        risk_score += 20
    elif mood.lower() == "stressed":
        risk_score += 15

    # ---------------- NUTRITION SCORING ----------------
    if "no food" in nutrition.lower():
        risk_score += 20
    elif "low" in nutrition.lower():
        risk_score += 10

    # ---------------- RISK CLASSIFICATION ----------------
    if risk_score >= 60:
        risk_level = "High"
        recommendation = "Immediate medical attention required. Contact ASHA worker."
    elif risk_score >= 30:
        risk_level = "Medium"
        recommendation = "Monitor symptoms and consult ASHA worker."
    else:
        risk_level = "Low"
        recommendation = "Continue regular monitoring."

    # ---------------- ESCALATION FLAG ----------------
    escalation = True if risk_level == "High" else False

    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "recommendation": recommendation,
        "escalation": escalation,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }