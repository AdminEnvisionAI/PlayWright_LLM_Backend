from beanie import Document, PydanticObjectId
from typing import Optional, List
from bson import ObjectId
from pydantic import BaseModel, Field
from datetime import datetime

class QuestionsCategoryModel(Document):
    name: str
    description: Optional[str] = None
    prompt_instruction: Optional[str] = None
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)
    isDeleted: bool = False

    class Settings:
        name = "questions_category"

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str,
            PydanticObjectId: str,
            datetime: lambda v: v.isoformat()
        }