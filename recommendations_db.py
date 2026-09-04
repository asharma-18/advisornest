# recommendations_db.py
# Database operations for AI recommendations

import os
import json
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

_supabase = None

def get_supabase():
    global _supabase
    if _supabase is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        print(f"Supabase URL present: {bool(url)}")
        print(f"Supabase KEY present: {bool(key)}")
        if not url or not key:
            raise Exception(f"Missing Supabase credentials. URL: {bool(url)}, KEY: {bool(key)}")
        _supabase = create_client(url, key)
    return _supabase

def save_recommendation(advisor_id, client_id, rec_data):
    """
    Saves the full AI recommendation to Supabase.
    Called when advisor saves a client profile.
    """
    try:
        result = get_supabase().table("recommendations").insert({
            "advisor_id":      advisor_id,
            "client_id":       client_id,
            "client_name":     rec_data.get("client_name", ""),
            "age":             rec_data.get("age", 0),
            "life_stage":      rec_data.get("life_stage", ""),
            "amount":          rec_data.get("amount", 0),
            "risk":            rec_data.get("risk", ""),
            "horizon":         rec_data.get("horizon", 0),
            "selected_option": rec_data.get("selected_option", ""),
            "ai_data":         rec_data.get("ai_data", {}),
            "allocation":      rec_data.get("allocation", {}),
            "suitability_note": rec_data.get("suitability_note", ""),
            "score":           rec_data.get("score", 0),
        }).execute()

        if result.data:
            return {"success": True, "id": result.data[0]["id"]}
        return {"success": False, "message": "Could not save recommendation"}

    except Exception as e:
        print(f"Save recommendation error: {str(e)}")
        return {"success": False, "message": str(e)}


def get_all_recommendations(advisor_id):
    """
    Gets all recommendations for this advisor.
    Ordered by most recent first.
    """
    try:
        result = get_supabase().table("recommendations")\
            .select("*")\
            .eq("advisor_id", advisor_id)\
            .order("created_at", desc=True)\
            .execute()
        return result.data if result.data else []
    except Exception as e:
        print(f"Get recommendations error: {str(e)}")
        return []


def get_client_recommendations(advisor_id, client_id):
    """
    Gets all recommendations for a specific client.
    """
    try:
        result = get_supabase().table("recommendations")\
            .select("*")\
            .eq("advisor_id", advisor_id)\
            .eq("client_id", client_id)\
            .order("created_at", desc=True)\
            .execute()
        return result.data if result.data else []
    except Exception as e:
        print(f"Get client recommendations error: {str(e)}")
        return []


def get_recommendation(advisor_id, rec_id):
    """
    Gets a single recommendation by ID.
    """
    try:
        result = get_supabase().table("recommendations")\
            .select("*")\
            .eq("advisor_id", advisor_id)\
            .eq("id", rec_id)\
            .execute()
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        print(f"Get recommendation error: {str(e)}")
        return None


def delete_recommendation(advisor_id, rec_id):
    """
    Deletes a recommendation.
    """
    try:
        get_supabase().table("recommendations")\
            .delete()\
            .eq("advisor_id", advisor_id)\
            .eq("id", rec_id)\
            .execute()
        return {"success": True}
    except Exception as e:
        print(f"Delete recommendation error: {str(e)}")
        return {"success": False, "message": str(e)}


def get_recommendation_count(advisor_id):
    """
    Returns total recommendation count for this advisor.
    """
    try:
        result = get_supabase().table("recommendations")\
            .select("id", count="exact")\
            .eq("advisor_id", advisor_id)\
            .execute()
        return result.count if result.count else 0
    except Exception:
        return 0