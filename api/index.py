import os
import sys

# Add the Backend folder to sys.path so that FastAPI and its internal imports work correctly
backend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Backend")
sys.path.append(os.path.abspath(backend_path))

# Import the FastAPI application instance from Backend/main.py
from main import app
