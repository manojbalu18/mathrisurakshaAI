"""
SIH FHIR-ready Mapping Layer.
Provides structured EXPORT of patient timeline data to FHIR-like resources.
Note: This is an export layer and does not claim production ABDM connectivity.
"""
from typing import Dict, Any, List, Optional
import uuid
from .patient_timeline_service import PatientTimelineService
import sqlite3

class FHIRMapper:
    @staticmethod
    def build_patient_resource(patient_id: str, db_path: str) -> Dict[str, Any]:
        """Maps basic patient demographic info to a FHIR Patient resource."""
        name = "Unknown"
        phone = ""
        village = ""
        try:
            with sqlite3.connect(db_path, check_same_thread=False) as conn:
                c = conn.cursor()
                c.execute("SELECT name, phone, village FROM users WHERE unique_id = ? OR CAST(id AS TEXT) = ?", (patient_id, patient_id))
                row = c.fetchone()
                if row:
                    name = row[0]
                    phone = row[1]
                    village = row[2]
        except sqlite3.OperationalError:
            pass
            
        res = {
            "resourceType": "Patient",
            "id": f"patient-{patient_id}",
            "identifier": [
                {
                    "system": "https://maatrisuraksha.local/patient-id",
                    "value": patient_id
                }
            ],
            "active": True,
            "name": [
                {
                    "use": "official",
                    "text": name
                }
            ]
        }
        
        if phone:
            res["telecom"] = [
                {
                    "system": "phone",
                    "value": phone,
                    "use": "mobile"
                }
            ]
            
        if village:
            res["address"] = [
                {
                    "text": village
                }
            ]
            
        return res

    @staticmethod
    def map_event_to_resource(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Maps a timeline event to the appropriate FHIR resource type."""
        patient_ref = f"Patient/patient-{event['patient_id']}"
        
        if event["event_type"] == "DAILY_LOG":
            return {
                "resourceType": "Observation",
                "id": f"obs-{event['event_id']}",
                "status": "final",
                "code": {
                    "text": "Daily Health Log"
                },
                "subject": {"reference": patient_ref},
                "effectiveDateTime": event["event_date"],
                "valueString": event["description"]
            }
            
        if event["event_type"] == "ALERT":
            return {
                "resourceType": "Condition",
                "id": f"cond-{event['event_id']}",
                "clinicalStatus": {
                    "coding": [{"code": "active" if event["status"] == "Active" else "resolved"}]
                },
                "code": {
                    "text": event["title"]
                },
                "subject": {"reference": patient_ref},
                "recordedDate": event["event_date"]
            }
            
        if event["event_type"] == "APPOINTMENT":
            status_map = {
                "Scheduled": "booked",
                "Completed": "fulfilled",
                "Cancelled": "cancelled"
            }
            fhir_status = status_map.get(event["status"], "pending")
            return {
                "resourceType": "Appointment",
                "id": f"appt-{event['reference_id']}",
                "status": fhir_status,
                "description": event["description"],
                "start": event["event_date"],
                "participant": [
                    {
                        "actor": {"reference": patient_ref},
                        "status": "accepted"
                    }
                ]
            }
            
        if event["event_type"] == "TELECONSULTATION":
            status_map = {
                "REQUESTED": "planned",
                "IN_PROGRESS": "in-progress",
                "COMPLETED": "finished",
                "CANCELLED": "cancelled",
                "NO_SHOW": "cancelled"
            }
            return {
                "resourceType": "Encounter",
                "id": f"enc-{event['reference_id']}",
                "status": status_map.get(event["status"], "unknown"),
                "class": {
                    "code": "VR",
                    "display": "virtual"
                },
                "subject": {"reference": patient_ref},
                "reasonCode": [
                    {
                        "text": event.get("metadata", {}).get("reason", "Teleconsultation")
                    }
                ],
                "period": {
                    "start": event["event_date"]
                }
            }
            
        if event["event_type"] == "REFERRAL":
            return {
                "resourceType": "ServiceRequest",
                "id": f"sr-{event['reference_id']}",
                "status": "active" if event["status"] not in ["CLOSED", "CANCELLED"] else "completed",
                "intent": "order",
                "subject": {"reference": patient_ref},
                "reasonCode": [
                    {"text": event["description"]}
                ],
                "authoredOn": event["event_date"]
            }
            
        # Other types might not have direct FHIR mappings or we keep them as basic DocumentReference/Observation
        return {
            "resourceType": "Observation",
            "id": f"obs-{event['event_id']}",
            "status": "final",
            "code": {
                "text": event["title"]
            },
            "subject": {"reference": patient_ref},
            "effectiveDateTime": event["event_date"],
            "valueString": event["description"]
        }

    @staticmethod
    def build_patient_bundle(patient_id: str, db_path: str = None) -> Dict[str, Any]:
        """Builds a complete FHIR-style Bundle for the patient."""
        # Need a db path, fallback to maatrisuraksha.db
        actual_db_path = db_path or "maatrisuraksha.db"
        events = PatientTimelineService.get_patient_timeline(patient_id, db_path=actual_db_path)
            
        entries = []
        
        # Add Patient resource
        patient_resource = FHIRMapper.build_patient_resource(patient_id, actual_db_path)
        entries.append({
            "fullUrl": f"urn:uuid:{uuid.uuid4()}",
            "resource": patient_resource
        })
        
        # Add event resources
        for event in events:
            resource = FHIRMapper.map_event_to_resource(event)
            if resource:
                entries.append({
                    "fullUrl": f"urn:uuid:{uuid.uuid4()}",
                    "resource": resource
                })
                
        return {
            "resourceType": "Bundle",
            "id": str(uuid.uuid4()),
            "type": "collection",
            "timestamp": "2024-01-01T00:00:00Z",
            "entry": entries
        }

    @staticmethod
    def validate_basic_structure(resource: Dict[str, Any]) -> bool:
        """Basic validation to ensure resourceType exists."""
        if not resource:
            return False
        if "resourceType" not in resource:
            return False
        if resource["resourceType"] == "Bundle":
            if "entry" not in resource or not isinstance(resource["entry"], list):
                return False
        return True
