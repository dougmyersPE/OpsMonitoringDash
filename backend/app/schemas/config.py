from pydantic import BaseModel


class ConfigItem(BaseModel):
    key: str
    value: str
    description: str | None = None


class ConfigUpdateRequest(BaseModel):
    value: str
    description: str | None = None
