"""
evaluation/_ragas_shim.py — Compatibility shim for ragas 0.4.x + langchain-community 0.4.x
============================================================================================
ragas 0.4.3 imports ChatVertexAI / VertexAI from old langchain-community paths
that were removed in langchain-community 0.4.x.  This shim patches sys.modules
so the old import paths resolve to the new langchain-google-vertexai package.

MUST be imported before `import ragas` anywhere in the codebase.

This shim can be removed once ragas releases a fix.
"""

from __future__ import annotations

import sys
import types


def apply() -> None:
    """Patch sys.modules so ragas can import VertexAI from old paths."""
    target = "langchain_community.chat_models.vertexai"
    if target in sys.modules:
        return  # already patched or naturally available

    try:
        from langchain_google_vertexai import ChatVertexAI
    except ImportError:
        # langchain-google-vertexai not installed — create a stub
        # so ragas at least imports (VertexAI features won't work)
        ChatVertexAI = None  # type: ignore[assignment,misc]

    try:
        from langchain_google_vertexai import VertexAI
    except ImportError:
        VertexAI = None  # type: ignore[assignment,misc]

    # Create the fake sub-module
    mod = types.ModuleType(target)
    mod.ChatVertexAI = ChatVertexAI  # type: ignore[attr-defined]
    sys.modules[target] = mod

    # Also patch the llms path if needed
    llms_target = "langchain_community.llms.vertexai"
    if llms_target not in sys.modules:
        llms_mod = types.ModuleType(llms_target)
        llms_mod.VertexAI = VertexAI  # type: ignore[attr-defined]
        sys.modules[llms_target] = llms_mod


# Auto-apply on import
apply()
