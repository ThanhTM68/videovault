from pydantic import BaseModel, Field, JsonValue


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, JsonValue] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail
