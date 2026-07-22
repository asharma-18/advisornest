import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

# Create Supabase client
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)


def register_advisor(email, password, full_name, firm_name):
    try:
        auth_response = supabase.auth.sign_up({
            "email": email,
            "password": password
        })

        if not auth_response.user:
            return {
                "success": False,
                "message": "Could not create account. Please try again."
            }

        user_id = auth_response.user.id

        supabase.table("advisors").insert({
            "id": user_id,
            "full_name": full_name,
            "firm_name": firm_name
        }).execute()

        return {
            "success": True,
            "message": "Account created successfully!"
        }

    except Exception as e:
        error = str(e)
        if "already registered" in error.lower():
            return {
                "success": False,
                "message": "An account with this email already exists."
            }
        return {
            "success": False,
            "message": "Registration failed. Please try again."
        }


def login_advisor(email, password):
    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        if not auth_response.user:
            return {
                "success": False,
                "message": "Invalid email or password."
            }

        user_id = auth_response.user.id

        profile = supabase.table("advisors")\
            .select("*")\
            .eq("id", user_id)\
            .execute()

        full_name = ""
        firm_name = ""
        if profile.data and len(profile.data) > 0:
            full_name = profile.data[0].get("full_name", "")
            firm_name = profile.data[0].get("firm_name", "")

        return {
            "success": True,
            "user_id": user_id,
            "email": email,
            "full_name": full_name,
            "firm_name": firm_name
        }

    except Exception as e:
        error = str(e)
        if "invalid" in error.lower() or "credentials" in error.lower():
            return {
                "success": False,
                "message": "Invalid email or password."
            }
        return {
            "success": False,
            "message": "Login failed. Please try again."
        }