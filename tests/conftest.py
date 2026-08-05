"""
tests/conftest.py — session-wide test safety nets
===================================================
Shared fixtures that apply across the whole suite. Kept minimal and
additive -- individual test files stay responsible for their own
test-specific mocking; this file exists for safety nets a test author
could otherwise forget, not test-specific behavior.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _no_real_nli_model_load():
    """
    Never let a test load the real HuggingFace NLI model.

    ``classify_permit_types()`` defaults to ``use_nli=True``, and
    ``rag/agents/registry.py`` self-registers the real callable at import
    time -- any test that resolves "permit_classifier" from the registry
    without its own stub (e.g. via the Manager) hits
    ``_load_nli_classifier()`` for real. That downloads/loads a ~85MB
    transformers model (``torch``/``sklearn``/``pandas`` in the import
    chain), which is slow, memory-heavy enough to OOM-kill on constrained
    machines, and makes real network calls -- exactly what AGENTS.md's
    "fully mocked on machine A" guarantee promises never happens.
    ``test_permit_classifier.py`` still patches this same target itself to
    test the NLI path directly; that local patch nests inside this one for
    the duration of those specific tests.
    """
    with patch("rag.permit_classifier._load_nli_classifier", return_value=None):
        yield
