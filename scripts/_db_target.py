"""
scripts/_db_target.py — work out which database a diagnostic is pointed at
==========================================================================
Shared by check_migrations.py and check_migration_details.py.

Knowing the target is not obvious in this project:
  * `api/load_env.py::bootstrap_env` loads `.env` LAST with ``override=True``,
    so a DATABASE_URL there beats `.env.local`.
  * `ENVIRONMENT=production` selects `.env.production` instead.
  * All three dotenv files are gitignored, so the target differs per machine.
  * `.env.local` is not guaranteed to point at localhost — it gets repointed at
    remote hosts during debugging and the edit outlives the session.

So every diagnostic names its target, says which file supplied it, and never
infers "local" from the flag the user passed.

Not a package (scripts/ has no __init__.py); imported by path insertion.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parent.parent

_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "host.docker.internal")


@dataclass(frozen=True)
class Target:
    """Where a diagnostic is about to connect, and how that was decided."""

    url: str
    source: str
    profile: str

    @property
    def host(self) -> str:
        """host:port portion of the URL, or '(unset)'."""
        if "@" not in self.url:
            return "(unset)"
        return self.url.split("@", 1)[1].split("/", 1)[0]

    @property
    def is_local(self) -> bool:
        """True only when the host really is this machine — not merely because
        the caller passed --local."""
        return any(self.host.startswith(prefix) for prefix in _LOCAL_HOSTS)


def canonical_local_url() -> str | None:
    """The DATABASE_URL `.env.local.example` prescribes, if readable."""
    example = dotenv_values(PROJECT_ROOT / ".env.local.example")
    return example.get("DATABASE_URL")


def resolve(argv: list[str], bootstrap) -> Target:
    """
    Decide the target from argv, then set DATABASE_URL to match.

    Supports `--local` (read `.env.local` directly, ignoring later overrides)
    and `--database-url=URL` (bypass dotenv entirely). `bootstrap` is passed in
    rather than imported so this module stays free of the api package.
    """
    # Both spellings: argparse accepts "--database-url URL" as well as
    # "--database-url=URL", and this runs before argparse.
    explicit: str | None = None
    for i, arg in enumerate(argv):
        if arg.startswith("--database-url="):
            explicit = arg.split("=", 1)[1]
            break
        if arg == "--database-url" and i + 1 < len(argv):
            explicit = argv[i + 1]
            break
    if explicit:
        bootstrap()
        os.environ["DATABASE_URL"] = explicit
        return Target(explicit, "--database-url flag", "explicit")

    if "--local" in argv:
        local = dotenv_values(PROJECT_ROOT / ".env.local")
        url = local.get("DATABASE_URL")
        if not url:
            print("--local: .env.local has no DATABASE_URL on this machine.")
            hint = canonical_local_url()
            if hint:
                print(f"  Expected shape (from .env.local.example):\n    {hint}")
            raise SystemExit(1)
        bootstrap()
        os.environ["DATABASE_URL"] = url
        return Target(url, ".env.local (forced by --local)", "local")

    profile = bootstrap()
    return Target(os.environ.get("DATABASE_URL", ""), f"bootstrap_env ({profile})", profile)


def banner(target: Target, *, read_only: bool = True) -> None:
    """Print the target loudly enough that prod is never mistaken for local."""
    print("=" * 72)
    print(f"  Target : {target.host}")
    print(f"  Source : {target.source}")
    if read_only:
        print("  Mode   : READ-ONLY (no writes issued)")
    if not target.is_local:
        print()
        print("  *** THIS HOST IS NOT THIS MACHINE ***")
        if target.source.startswith(".env.local"):
            # The flag did its job; .env.local is what is wrong.
            print("  --local was honoured, but .env.local itself points off-box.")
            hint = canonical_local_url()
            if hint:
                print(f"  For Docker Postgres, .env.local should read:\n    {hint}")
            print("  Or override for one run:")
            print("    py scripts/<script>.py --database-url='<url>'")
        else:
            print("  Re-run with --local to read .env.local instead.")
    print("=" * 72)
    print()


def explain_connection_failure(target: Target, exc: Exception) -> None:
    """Turn a psycopg connection error into something actionable."""
    print(f"Could not connect to {target.host}")
    print(f"  source: {target.source}")
    print(f"  error : {type(exc).__name__}: {str(exc).strip().splitlines()[0]}")
    print()
    if target.is_local:
        print("  Is the container up?   docker compose up -d")
        return
    print("  That host is not this machine, so the likely causes are:")
    print("    * .env.local was repointed at a remote host and left that way")
    print("    * the host is only reachable from another network (VPN / campus)")
    print("    * a security group does not allow this machine's IP")
    hint = canonical_local_url()
    if hint:
        print(f"\n  To target Docker Postgres on this machine:\n    {hint}")
    print("\n  One-off override:")
    print("    py scripts/check_migrations.py --database-url='<url>'")


def ensure_reachable(target: Target, _get_conn=None, *, timeout: int = 5) -> None:
    """
    Fail fast with an explanation instead of a traceback.

    Connects directly rather than through db.client's pool: the pool waits 30s
    before raising PoolTimeout, which is a long time to sit in front of a
    diagnostic that already knows the host is wrong. `_get_conn` is accepted
    and ignored so callers read symmetrically with the rest of this module.
    """
    import psycopg

    if not target.url:
        print("DATABASE_URL is not set for this target.")
        sys.exit(1)
    try:
        with psycopg.connect(target.url, connect_timeout=timeout) as conn:
            conn.execute("SELECT 1;")
    except Exception as exc:
        explain_connection_failure(target, exc)
        sys.exit(1)
