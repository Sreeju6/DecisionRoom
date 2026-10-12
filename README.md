# DecisionRoom Cool Frontend

This is a real React/Vite frontend based on your reference: dark cosmic background, neon purple/blue glow, glass panels, hero section, decision form, seven-agent workflow, metric cards, comparison bars, India context, and result panels.

## Install
1. Copy `frontend/` into your existing DecisionRoom project.
2. In the frontend folder run:
   `npm install`
   `Copy-Item .env.example .env`
   `npm run dev`
3. The page expects the API at `http://127.0.0.1:8000` by default.

## API contract
The frontend sends:
`POST /api/analyze`
JSON: `{"target_state":"Tamil Nadu","decision_question":"..."}`

It expects the API to return the full structured report as JSON, ideally with keys:
`data_agent`, `research_agent`, `official_verification`, `risk_agent`, `critic_agent`, `planner_agent`, `final_decision_agent`.

Set `VITE_API_URL` to your deployed API URL before building for Netlify.

## Deploy to Netlify
- Base directory: `frontend`
- Build command: `npm run build`
- Publish directory: `dist`
- Environment variable: `VITE_API_URL=https://YOUR-API-SERVICE-DOMAIN`
- `netlify.toml` is included.

Note: this package focuses on the actual frontend. It does not replace your existing multi-agent backend. Ensure your FastAPI adapter exposes `/api/analyze` and returns the structured JSON report from your existing workflow.
