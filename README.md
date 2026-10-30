# FinSight — Personal Finance & Expense Intelligence

A full-stack, responsive personal-finance project based on the FinSight Software Engineering Lab SRS. The UI uses a clean white and forest-green palette, with responsive desktop/mobile layouts.

## Features

- Email/password registration and login; Argon2 password hashing and signed access tokens.
- Income and expense records, editing, deletion, category suggestions, and CSV import/export.
- Weekly/monthly category budgets, calculated spend, and 90% budget reminders.
- Analytics dashboard with cash flow, category breakdown, recorded totals, and previous-month comparison.
- Explainable unusual-transaction flags based on prior transactions in the same category.
- Expense forecast using recent months with recorded expense activity; the UI labels it a historical estimate, not an AI guarantee.
- Target-based savings goals with dates and progress updates.
- Explicitly linked financial advisors can sign in using their linked email to retrieve a read-only client summary in the Advisor Access page.
- Mobile-responsive UI, alerts, account settings, theme toggle, API docs and CSV download.

## Stack

- Frontend: React, Vite, Recharts, Lucide icons.
- Backend: FastAPI, SQLAlchemy, Pydantic, Argon2, PyJWT.
- Database: SQLite by default (stored at `backend/finsight.db` when the API runs from the `backend/` directory). `DATABASE_URL` can be changed to a compatible SQLAlchemy connection string for a managed relational database.

## Run locally (Windows PowerShell)

Extract the zip, then open **two terminals** in the extracted `finsight` directory.

### 1. Start the backend

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:SECRET_KEY = "replace-with-your-own-long-random-secret"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API health: <http://127.0.0.1:8000/api/health>  
Interactive API documentation: <http://127.0.0.1:8000/docs>

### 2. Start the frontend

```powershell
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (typically <http://localhost:5173>).

The frontend connects to `http://127.0.0.1:8000` by default. To use another API host, create `frontend/.env.local`:

```env
VITE_API_URL=http://127.0.0.1:8000
```

Restart Vite after changing environment variables. The included `run_backend_windows.bat` and `run_frontend_windows.bat` are optional shortcuts; the PowerShell commands above provide more control over the development environment.

## Presentation/demo data (optional)

For a fresh demo account, the seed script is available after running the backend dependencies:

```powershell
cd backend
python seed_demo.py
```

Demo sign-in: `demo@finsight.app` / `DemoPass123!`

This account is for local demonstrations only. The seed script does not overwrite an existing account with that email.

Alternatively, register a new account, then use the API demo seed route only after setting `$env:ENABLE_DEMO_SEED = "true"` and restarting the backend. The route seeds sample transactions only into an account with no transactions.

## CSV format

Required columns: `date`, `amount`. Optional: `type`, `category`, `note` (or `description`). Example:

```csv
date,amount,type,category,note
2026-10-01,1200,expense,Food,Lunch and groceries
2026-10-02,45000,income,Salary,Monthly salary
```

Dates use ISO `YYYY-MM-DD`. Income rows should use `income` or `credit` in the type column; negative amounts are also interpreted as income. A sample CSV can be downloaded from the Transactions page.

## Tests and frontend build

Backend (from `backend/`, after installing the requirements):

```powershell
python -m pytest -q tests_test_api.py
```

Frontend (from `frontend/`):

```powershell
npm run build
```

The backend smoke tests cover health, authentication and transaction flow, and explicit advisor-access checks. Frontend JSX syntax was checked, but the Vite production build could not be run in the generation environment because it could not reach the npm package registry; install dependencies locally and run the build command above.

## Deployment / security notes

- Set a strong, random `SECRET_KEY` and a production database URL before exposing the API.
- Configure `CORS_ORIGINS` with the exact frontend origin(s), and serve the frontend/backend over HTTPS.
- `render.yaml` is only a starter configuration. Update its frontend origin placeholder. Use a persistent disk or, preferably, a managed relational database for hosted deployments; SQLite on ephemeral hosts may lose data after redeploys.
- The frontend can be deployed separately to a static host that supports Vite. Set `VITE_API_URL` to the deployed API URL before building; visitors cannot reach a developer's localhost API.
- Advisor summary access is checked against the advisor's authenticated email and the owner's explicit link. The advisor interface is read-only.
- The forecast is a simple average of recent months with recorded expenses. Anomaly checks are transparent baseline heuristics; neither should be represented as certified fraud detection or a trained ML system.
- Set up backups and rate limiting before public production use.

## SRS feature mapping

| SRS capability | Implementation |
| --- | --- |
| FR-1 to FR-3 authentication | `/api/auth/register`, `/api/auth/login`, frontend auth screen |
| FR-4 to FR-6 transactions/category | transaction CRUD endpoints and note-driven category suggestion |
| FR-7 to FR-9 budgets | budget endpoints, spend calculation, 90% alerts |
| FR-10 to FR-11 analytics/comparison | `/api/dashboard`, `/api/analytics`, charts |
| FR-12 to FR-13 anomaly notices | baseline transaction flag and `/api/alerts` |
| FR-14 forecast | `/api/dashboard` historical-average estimate and Forecasts page |
| FR-15 to FR-16 goal tracking | goal endpoints and Goals page |
| FR-17 advisor access | explicit advisor links and read-only `/api/advisor` endpoint |
