from pydantic import BaseModel


class ChatbotCreate(BaseModel):
    name: str
    description: str | None = None
    language: str
    type: str = "builder"
    project_id: int
    purpose: str = "custom"
    mode: str = "builder"
    channel: str = "web_widget"
    build_method: str = "blank"
    template_key: str | None = None


class ChatbotUpdate(BaseModel):
    name: str
    description: str | None = None
    language: str
    type: str = "builder"
    purpose: str = "custom"
    mode: str = "builder"
    channel: str = "web_widget"
    template_key: str | None = None


class ChatbotStatusUpdate(BaseModel):
    is_active: bool


class ChatbotApiKeyResponse(BaseModel):
    public_api_key: str


class RagSettingsUpdate(BaseModel):
    retrieval_mode: str = "auto"
    max_chunks: int = 3
    min_score: float = 0.2
    show_sources: bool = True
    strict_context: bool = True
    response_length: str = "short"
