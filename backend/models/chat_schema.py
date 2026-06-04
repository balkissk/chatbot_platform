from pydantic import BaseModel

class ChatRequest(BaseModel):
    chatbot_id: int
    message: str
    version_id: int | None = None
    session_id: int | None = None
    current_node_key: str | None = None
    variables: dict | None = None


class ChatSessionCreate(BaseModel):
    chatbot_id: int
    version_id: int | None = None
