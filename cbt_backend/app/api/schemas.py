from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    mode: str = Field(default="human_optional", description="human_optional | auto | human_required")


class CreateSessionResponse(BaseModel):
    thread_id: str


class SessionListItem(BaseModel):
    thread_id: str
    created_at: str
    mode: str
