import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run("ledger_api.app:app", host=os.environ.get("LEDGER_HOST", "127.0.0.1"),
                port=int(os.environ.get("LEDGER_PORT", "8100")), log_level="warning")
