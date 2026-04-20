from pydantic import BaseModel

class ChatRequest(BaseModel):
    chatbot_id: int
    message: str