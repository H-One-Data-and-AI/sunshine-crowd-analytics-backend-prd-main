Local (recommended)
1. Create & activate venv:
   python3 -m venv myenv
   source myenv/bin/activate
2. Install deps:
   pip install -r requirements.txt
3. Ensure .env exists (SECRET_KEY, JWT_SECRET_KEY). Example:
   export SECRET_KEY="..." && export JWT_SECRET_KEY="..."
   or use --env-file when running Docker.
4. Initialize DB:
   python app/db_init.py
5. Run server:
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   uvicorn main:app --app-dir app --reload --env-file .env
   uvicorn main:app --app-dir app --reload --env-file .env --port 8000

Docker
1. Build:
   docker build -t crowd-backend:latest .
2. Run:
   docker run -d -p 8000:8000 --env-file .env --name crowd-backend crowd-backend:latest

Useful endpoints
- POST /token (login) — see app/main.py
- POST /main_adjust/recalculate — recalculates scores (services/scoring_service.py)

Notes
- DB path and settings: app/settings.py
- CSV helpers and streaming: app/utils/db_utils.py