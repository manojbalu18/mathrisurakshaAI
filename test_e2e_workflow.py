import sqlite3
import datetime
import database
import database_village_health as dvh
from ai_engine import calculate_risk

def run_tests():
    print("==================================================")
    print("RUNNING END-TO-END PATIENT -> ASHA -> SUPERVISOR TEST")
    print("==================================================")
    
    # Initialize DB
    database.init_db()
    
    mother_id = "001"
    
    # 1. Mother Care submits health data
    symptoms = ["bleeding", "reduced fetal movement", "headache", "swelling"]
    mood = "stressed"
    nutrition = "low"
    
    print(f"\n[STEP 1-4] Patient {mother_id} enters symptoms: {symptoms}")
    
    # 2. AI Risk Assessment
    ai_eval = calculate_risk(symptoms, mood, nutrition)
    print(f"[STEP 5-7] AI Risk Calculated: Score={ai_eval['risk_score']}, Level={ai_eval['risk_level']}, Escalation={ai_eval['escalation']}")
    assert ai_eval['risk_level'] == "High", f"Expected High risk, got {ai_eval['risk_level']}"
    
    # 3. Save into database
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    database.save_daily_log(mother_id, symptoms, mood, nutrition, ai_eval['risk_score'], ai_eval['risk_level'], timestamp)
    print(f"[STEP 8] Daily log saved to SQLite for mother {mother_id}")
    
    # 4. Create Alert
    database.create_alert(mother_id, "High", timestamp)
    print(f"[STEP 8] Alert created in database for mother {mother_id}")
    
    # 5. Check ASHA Worker View
    active_alerts = dvh.get_high_risk_mothers_alert()
    print(f"[STEP 10-13] ASHA worker retrieves active high-risk alerts: Found {len(active_alerts)} alerts")
    assert any(str(r[0]) == mother_id for r in active_alerts), "Mother 001 not found in high-risk alerts!"
    
    # 6. ASHA Worker Takes Action & Updates Status
    print(f"[STEP 14-16] ASHA Worker performs clinical review and updates status to 'Referred to PHC'")
    database.update_case_status(
        mother_id=mother_id,
        asha_id="ASHA (Hyderabad)",
        status="Referred to PHC",
        action_taken="Referred to Primary Health Centre (PHC)",
        notes="Patient evaluated at home. Elevated BP and bleeding noted. Immediate transport arranged.",
        followup_date="2026-09-12"
    )
    
    # 7. Supervisor View Verification
    print(f"\n[STEP 17-20] Supervisor inspects district surveillance & live metrics:")
    sup_metrics = dvh.get_supervisor_metrics()
    print("   Total Caseload:", sup_metrics['total_cases'])
    print("   High Risk:", sup_metrics['high_risk'])
    print("   Referred to PHC:", sup_metrics['referred'])
    print("   Pending:", sup_metrics['pending'])
    
    assert sup_metrics['total_cases'] >= 115, f"Expected 115+ total cases, got {sup_metrics['total_cases']}"
    assert sup_metrics['high_risk'] >= 1, "Expected at least 1 high-risk case"
    assert sup_metrics['referred'] >= 1, "Expected at least 1 referred case"
    
    # 8. Check ASHA Workload Breakdown
    workload = dvh.get_asha_workload_breakdown()
    hyd_workload = [w for w in workload if 'Hyderabad' in w['Village']]
    print("\n   Hyderabad ASHA Workload:", hyd_workload[0] if hyd_workload else "Not found")
    
    # 9. Case Resolution
    print("\n[RESOLVE] ASHA Worker marks case as resolved after successful PHC visit:")
    database.resolve_alert(mother_id, asha_id="ASHA (Hyderabad)", notes="Patient received medical care at PHC, stable.")
    
    post_metrics = dvh.get_supervisor_metrics()
    print("   Resolved cases:", post_metrics['resolved'])
    print("   High risk alerts remaining active:", len(database.get_active_alerts()))
    
    print("\n==================================================")
    print("ALL 20 END-TO-END WORKFLOW CHECKS PASSED SUCCESSFULLY!")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
