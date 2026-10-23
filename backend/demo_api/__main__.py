import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("demo_api.app:app", host=os.environ.get("DEMO_HOST", "127.0.0.1"),
                port=int(os.environ.get("DEMO_PORT", "8000")), log_level="warning")
