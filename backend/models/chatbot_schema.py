from pydantic import BaseModel

class ChatbotCreate(BaseModel):
    name: str
    language: str
    type: str          
    project_id: int