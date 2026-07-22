from app import create_app

# Build the Flask application
app = create_app()

if __name__ == "__main__":
    # Start the web server
    # debug=True means:
    # 1. Flask restarts automatically when you save a file
    # 2. Shows detailed error messages in the browser
    # 3. NEVER use debug=True in production
    app.run(debug=True, port=5000)
