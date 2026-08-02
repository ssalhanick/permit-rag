"""
tests/test_kickoff_extract.py — one-shot extraction from free-form kickoff text
================================================================================
The kickoff wizard's "free-form text/talk" entry paths: a user describes
their whole project in their own words, this extracts a best-effort guess
across address/spaces/work_types/materials/budget/persona/comments, and the
frontend pre-fills the existing step-by-step wizard with it for review --
never bypasses the wizard, never a one-shot project creation.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from api.main import app


def test_generate_kickoff_extraction_ollama(monkeypatch) -> None:
    """It should parse Ollama's extraction response into the expected shape."""
    import rag.generator as generator_module

    class DummyCapabilities:
        supports_local_runtime = True
        supports_prompt_caching = False
        provider = "ollama"

    monkeypatch.setattr(generator_module, "get_provider_capabilities", lambda: DummyCapabilities())

    class DummyResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {
                "message": {
                    "content": (
                        '{"address_guess": "123 Main St, Dallas", "spaces": ["kitchen"], '
                        '"work_types": ["plumbing"], "materials": ["quartz countertop"], '
                        '"budget": "$25k", "persona": "diy", "comments": "- Kitchen remodel"}'
                    )
                }
            }

    import requests
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: DummyResponse())

    res = generator_module.generate_kickoff_extraction(
        "I'm redoing my kitchen at 123 Main St in Dallas, quartz countertops, "
        "budget around 25k, doing it myself, need a plumber too"
    )
    assert res["address_guess"] == "123 Main St, Dallas"
    assert res["spaces"] == ["kitchen"]
    assert res["work_types"] == ["plumbing"]
    assert res["materials"] == ["quartz countertop"]
    assert res["budget"] == "$25k"
    assert res["persona"] == "diy"


def test_generate_kickoff_extraction_bounds_comments(monkeypatch) -> None:
    """comments gets the same bound_notes() treatment as the chat path's notes
    field -- same injection-surface discipline, never an unbounded free-text
    blob (STATE.md's "Kickoff demotion" decision)."""
    import rag.generator as generator_module

    class DummyCapabilities:
        supports_local_runtime = True
        supports_prompt_caching = False
        provider = "ollama"

    monkeypatch.setattr(generator_module, "get_provider_capabilities", lambda: DummyCapabilities())

    overlong_comment = "- " + ("filler " * 500)

    class DummyResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {"message": {"content": f'{{"comments": "{overlong_comment}"}}'}}

    import requests
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: DummyResponse())

    res = generator_module.generate_kickoff_extraction("some project description")
    assert len(res["comments"]) < len(overlong_comment)


def test_generate_kickoff_extraction_leaves_unmentioned_fields_empty(monkeypatch) -> None:
    """Fields the model didn't return stay absent -- extraction never guesses."""
    import rag.generator as generator_module

    class DummyCapabilities:
        supports_local_runtime = True
        supports_prompt_caching = False
        provider = "ollama"

    monkeypatch.setattr(generator_module, "get_provider_capabilities", lambda: DummyCapabilities())

    class DummyResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, Any]:
            return {"message": {"content": '{"spaces": ["bathroom"]}'}}

    import requests
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: DummyResponse())

    res = generator_module.generate_kickoff_extraction("redoing my bathroom")
    assert res["spaces"] == ["bathroom"]
    assert res.get("address_guess") is None
    assert res.get("budget") is None


def test_kickoff_extract_route_endpoint(monkeypatch) -> None:
    """POST /projects/kickoff/extract calls the generator and returns its shape."""
    import rag.generator as generator_module

    def dummy_extract(text: str) -> dict[str, Any]:
        assert text == "redoing my kitchen"
        return {
            "address_guess": None,
            "spaces": ["kitchen"],
            "work_types": [],
            "materials": [],
            "budget": None,
            "persona": None,
            "comments": None,
        }

    monkeypatch.setattr(generator_module, "generate_kickoff_extraction", dummy_extract)

    from api.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "00000000-0000-0000-0000-000000000000", "role": "member",
    }
    try:
        client = TestClient(app)
        resp = client.post(
            "/api/projects/kickoff/extract",
            json={"text": "redoing my kitchen"},
            headers={"Authorization": "Bearer dummy_token"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["spaces"] == ["kitchen"]
    finally:
        app.dependency_overrides.clear()


def test_kickoff_extract_route_requires_nonempty_text() -> None:
    """FastAPI should reject an empty text field (min_length=1)."""
    from api.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "00000000-0000-0000-0000-000000000000", "role": "member",
    }
    try:
        client = TestClient(app)
        resp = client.post(
            "/api/projects/kickoff/extract",
            json={"text": ""},
            headers={"Authorization": "Bearer dummy_token"},
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()
