import unittest
import os
import tempfile
import sqlite3
import json
from sih_extensions.sih_database import init_sih_db
from sih_extensions.fhir_mapper import FHIRMapper

class TestFHIRMapper(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, unique_id TEXT, name TEXT, phone TEXT, village TEXT, role TEXT)")
            c.execute("CREATE TABLE daily_logs (id INTEGER PRIMARY KEY, user_id TEXT, date TEXT, risk_level TEXT, risk_score INTEGER, symptoms TEXT, mood TEXT, nutrition TEXT)")
            c.execute("CREATE TABLE alerts (id INTEGER PRIMARY KEY, user_id TEXT, timestamp TEXT, risk_level TEXT, status TEXT)")
            
            c.execute("INSERT INTO users (unique_id, name, phone, village, role) VALUES ('PAT-2', 'Jane Doe', '1234567890', 'Test Village', 'Mother')")
            c.execute("INSERT INTO daily_logs (user_id, date, risk_level, risk_score, symptoms, mood, nutrition) VALUES ('PAT-2', '2023-10-01T10:00:00', 'Low', 10, 'None', 'Good', 'Good')")
            conn.commit()

        init_sih_db(db_path=self.db_path)
        
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO sih_appointments (patient_id, facility_id, appointment_time, status) VALUES ('PAT-2', 'FAC-1', '2023-10-03T10:00:00', 'Scheduled')")
            conn.commit()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_build_patient_resource(self):
        pat = FHIRMapper.build_patient_resource("PAT-2", db_path=self.db_path)
        self.assertEqual(pat["resourceType"], "Patient")
        self.assertEqual(pat["name"][0]["text"], "Jane Doe")
        self.assertEqual(pat["telecom"][0]["value"], "1234567890")

    def test_map_event_to_resource(self):
        event_appt = {
            "event_id": "app-1",
            "patient_id": "PAT-2",
            "event_type": "APPOINTMENT",
            "event_date": "2023-10-03T10:00:00",
            "title": "Appt",
            "description": "Test Appt",
            "status": "Scheduled",
            "reference_id": 1
        }
        res = FHIRMapper.map_event_to_resource(event_appt)
        self.assertEqual(res["resourceType"], "Appointment")
        self.assertEqual(res["status"], "booked")
        
        event_log = {
            "event_id": "log-1",
            "patient_id": "PAT-2",
            "event_type": "DAILY_LOG",
            "event_date": "2023-10-01T10:00:00",
            "title": "Log",
            "description": "Test Log",
            "status": "Low"
        }
        res2 = FHIRMapper.map_event_to_resource(event_log)
        self.assertEqual(res2["resourceType"], "Observation")
        self.assertEqual(res2["valueString"], "Test Log")

    def test_build_patient_bundle(self):
        bundle = FHIRMapper.build_patient_bundle("PAT-2", db_path=self.db_path)
        
        self.assertEqual(bundle["resourceType"], "Bundle")
        self.assertEqual(bundle["type"], "collection")
        
        # 1 Patient resource + 1 Observation (Log) + 1 Appointment
        self.assertEqual(len(bundle["entry"]), 3)
        
        resource_types = [e["resource"]["resourceType"] for e in bundle["entry"]]
        self.assertIn("Patient", resource_types)
        self.assertIn("Observation", resource_types)
        self.assertIn("Appointment", resource_types)
        
        # Test serialization
        json_str = json.dumps(bundle)
        self.assertIn("Jane Doe", json_str)
        
    def test_validation(self):
        bundle = FHIRMapper.build_patient_bundle("PAT-2", db_path=self.db_path)
        self.assertTrue(FHIRMapper.validate_basic_structure(bundle))
        
        self.assertFalse(FHIRMapper.validate_basic_structure({"wrong": "data"}))
        self.assertFalse(FHIRMapper.validate_basic_structure(None))
