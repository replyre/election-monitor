"""How stored media leaves the API.

The type comes from the sender (Telegram's mime_type, an upload's header), so it
is not trusted: a "voice note" typed text/html would run script on this origin
if served inline. Only real image, audio and video types are served inline;
anything else downloads as an opaque file, and every response is sandboxed.
"""

from __future__ import annotations

from fastapi import Response

INLINE_TYPES = frozenset({
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "audio/ogg", "audio/mpeg", "audio/mp4", "audio/aac", "audio/wav", "audio/x-wav",
    "audio/webm", "audio/opus",
    "video/mp4", "video/webm", "video/quicktime",
})


def media_response(data: bytes, mime: str | None) -> Response:
    kind = (mime or "").split(";")[0].strip().lower()
    inline = kind in INLINE_TYPES
    return Response(data, media_type=kind if inline else "application/octet-stream",
                    headers={"Cache-Control": "private, no-store",
                             "Content-Disposition": "inline" if inline else "attachment",
                             "Content-Security-Policy": "default-src 'none'; sandbox",
                             "Referrer-Policy": "no-referrer",
                             "X-Content-Type-Options": "nosniff"})
