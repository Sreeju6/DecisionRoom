MINIMAL DECISIONROOM FRONTEND — REPLACE ONLY TWO FILES

This ZIP intentionally stores main.jsx and styles.css at the ZIP ROOT (no nested frontend/src folders).

Copy these files directly into:
C:\Users\varan\Desktop\DecisionRoom\frontend\src\

Choose Replace/Overwrite for both files. Confirm the folder path in File Explorer ends exactly:
DecisionRoom > frontend > src
NOT DecisionRoom > frontend > src > frontend > src.

This layout shows only:
- Decision question and target state
- Final recommendation and confidence
- Expandable Research, Risks, Critic Findings and Alternative Plans
It does not display an Official Source Verification panel.
The existing API call remains POST /api/analyze.
After replacing, Vite usually auto-refreshes. If not, reload the page. Do not replace your backend, .env, or agents.
