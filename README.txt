DECISIONROOM API FIX

1. Copy api.py into C:\Users\varan\Desktop\DecisionRoom (same folder as main.py).
2. Copy requirements-api.txt into that project root too.
3. In the existing activated venv, run:
   pip install -r requirements-api.txt
   python -m uvicorn api:app --host 127.0.0.1 --port 8000 --reload
4. Visit http://127.0.0.1:8000/health — expected {"status":"ok","service":"DecisionRoom API"}
5. Leave that terminal running. Refresh the frontend and run analysis.

The adapter imports and calls your existing agents. It does not replace main.py,
agents, .env, data, documents, or vector_db. It saves web reports under reports/.

For Netlify later, set VITE_API_URL to the deployed API base URL and set
DECISIONROOM_CORS_ORIGINS on the API host to include your exact Netlify domain.
