from pydantic import BaseModel
from typing import List, Optional
from enum import Enum


class Category(str, Enum):
    GENERAL = "General / Discovery"
    INTENT = "Semantic / Intent-Based"
    BRAND = "Brand Name Mention"
    COMPARISON = "Comparison / Alternative"


class WebsiteAnalysis(BaseModel):
    brandName: str
    niche: str
    purpose: str
    services: List[str]


class WebsiteAnalysisResponse(BaseModel):
    website_analysis: WebsiteAnalysis
    prompt_questions_id: str    



class Question(BaseModel):
    id: str
    category: str
    text: str
    category_name: Optional[str] = None
    category_id: Optional[str] = None
    uuid: Optional[str] = None


class EvaluationResult(BaseModel):
    id: str
    category: str
    question: str
    fullAnswer: str
    found: bool
    loading: Optional[bool] = False


class AnalyzeRequest(BaseModel):
    domain: str
    nation: str
    state: str
    queryContext: Optional[str] = ""
    company_id: Optional[str] = ""
    project_id: Optional[str] = ""


class GenerateQuestionsRequest(BaseModel):
    analysis: WebsiteAnalysis
    domain: str
    nation: str
    state: str
    prompt_questions_id: str


class AskRequest(BaseModel):
    question: str
    nation: str
    state: str


class AskResponse(BaseModel):
    answer: str
    prompt_questions_id: Optional[str]=None

class AskChatGPTRequest(BaseModel):
    question: str
    prompt_questions_id: str
    category_id: str
    uuid: Optional[str]=None


class AskGeminiRequest(BaseModel):
    question: str
    prompt_questions_id: str
    category_id: str
    uuid: Optional[str]=None
