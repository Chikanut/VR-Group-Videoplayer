#!/usr/bin/env python3
"""Entry point for VR Classroom Control Server."""
import uvicorn
from server.config import load_config

if __name__ == "__main__":
    config = load_config()
    port = config.get("serverPort", 8000)
    print(f"Starting VR Classroom Control Server on port {port}...")
    uvicorn.run("server.main:app", host="0.0.0.0", port=port, reload=False)
