from pydantic import BaseModel
from sqlalchemy import inspect

from pms_api.core.common import require


def changes(body: BaseModel, exclude: set[str] | None = None) -> dict:
    values = body.model_dump(mode="python", exclude=exclude or set())
    result = {key: values[key] for key in body.model_fields_set if key in values}
    # JSON settings need complete nested defaults, while omitted top-level fields stay unchanged.
    for key in result:
        original = getattr(body, key)
        if isinstance(original, BaseModel):
            result[key] = original.model_dump(mode="json", exclude_none=True)
    return result


def update_fields(row, values: dict):
    columns = inspect(row).mapper.columns
    for key, value in values.items():
        require(value is not None or columns[key].nullable, "null_not_allowed", f"{key} cannot be null")
        setattr(row, key, value)
