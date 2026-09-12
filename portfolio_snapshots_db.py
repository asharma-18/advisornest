# portfolio_snapshots_db.py
# Stores daily portfolio value snapshots per client, used to
# build a performance-over-time chart once enough history exists.

import os
from datetime import date
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

_supabase = None

def get_supabase():
    global _supabase
    if _supabase is None:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_KEY")
        _supabase = create_client(url, key)
    return _supabase


def save_snapshot(advisor_id, client_id, total_value):
    """
    Records today's portfolio value for a client.
    Upserts on (client_id, snapshot_date) so recalculating
    drift multiple times in one day doesn't create duplicate rows.
    """
    try:
        today = date.today().isoformat()
        get_supabase().table("portfolio_snapshots").upsert({
            "advisor_id":    advisor_id,
            "client_id":     client_id,
            "snapshot_date": today,
            "total_value":   total_value,
        }, on_conflict="client_id,snapshot_date").execute()
        return {"success": True}
    except Exception as e:
        print(f"Save snapshot error: {str(e)}")
        return {"success": False, "message": str(e)}


def get_client_snapshots(advisor_id, client_id):
    """
    Gets all recorded snapshots for a client, oldest first —
    ready to feed straight into a line chart.
    """
    try:
        result = get_supabase().table("portfolio_snapshots")\
            .select("*")\
            .eq("advisor_id", advisor_id)\
            .eq("client_id", client_id)\
            .order("snapshot_date", desc=False)\
            .execute()
        return result.data if result.data else []
    except Exception as e:
        print(f"Get snapshots error: {str(e)}")
        return []