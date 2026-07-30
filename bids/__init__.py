"""
bids/ — contractor marketplace bidding + the Bid Evaluator analysis engine.

Import boundary (AGENTS.md): bids/ -> db/, commerce/, standard library only.
rag/agents/ must NOT import this package directly; a future chat-facing use
(the hiring_contractor persona's "Bid uploads route to the Bid Evaluator")
goes through the DI registry in rag/agents/registry.py instead, wired at
startup by api/main.py — see bids/evaluator.py's AGENT_NAME registration.
"""
