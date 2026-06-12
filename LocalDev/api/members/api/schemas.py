from pydantic import BaseModel
from typing import Optional

class UserProfile(BaseModel):
    id: str
    name: str
    email: str
    role: str
    chapter_id: str
    chapter_name: Optional[str] = None


