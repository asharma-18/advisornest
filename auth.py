import os
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


def register_advisor(email, password, full_name, firm_name, license_number=""):
    try:
        auth_response = get_supabase().auth.sign_up({
            "email": email,
            "password": password
        })

        if not auth_response.user:
            return {
                "success": False,
                "message": "Could not create account. Please try again."
            }

        user_id = auth_response.user.id

        from datetime import datetime, timezone
        get_supabase().table("advisors").insert({
            "id":                user_id,
            "full_name":         full_name,
            "firm_name":         firm_name,
            "license_number":    license_number,
            "terms_accepted_at": datetime.now(timezone.utc).isoformat(),
        }).execute()

        return {
            "success": True,
            "message": "Account created successfully!"
        }

    except Exception as e:
        error_msg = str(e)
        print(f"Register error: {error_msg}")
        if "already registered" in error_msg.lower():
            return {
                "success": False,
                "message": "An account with this email already exists."
            }
        return {
            "success": False,
            "message": f"Registration failed: {error_msg}"
        }


def login_advisor(email, password):
    try:
        auth_response = get_supabase().auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        if not auth_response.user:
            return {
                "success": False,
                "message": "Invalid email or password."
            }

        user_id = auth_response.user.id

        profile = get_supabase().table("advisors")\
            .select("*")\
            .eq("id", user_id)\
            .execute()

        full_name      = ""
        firm_name      = ""
        license_number = ""

        if profile.data and len(profile.data) > 0:
            full_name      = profile.data[0].get("full_name", "")
            firm_name      = profile.data[0].get("firm_name", "")
            license_number = profile.data[0].get("license_number", "")

        return {
            "success":        True,
            "user_id":        user_id,
            "email":          email,
            "full_name":      full_name,
            "firm_name":      firm_name,
            "license_number": license_number
        }

    except Exception as e:
        error_msg = str(e)
        print(f"Login error: {error_msg}")
        if "invalid" in error_msg.lower() or "credentials" in error_msg.lower():
            return {
                "success": False,
                "message": "Invalid email or password. Please try again."
            }
        return {
            "success": False,
            "message": f"Login failed: {error_msg}"
        }


def get_google_auth_url():
    try:
        response = get_supabase().auth.sign_in_with_oauth({
            "provider": "google",
            "options": {
                "redirect_to": os.environ.get("GOOGLE_REDIRECT_URI",
                    "http://127.0.0.1:5000/auth/google/callback")
            }
        })
        return response.url
    except Exception as e:
        print(f"Google auth error: {str(e)}")
        return None