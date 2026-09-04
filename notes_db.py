# notes_db.py
# All database operations for client meeting notes

import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

_supabase = None

def get_supabase():
    global _supabase
    if _supabase is None:
        _supabase = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_KEY")
        )
    return _supabase


def get_all_notes(advisor_id):
    """
    Gets all notes for this advisor across all clients.
    Ordered by most recent first.
    """
    try:
        result = get_supabase().table("notes")\
            .select("*, clients(client_name)")\
            .eq("advisor_id", advisor_id)\
            .order("created_at", desc=True)\
            .execute()
        return result.data if result.data else []
    except Exception as e:
        print(f"Get notes error: {str(e)}")
        return []


def get_client_notes(advisor_id, client_id):
    try:
        result = get_supabase().table("notes")\
            .select("*, clients(client_name)")\
            .eq("advisor_id", advisor_id)\
            .eq("client_id", client_id)\
            .order("created_at", desc=True)\
            .execute()
        return result.data if result.data else []
    except Exception as e:
        print(f"Get client notes error: {str(e)}")
        return []


def add_note(advisor_id, client_id, subject, body, meeting_date):
    """
    Adds a new note for a client.
    """
    try:
        data = {
            "advisor_id":   advisor_id,
            "client_id":    client_id,
            "subject":      subject,
            "body":         body,
        }
        if meeting_date:
            data["meeting_date"] = meeting_date

        result = get_supabase().table("notes")\
            .insert(data)\
            .execute()

        if result.data:
            return {"success": True, "note": result.data[0]}
        return {"success": False, "message": "Could not save note."}
    except Exception as e:
        print(f"Add note error: {str(e)}")
        return {"success": False, "message": str(e)}


def delete_note(note_id, advisor_id):
    """
    Deletes a note. Checks advisor_id for security.
    """
    try:
        get_supabase().table("notes")\
            .delete()\
            .eq("id", note_id)\
            .eq("advisor_id", advisor_id)\
            .execute()
        return {"success": True}
    except Exception as e:
        print(f"Delete note error: {str(e)}")
        return {"success": False, "message": str(e)}


def get_note_count(advisor_id):
    """
    Returns total note count for this advisor.
    Used on the dashboard.
    """
    try:
        result = get_supabase().table("notes")\
            .select("id", count="exact")\
            .eq("advisor_id", advisor_id)\
            .execute()
        return result.count if result.count else 0
    except Exception:
        return 0


def update_note(note_id, advisor_id, subject, body, meeting_date):
    """
    Updates an existing note.
    Checks advisor_id for security.
    """
    try:
        data = {
            "subject": subject,
            "body":    body,
        }
        if meeting_date:
            data["meeting_date"] = meeting_date

        result = get_supabase().table("notes")\
            .update(data)\
            .eq("id", note_id)\
            .eq("advisor_id", advisor_id)\
            .execute()

        if result.data:
            return {"success": True}
        return {"success": False, "message": "Could not update note."}
    except Exception as e:
        print(f"Update note error: {str(e)}")
        return {"success": False, "message": str(e)}