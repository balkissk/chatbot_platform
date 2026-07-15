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
    assistant_count: int = 0
    published_assistant_count: int = 0
    draft_only_assistant_count: int = 0
    last_activity_at: datetime | None = None


class ProjectOverview(ProjectResponse):
    draft_version_count: int = 0
    archived_version_count: int = 0


class ProjectSummaryResponse(BaseModel):
    projects: int = 0
    assistants: int = 0
    published_assistants: int = 0
    draft_only: int = 0
