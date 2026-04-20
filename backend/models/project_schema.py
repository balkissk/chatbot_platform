from pydantic import BaseModel

class ProjectCreate(BaseModel):
    name: str
    description: str
    user_id: int