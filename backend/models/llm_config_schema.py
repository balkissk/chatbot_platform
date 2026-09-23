from pydantic import BaseModel


class LLMConfigCreate(BaseModel):
    version_id: int
    model: str = "llama3"
    temperature: float = 0.7
    system_prompt: str | None = None
    tone: str | None = "Professional"
    language: str | None = "French"
    response_style: str | None = "Concise"


class LLMConfigResponse(BaseModel):
    id: int
    version_id: int
    model: str
    temperature: float
    system_prompt: str | None
    tone: str | None = None
    language: str | None = None
    response_style: str | None = None

    class Config:
        from_attributes = True
