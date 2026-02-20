# main.py
import gui
import sys
import os

# Import the FastAPI app from server.py to ensure unified routes
try:
    from server import app
except ImportError:
    # Fallback if server.py is not in the same directory (though it should be)
    app = None

if __name__ == "__main__":
    # Check if we should run as a server or GUI
    # On headless environments like AWS, users typically run uvicorn main:app
    # But if run as 'python main.py server', we can also start it directly.
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        import uvicorn
        print("🚀 Starting Anti-Gravity Server...")
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
    else:
        print("🖥️ Starting Anti-Gravity GUI...")
        gui.main()
