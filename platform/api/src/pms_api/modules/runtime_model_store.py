"""One lookup for new models and pre-migration execution records."""

from pms_api.database.models import RuntimeModel


async def runtime_model(session, model_id, legacy_type=None, **options):
    if model_id is None:
        return None
    row = await session.get(RuntimeModel, model_id, **options)
    if row is None and legacy_type is not None:
        row = await session.get(legacy_type, model_id, **options)
    return row
