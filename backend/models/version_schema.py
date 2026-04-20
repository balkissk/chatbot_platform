from pydantic import BaseModel

class VersionCreate(BaseModel):
    chatbot_id: int