"""Provider-specific public media ownership evidence."""

from app.comments.models import PublicMedia


def media_ownership_ok(media: PublicMedia, is_simulated: bool) -> bool:
    return media.ownership_state == ("verified_synthetic" if is_simulated else "verified_provider")
