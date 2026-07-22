import os
from dotenv import load_dotenv

# This reads your .env file and loads all 
# the keys into Python's memory
load_dotenv()

class Config:
    # Flask needs a secret key to encrypt 
    # user sessions — like a password for sessions
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-key-change-in-production")
    
    # Supabase database connection
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    
    # OpenAI for AI reasoning
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    
    # FRED for Treasury and CD rates
    FRED_API_KEY = os.getenv("FRED_API_KEY")
    
    # Flask debug mode — True during development
    # NEVER True in production
    DEBUG = True