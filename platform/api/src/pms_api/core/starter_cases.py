"""Identify the reviewed bundled revision, independently of administrator edits."""

from uuid import UUID

from training_contracts import fingerprint

PREVIOUS_STARTER_HASHES = {
    UUID(
        "00000000-0000-4000-8000-000000000501"
    ): "6a3df0c0ed80b4081d99064c9b62fe6f5a639b0ce5df66871c18534a166d3755",
    UUID(
        "00000000-0000-4000-8000-000000000507"
    ): "94e97c84f6d02cb6458763be8650901c20aef2b176a38e4e43401bd65acf5ef7",
}

STARTER_HASHES = {
    UUID(
        "00000000-0000-4000-8000-000000000501"
    ): "07584c20d71e8b12c0b7dece2b5b41f43a61ce8731e398e30cdb2f5bf0fe225f",
    UUID(
        "00000000-0000-4000-8000-000000000507"
    ): "bff6d2da9aa2b255aa3981396eeeebf06a6d7a3ec9386b3f3d3dd28d4813ac1a",
}


def corrected_starter(
    template_id: UUID, revision: int, document: dict, *, allow_previous: bool = False
) -> bool:
    hashes = PREVIOUS_STARTER_HASHES if allow_previous and revision == 5 else STARTER_HASHES
    return (
        (revision == 6 or allow_previous and revision == 5)
        and template_id in hashes
        and fingerprint(document) == hashes[template_id]
    )
