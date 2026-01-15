from beanie import Document, PydanticObjectId
from typing import Optional, List
from bson import ObjectId
from pydantic import BaseModel, Field
from datetime import datetime


# 🔹 Sub-model for LLM Semantic Tags (ONE-TIME tagging)
class LLMFlags(BaseModel):
    brand_mentioned: bool = False
    brand_rank: Optional[int] = None  # 1, 2, 3... or None
    is_recommended: bool = False
    sentiment: Optional[str] = None  # positive/neutral/negative
    citation_type: Optional[str] = None  # first_party/third_party/none
    features_mentioned: List[str] = []
    competitors_mentioned: List[str] = []


# 🔹 Sub-model for Question + Answer
class QnAModel(BaseModel):
    category_id: PydanticObjectId
    question: str
    answer: Optional[str] = None
    capture: Optional[bool] = False
    category_name: Optional[str] = None
    uuid: Optional[str] = None
    llm_flags: Optional[LLMFlags] = None  # 🆕 LLM semantic tags


class PromptQuestionsModel(Document):
    company_id: Optional[PydanticObjectId]
    project_id: Optional[PydanticObjectId]
    website_url: Optional[str]
    context: Optional[str] = None
    chatgpt_website_analysis: Optional[str] = None
    gemini_website_analysis: Optional[str] = None
    nation: Optional[str] = None
    state: Optional[str] = None
    qna: Optional[List[QnAModel]] = Field(default_factory=list)
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)
    isDeleted: bool = False

    class Settings:
        name = "prompt_questions"

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str,
            PydanticObjectId: str,
            datetime: lambda v: v.isoformat()
        }
