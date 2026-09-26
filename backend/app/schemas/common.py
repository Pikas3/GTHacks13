from pydantic import BaseModel, ConfigDict


class Schema(BaseModel):
    """Base for all API/domain schemas. `from_attributes` lets repositories map ORM rows."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=False)
