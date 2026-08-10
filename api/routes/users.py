"""
api/routes/users.py — Public-facing per-user resources.
=======================================================
Currently just avatar serving. Kept out of api/routes/auth.py because
everything there is scoped to "the caller's own account" behind
get_current_user, and this endpoint is deliberately neither.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response

from db import client as db_client

router = APIRouter(prefix="/users", tags=["users"])

# Long enough to keep avatars out of the request path on a busy page (a project
# member list renders one per row); short enough that a stale photo self-heals
# even for a client that ignores the ?v= cache-buster.
_AVATAR_MAX_AGE_SECONDS = 300


@router.get(
    "/{user_id}/avatar",
    summary="Fetch a user's profile photo",
    responses={
        200: {"content": {"image/webp": {}}, "description": "The user's profile photo"},
        304: {"description": "Client's cached copy is current"},
        404: {"description": "No profile photo for this user"},
    },
)
def get_user_avatar(user_id: UUID, request: Request) -> Response:
    """Serve a user's profile photo.

    Deliberately unauthenticated. An <img src> cannot carry an Authorization
    header, so requiring a bearer token here would make the endpoint unusable
    for the thing it exists to do. Access is gated by the unguessable row UUID,
    and the exposure is a 256x256 thumbnail the user chose to upload as their
    public-facing identity — the same model GitHub and Gravatar use. Nothing
    else about the user is disclosed: a request for a nonexistent user and one
    for a real user with no photo are both a bare 404.
    """
    avatar = db_client.get_user_avatar(user_id)
    if not avatar:
        raise HTTPException(status_code=404, detail="No profile photo for this user.")

    # Quoted per RFC 9110; the timestamp changes on every replacement, so this
    # is a strong validator without hashing the bytes.
    etag = f'"{avatar["updated_at"].timestamp()}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})

    return Response(
        content=avatar["data"],
        media_type=avatar["mime"],
        headers={
            "ETag": etag,
            "Cache-Control": f"public, max-age={_AVATAR_MAX_AGE_SECONDS}",
        },
    )
