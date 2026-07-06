"""tests/api_paths.py — /api prefix helper for TestClient requests."""


def api(path: str) -> str:
    """Return an API path with the production /api namespace prefix."""
    if not path.startswith("/"):
        path = f"/{path}"
    if path.startswith("/api"):
        return path
    return f"/api{path}"
