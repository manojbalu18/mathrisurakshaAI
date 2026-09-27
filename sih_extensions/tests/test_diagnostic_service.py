import unittest
import os
import tempfile
from sih_extensions.sih_database import init_sih_db
from sih_extensions.facility_directory import FacilityDirectory
from sih_extensions.diagnostic_service import DiagnosticService

class TestDiagnosticService(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        init_sih_db(db_path=self.db_path)
        FacilityDirectory.seed_demo_data(db_path=self.db_path)
        DiagnosticService.seed_demo_data(db_path=self.db_path)

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_diagnostic_creation_and_retrieval(self):
        res = DiagnosticService.create_or_update_diagnostic(
            "FAC-DEMO-001", "DIAG-100", "CT Scan", "Radiology", "Advanced Imaging", "AVAILABLE", db_path=self.db_path
        )
        self.assertTrue(res["success"])
        
        d = DiagnosticService.get_diagnostic("DIAG-100", "FAC-DEMO-001", db_path=self.db_path)
        self.assertEqual(d["category"], "Radiology")
        self.assertEqual(d["status"], "AVAILABLE")
        
    def test_invalid_facility(self):
        res = DiagnosticService.create_or_update_diagnostic(
            "INVALID", "DIAG-100", "Test", "Test", "Test", db_path=self.db_path
        )
        self.assertFalse(res["success"])

    def test_availability_update(self):
        DiagnosticService.create_or_update_diagnostic("FAC-DEMO-001", "DIAG-200", "Test", "Cat", "Dept", db_path=self.db_path)
        
        DiagnosticService.update_availability("DIAG-200", "FAC-DEMO-001", "UNAVAILABLE", db_path=self.db_path)
        d = DiagnosticService.get_diagnostic("DIAG-200", "FAC-DEMO-001", db_path=self.db_path)
        self.assertEqual(d["status"], "UNAVAILABLE")

    def test_search_and_list(self):
        # Demo data is seeded
        inv = DiagnosticService.get_facility_diagnostics("FAC-DEMO-001", db_path=self.db_path)
        self.assertGreaterEqual(len(inv), 2)
        
        search = DiagnosticService.search_diagnostic("Blood", db_path=self.db_path)
        self.assertTrue(any("Blood" in s["item_name"] for s in search))

    def test_deactivate(self):
        DiagnosticService.deactivate_diagnostic("DIAG-001", "FAC-DEMO-001", db_path=self.db_path)
        inv = DiagnosticService.get_facility_diagnostics("FAC-DEMO-001", db_path=self.db_path)
        # Should not include deactivated item
        self.assertFalse(any(i["item_id"] == "DIAG-001" for i in inv))
