"""Plain helper functions shared by the API tests."""

from pathlib import Path

SAMPLES = Path(__file__).resolve().parents[2] / "frontend" / "public" / "samples"
BEFORE_CSV = SAMPLES / "assessment_before.csv"
AFTER_CSV = SAMPLES / "assessment_after.csv"


def signup(client, username="alice", email=None, password="password123"):
    """Create an account and return auth headers for it."""
    resp = client.post("/auth/signup", json={
        "email": email or f"{username}@example.edu",
        "username": username,
        "password": password,
    })
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def upload(client, headers, path=BEFORE_CSV, term_label=None):
    data = {"term_label": term_label} if term_label else {}
    with open(path, "rb") as f:
        return client.post(
            "/files/upload",
            headers=headers,
            files={"file": (path.name, f, "text/csv")},
            data=data,
        )
