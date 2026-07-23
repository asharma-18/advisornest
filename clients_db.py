# clients_db.py
# All database operations for client profiles
# Imported by routes.py

import os
import json
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

# Use service role key for database operations
# This bypasses RLS — keep this key secret
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")
)

def save_client(advisor_id, client_data):
    try:
        result = supabase.table("clients").insert({
            "advisor_id":       advisor_id,
            "client_name":      client_data["client_name"],
            "age":              client_data["age"],
            "life_stage":       client_data["life_stage"],
            "amount":           client_data["amount"],
            "risk":             client_data["risk"],
            "horizon":          client_data["horizon"],
            "allocation":       client_data["allocation"],
            "score":            client_data["score"],
            "flags":            client_data["flags"],
            "suitability_note": client_data["suitability_note"],
        }).execute()

        print(f"Save result: {result}")

        if result.data:
            return {
                "success": True,
                "message": f"{client_data['client_name']} saved successfully.",
                "client_id": result.data[0]["id"]
            }
        else:
            return {
                "success": False,
                "message": "Could not save client. Please try again."
            }

    except Exception as e:
        print(f"FULL ERROR: {repr(e)}")
        return {
            "success": False,
            "message": f"Failed: {repr(e)}"
        }

def get_all_clients(advisor_id):
    """
    Gets all clients saved by this advisor.
    Returns a list of client records ordered by most recent first.
    """
    try:
        result = supabase.table("clients")\
            .select("*")\
            .eq("advisor_id", advisor_id)\
            .order("created_at", desc=True)\
            .execute()

        return result.data if result.data else []

    except Exception:
        return []


def get_client(client_id, advisor_id):
    """
    Gets a single client by ID.
    advisor_id is checked to make sure the advisor
    owns this client — security check.
    """
    try:
        result = supabase.table("clients")\
            .select("*")\
            .eq("id", client_id)\
            .eq("advisor_id", advisor_id)\
            .execute()

        if result.data and len(result.data) > 0:
            return result.data[0]
        return None

    except Exception:
        return None


def delete_client(client_id, advisor_id):
    """
    Deletes a client profile.
    advisor_id is checked so advisors can only
    delete their own clients.
    """
    try:
        supabase.table("clients")\
            .delete()\
            .eq("id", client_id)\
            .eq("advisor_id", advisor_id)\
            .execute()

        return {
            "success": True,
            "message": "Client deleted successfully."
        }

    except Exception:
        return {
            "success": False,
            "message": "Could not delete client. Please try again."
        }


def get_client_count(advisor_id):
    """
    Returns the total number of clients saved
    by this advisor. Used on the dashboard.
    """
    try:
        result = supabase.table("clients")\
            .select("id", count="exact")\
            .eq("advisor_id", advisor_id)\
            .execute()

        return result.count if result.count else 0

    except Exception:
        return 0