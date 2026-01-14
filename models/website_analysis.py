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


class Question(BaseModel):
    id: str
    category: str
    text: str


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


class GenerateQuestionsRequest(BaseModel):
    analysis: WebsiteAnalysis
    domain: str
    nation: str
    state: str


class AskRequest(BaseModel):
    question: str
    nation: str
    state: str


class AskResponse(BaseModel):
    answer: str


class AskChatGPTRequest(BaseModel):
    question: str
