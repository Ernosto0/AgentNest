"""Historical render versions win over current caption grounding."""

import uuid

from app.content.templates.link import merge_references


def test_render_version_wins_and_duplicates_are_removed():
    one, two = uuid.uuid4(), uuid.uuid4()
    assert merge_references(((one, 2), (two, 1)), ((one, 1),)) == ((one, 1), (two, 1))
