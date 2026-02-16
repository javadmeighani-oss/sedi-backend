# KC Question Fatigue V1 — Server test plan (commands only)

1. `python -m alembic -c backend/alembic.ini upgrade head`
2. `python -c "from backend.app.main import app; print([r.path for r in app.routes if hasattr(r,'path')])"`
3. `curl -s "http://localhost:8000/knowledge/next_question?user_id=1" | python -m json.tool`
4. `curl -s -X POST "http://localhost:8000/knowledge/apply_answer" -H "Content-Type: application/json" -d "{\"user_id\":1,\"question_type\":\"confirm_candidate\",\"candidate_id\":1,\"answer\":\"نه\"}" | python -m json.tool`
5. `curl -s "http://localhost:8000/knowledge/next_question?user_id=1" | python -m json.tool`

*(Adjust base URL and user_id/candidate_id as needed; step 3–5 validate next_question and apply_answer and that blocking/fatigue appears when expected.)*
