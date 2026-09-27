"""
SIH Dedicated Offline Queue Manager.
Operates completely independently of the legacy offline_sync table.
Supports robust queuing, retries, and status tracking for complex operations.
"""

import json
import uuid
from typing import List, Dict, Any

from .sih_database import get_sih_connection, DB_PATH

class SIHOfflineQueue:
    
    @staticmethod
    def enqueue(operation_type: str, payload: Dict[str, Any], db_path: str = DB_PATH) -> str:
        """Add a new operation to the queue and return its unique ID."""
        operation_id = str(uuid.uuid4())
        payload_str = json.dumps(payload)
        
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
            INSERT INTO sih_offline_sync 
            (operation_id, operation_type, payload, status)
            VALUES (?, ?, ?, 'PENDING')
            """, (operation_id, operation_type, payload_str))
            conn.commit()
            
        return operation_id
        
    @staticmethod
    def get_pending(limit: int = 50, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
        """Retrieve operations that are PENDING or eligible for retry."""
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
            SELECT id, operation_id, operation_type, payload, status, retry_count, error_msg, last_attempt, created_at
            FROM sih_offline_sync
            WHERE status IN ('PENDING', 'FAILED') AND retry_count < 3
            ORDER BY created_at ASC LIMIT ?
            """, (limit,))
            rows = c.fetchall()
            
        results = []
        for r in rows:
            try:
                payload = json.loads(r[3])
            except json.JSONDecodeError:
                payload = {"_raw": r[3], "_error": "invalid json"}
                
            results.append({
                'id': r[0],
                'operation_id': r[1],
                'operation_type': r[2],
                'payload': payload,
                'status': r[4],
                'retry_count': r[5],
                'error_msg': r[6],
                'last_attempt': r[7],
                'created_at': r[8]
            })
        return results
        
    @staticmethod
    def mark_processing(operation_id: str, db_path: str = DB_PATH):
        """Mark an operation as actively being processed."""
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
            UPDATE sih_offline_sync 
            SET status = 'PROCESSING', last_attempt = CURRENT_TIMESTAMP
            WHERE operation_id = ?
            """, (operation_id,))
            conn.commit()

    @staticmethod
    def mark_synced(operation_id: str, db_path: str = DB_PATH):
        """Mark an operation as successfully completed."""
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
            UPDATE sih_offline_sync 
            SET status = 'SYNCED', synced_at = CURRENT_TIMESTAMP
            WHERE operation_id = ?
            """, (operation_id,))
            conn.commit()

    @staticmethod
    def mark_failed(operation_id: str, error_msg: str, db_path: str = DB_PATH):
        """Mark an operation as failed, incrementing the retry count."""
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
            UPDATE sih_offline_sync 
            SET status = 'FAILED', 
                retry_count = retry_count + 1,
                error_msg = ?
            WHERE operation_id = ?
            """, (error_msg, operation_id))
            conn.commit()

    @staticmethod
    def retry_failed(db_path: str = DB_PATH):
        """Reset failed but retriable operations back to PENDING."""
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
            UPDATE sih_offline_sync 
            SET status = 'PENDING'
            WHERE status = 'FAILED' AND retry_count < 3
            """)
            conn.commit()

    @staticmethod
    def get_queue_status(db_path: str = DB_PATH) -> Dict[str, int]:
        """Return the count of operations by status."""
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT status, COUNT(*) FROM sih_offline_sync GROUP BY status")
            rows = c.fetchall()
            
        return {r[0]: r[1] for r in rows}
