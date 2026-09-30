"""
Integration tests: real HTTP requests through the FastAPI app, with a temporary
SQLite database and upload folder (see conftest.py).
"""

import pytest

import app.engine.query_parser as qp
from app.core.config import settings
from helpers import AFTER_CSV, BEFORE_CSV, signup, upload


def query(client, headers, ids, mapping, question, export=False):
    return client.post("/analysis/query", headers=headers, json={
        "file_ids": ids, "mapping": mapping, "question": question, "export": export,
    })


# ---------------------------------------------------------------------------
# Health and authentication
# ---------------------------------------------------------------------------

def test_health_reports_basic_mode(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["ai_configured"] is False
    assert body["ai_chain"] == []


def test_signup_returns_token(client):
    resp = client.post("/auth/signup", json={
        "email": "prof@example.edu", "username": "prof_jones", "password": "password123",
    })
    assert resp.status_code == 201
    assert resp.json()["username"] == "prof_jones"
    assert resp.json()["access_token"]


@pytest.mark.parametrize("payload, status", [
    ({"email": "a@example.edu", "username": "ab", "password": "password123"}, 422),        # username too short
    ({"email": "a@example.edu", "username": "bad name!", "password": "password123"}, 422),  # invalid characters
    ({"email": "a@example.edu", "username": "valid", "password": "short"}, 422),            # password too short
    ({"email": "not-an-email", "username": "valid", "password": "password123"}, 422),
])
def test_signup_validation(client, payload, status):
    assert client.post("/auth/signup", json=payload).status_code == status


def test_signup_rejects_duplicate_email_and_username(client):
    signup(client, "alice", "alice@example.edu")
    dup_email = client.post("/auth/signup", json={
        "email": "alice@example.edu", "username": "other", "password": "password123"})
    dup_user = client.post("/auth/signup", json={
        "email": "other@example.edu", "username": "alice", "password": "password123"})
    assert (dup_email.status_code, dup_email.json()["detail"]) == (400, "Email already registered")
    assert (dup_user.status_code, dup_user.json()["detail"]) == (400, "Username already taken")


@pytest.mark.parametrize("identifier", ["alice", "alice@example.edu", "ALICE@example.edu"])
def test_login_with_username_or_email(client, identifier):
    signup(client, "alice", "alice@example.edu")
    resp = client.post("/auth/login", json={"identifier": identifier, "password": "password123"})
    assert resp.status_code == 200


def test_login_wrong_password_gives_neutral_error(client):
    signup(client, "alice")
    resp = client.post("/auth/login", json={"identifier": "alice", "password": "wrong-password"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid email/username or password"


def test_me_requires_a_valid_token(client, auth):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/auth/me", headers=auth).json()["username"] == "alice"


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

def test_upload_detects_columns_and_rows(client, auth):
    body = upload(client, auth, BEFORE_CSV, "Before").json()
    assert body["detected_columns"] == ["StudentName", "Major", "Year", "Gender", "AssignmentGrade"]
    assert body["row_count"] == 50
    assert body["term_label"] == "Before"


def test_upload_rejects_non_csv(client, auth):
    resp = client.post("/files/upload", headers=auth,
                       files={"file": ("notes.txt", b"hello", "text/plain")})
    assert resp.status_code == 400


def test_upload_requires_login(client):
    assert upload(client, {}, BEFORE_CSV).status_code == 401


def test_list_update_and_delete_file(client, auth):
    file_id = upload(client, auth, BEFORE_CSV).json()["file_id"]
    assert [f["id"] for f in client.get("/files/list", headers=auth).json()] == [file_id]

    patched = client.patch(f"/files/{file_id}/term", headers=auth, json={"term_label": "FA24"})
    assert patched.json()["term_label"] == "FA24"

    stored = settings.uploads_dir / patched.json()["stored_filename"]
    assert stored.exists()
    assert client.delete(f"/files/{file_id}", headers=auth).status_code == 204
    assert not stored.exists()
    assert client.get("/files/list", headers=auth).json() == []


def test_users_cannot_access_each_others_files(client, auth, sample_mapping):
    file_id = upload(client, auth, BEFORE_CSV).json()["file_id"]
    bob = signup(client, "bob")

    assert client.get("/files/list", headers=bob).json() == []
    assert client.patch(f"/files/{file_id}/term", headers=bob, json={"term_label": "x"}).status_code == 404
    assert client.delete(f"/files/{file_id}", headers=bob).status_code == 404
    assert query(client, bob, [file_id], sample_mapping, "Show grade distribution").status_code == 404
    # ...and the owner's file is untouched
    assert len(client.get("/files/list", headers=auth).json()) == 1


# ---------------------------------------------------------------------------
# Column mappings
# ---------------------------------------------------------------------------

def test_mapping_suggest_save_and_reuse(client, auth):
    cols = ["StudentName", "Major", "AssignmentGrade"]
    suggestion = client.post("/mappings/suggest", headers=auth, json={"columns": cols}).json()
    assert suggestion["suggestions"]["grade"] == "AssignmentGrade"
    fp = suggestion["fingerprint"]

    assert client.get(f"/mappings/saved/{fp}", headers=auth).status_code == 404
    client.post("/mappings/save", headers=auth, json={"columns_fingerprint": fp, "mapping": {"grade": "AssignmentGrade"}})
    client.post("/mappings/save", headers=auth, json={"columns_fingerprint": fp, "mapping": {"grade": "Major"}})  # upsert
    assert client.get(f"/mappings/saved/{fp}", headers=auth).json()["mapping"] == {"grade": "Major"}

    bob = signup(client, "bob")
    assert client.get(f"/mappings/saved/{fp}", headers=bob).status_code == 404


# ---------------------------------------------------------------------------
# Analysis end to end (basic mode, no LLM)
# ---------------------------------------------------------------------------

def test_compare_majors_end_to_end(client, two_files):
    headers, ids, mapping = two_files
    body = query(client, headers, ids, mapping, "Compare CS vs Biology students").json()
    assert body["raw_intent"]["intent_type"] == "compare_majors"
    cards = {c["label"]: c for c in body["comparison_cards"]}
    assert cards["Computer Science"]["mean"] == 79.17
    assert cards["Biology"]["mean"] == 76.89
    assert body["stat_tests"][0]["p_value"] == 0.3362
    assert len(body["charts"]) == 2 and all(c["image_b64"] for c in body["charts"])


def test_top_improvers_end_to_end(client, two_files):
    headers, ids, mapping = two_files
    body = query(client, headers, ids, mapping, "Which students improved the most?").json()
    table = next(t for t in body["tables"] if t["title"] == "Top Improvers")
    assert table["rows"][0]["Student Name"] == "Student 031"
    assert body["summary"].startswith("Student 031 from Biology improved the most")


def test_improvers_with_one_file_explains_what_is_missing(client, two_files):
    headers, ids, mapping = two_files
    body = query(client, headers, ids[:1], mapping, "Which students improved the most?").json()
    assert "requires two uploaded files" in body["summary"]


@pytest.mark.parametrize("ids", [[], [1, 2, 3]])
def test_query_needs_one_or_two_files(client, auth, sample_mapping, ids):
    assert query(client, auth, ids, sample_mapping, "anything").status_code == 400


def test_excel_export_download(client, two_files):
    headers, ids, mapping = two_files
    session_id = query(client, headers, ids, mapping, "Show grade distribution", export=True).json()["export_session_id"]
    resp = client.get(f"/analysis/export/{session_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"   # .xlsx files are zip archives
    assert client.get("/analysis/export/doesnotexist", headers=headers).status_code == 404


# ---------------------------------------------------------------------------
# Analysis end to end with the LLM failover chain (providers faked)
# ---------------------------------------------------------------------------

@pytest.fixture
def llm_chain(monkeypatch):
    monkeypatch.setattr(settings, "ai_provider", "gemini,openai")
    monkeypatch.setattr(settings, "gemini_api_key", "gem-test-key")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-key")

    def install(gemini_intent=None, openai_intent=None, gemini_summary=None, openai_summary=None):
        async def returns(value):
            return value
        monkeypatch.setattr(qp, "_gemini_parse_intent", lambda q, c: returns(gemini_intent))
        monkeypatch.setattr(qp, "_openai_parse_intent", lambda q, c: returns(openai_intent))
        monkeypatch.setattr(qp, "_gemini_generate_summary", lambda q, r: returns(gemini_summary))
        monkeypatch.setattr(qp, "_openai_generate_summary", lambda q, r: returns(openai_summary))
    return install


def test_health_reports_the_chain(client, llm_chain):
    body = client.get("/health").json()
    assert body["ai_configured"] is True
    assert body["ai_chain"] == ["gemini", "openai"]


def test_llm_intent_and_summary_are_used(client, two_files, llm_chain):
    llm_chain(gemini_intent={"intent_type": "grade_bands", "filters": {}}, gemini_summary="Gemini wrote this.")
    headers, ids, mapping = two_files
    # The question alone would be parsed as a summary by the rules; the LLM's intent wins.
    body = query(client, headers, ids, mapping, "How are my students doing on letter grades?").json()
    assert body["raw_intent"]["intent_type"] == "grade_bands"
    assert body["summary"] == "Gemini wrote this."


def test_second_provider_answers_when_first_fails(client, two_files, llm_chain):
    llm_chain(openai_intent={"intent_type": "grade_bands"}, openai_summary="OpenAI wrote this.")
    headers, ids, mapping = two_files
    body = query(client, headers, ids, mapping, "How are my students doing on letter grades?").json()
    assert body["raw_intent"]["intent_type"] == "grade_bands"
    assert body["summary"] == "OpenAI wrote this."


def test_every_provider_failing_still_returns_a_correct_answer(client, two_files, llm_chain):
    llm_chain()   # every provider returns nothing
    headers, ids, mapping = two_files
    resp = query(client, headers, ids, mapping, "Which students improved the most?")
    assert resp.status_code == 200
    body = resp.json()
    assert body["raw_intent"]["intent_type"] == "top_improvers"   # rule-based parser
    assert body["summary"].startswith("Student 031 from Biology improved the most")   # template


def test_llm_never_changes_the_numbers(client, two_files, llm_chain):
    """Whatever the LLM writes, the statistics come from the engine."""
    llm_chain(gemini_intent={"intent_type": "compare_majors", "compare_major_a": "Computer Science",
                             "compare_major_b": "Biology", "filters": {}},
              gemini_summary="CS averaged 99.9 (a hallucinated number).")
    headers, ids, mapping = two_files
    body = query(client, headers, ids, mapping, "Compare CS vs Biology students").json()
    cards = {c["label"]: c for c in body["comparison_cards"]}
    assert cards["Computer Science"]["mean"] == 79.17


def test_grade_bands_work_with_one_file(client, two_files):
    headers, ids, mapping = two_files
    body = query(client, headers, ids[:1], mapping, "Show grade distribution").json()
    assert body["raw_intent"]["intent_type"] == "grade_bands"
    assert body["summary"].startswith("Of 50 students")


# Every question type, with one file and with two: each must return a
# summary and data, never a server error.
ALL_QUESTION_TYPES = [
    ("Summarize the overall performance of students", "summary_one_file"),
    ("Compare the two terms", "compare_terms"),
    ("Compare CS vs Biology students", "compare_majors"),
    ("Which major has the highest mean grade?", "best_major"),
    ("Which major performed worst?", "worst_major"),
    ("Show the SLO attainment distribution", "slo_distribution"),
    ("Which student performed the best?", "best_student"),
    ("Which student had the lowest grade?", "worst_student"),
    ("Which students improved the most?", "top_improvers"),
    ("Which students declined the most?", "biggest_declines"),
    ("Show grade distribution", "grade_bands"),
]


@pytest.mark.parametrize("n_files", [1, 2])
@pytest.mark.parametrize("question, intent", ALL_QUESTION_TYPES)
def test_every_question_type(client, two_files, question, intent, n_files):
    headers, ids, mapping = two_files
    resp = query(client, headers, ids[:n_files], mapping, question)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    if not (intent == "compare_terms" and n_files == 1):
        assert body["raw_intent"]["intent_type"] == intent
    assert body["summary"]
    assert body["tables"] or body["charts"] or body["stat_tests"] or "two uploaded files" in body["summary"]
