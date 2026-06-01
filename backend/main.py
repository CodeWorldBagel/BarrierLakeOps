"""Zeabur 原生 Python 建置的進入點(預設執行 `python main.py`)。

本機開發仍可用:uvicorn barrier_lake_ops.app:app --reload --port 8000
"""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "barrier_lake_ops.app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
    )
