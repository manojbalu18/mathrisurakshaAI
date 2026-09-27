import unittest
import os
import tempfile
import sqlite3
from sih_extensions.sih_database import init_sih_db
from sih_extensions.patient_timeline_service import PatientTimelineService

class TestPatientTimelineService(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        
        # Initialize legacy tables needed for tests
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, unique_id TEXT, name TEXT, role TEXT)")
            c.execute("CREATE TABLE daily_logs (id INTEGER PRIMARY KEY, user_id TEXT, date TEXT, risk_level TEXT, risk_score INTEGER, symptoms TEXT, mood TEXT, nutrition TEXT)")
            c.execute("CREATE TABLE alerts (id INTEGER PRIMARY KEY, user_id TEXT, timestamp TEXT, risk_level TEXT, status TEXT)")
            
            c.execute("INSERT INTO users (unique_id, name, role) VALUES ('PAT-1', 'Test Mother', 'Mother')")
            c.execute("INSERT INTO daily_logs (user_id, date, risk_level, risk_score, symptoms, mood, nutrition) VALUES ('PAT-1', '2023-10-01T10:00:00', 'Low', 10, 'None', 'Good', 'Good')")
            c.execute("INSERT INTO alerts (user_id, timestamp, risk_level, status) VALUES ('PAT-1', '2023-10-02T10:00:00', 'High', 'Active')")
            conn.commit()

        # Initialize SIH tables
        init_sih_db(db_path=self.db_path)
        
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO sih_appointments (patient_id, facility_id, appointment_time, status) VALUES ('PAT-1', 'FAC-1', '2023-10-03T10:00:00', 'Scheduled')")
            c.execute("INSERT INTO sih_referrals (patient_id, source_facility, referred_to_facility, reason, status, created_at) VALUES ('PAT-1', 'FAC-1', 'FAC-2', 'Specialist', 'OPEN', '2023-10-04T10:00:00')")
            conn.commit()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_timeline_aggregation_and_ordering(self):
        timeline = PatientTimelineService.get_patient_timeline("PAT-1", db_path=self.db_path)
        
        self.assertEqual(len(timeline), 4)
        
        # Should be descending order by date
        self.assertEqual(timeline[0]["event_type"], "REFERRAL") # 10-04
        self.assertEqual(timeline[1]["event_type"], "APPOINTMENT") # 10-03
        self.assertEqual(timeline[2]["event_type"], "ALERT") # 10-02
        self.assertEqual(timeline[3]["event_type"], "DAILY_LOG") # 10-01

    def test_timeline_filtering(self):
        # Filter by type
        alerts = PatientTimelineService.get_patient_timeline("PAT-1", event_type="ALERT", db_path=self.db_path)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["status"], "Active")
        
        # Filter by date
        filtered = PatientTimelineService.get_patient_timeline("PAT-1", start_date="2023-10-02T00:00:00", end_date="2023-10-03T23:59:59", db_path=self.db_path)
        self.assertEqual(len(filtered), 2)
        types = [e["event_type"] for e in filtered]
        self.assertIn("ALERT", types)
        self.assertIn("APPOINTMENT", types)

    def test_missing_patient(self):
        timeline = PatientTimelineService.get_patient_timeline("INVALID-PATIENT", db_path=self.db_path)
        self.assertEqual(len(timeline), 0)

    def test_pagination(self):
        timeline = PatientTimelineService.get_patient_timeline("PAT-1", limit=2, offset=1, db_path=self.db_path)
        self.assertEqual(len(timeline), 2)
        # Offset 1 means we skip REFERRAL (index 0) and get APPOINTMENT and ALERT
        self.assertEqual(timeline[0]["event_type"], "APPOINTMENT")
        self.assertEqual(timeline[1]["event_type"], "ALERT")
