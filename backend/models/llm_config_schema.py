from pydantic import BaseModel


class LLMConfigCreate(BaseModel):
    version_id: int
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    system_prompt: str | None = None


class LLMConfigResponse(BaseModel):
    id: int
    version_id: int
    model: str
    temperature: float
    system_prompt: str | None

    class Config:
        orm_mode = True