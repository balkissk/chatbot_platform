from datetime import datetime

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: str


class ProjectUpdate(BaseModel):
    name: str
    description: str


class ProjectResponse(BaseModel):
    id: int
    name: str
    description: str
    user_id: int
    created_at: datetime
    chatbot_count: int = 0
    version_count: int = 0
    published_version_count: int = 0


class ProjectOverview(ProjectResponse):
    draft_version_count: int = 0
    archived_version_count: int = 0
