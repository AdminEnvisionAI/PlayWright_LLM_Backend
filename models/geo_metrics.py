from beanie import Document, PydanticObjectId
from typing import Optional, List, Dict, Any
from bson import ObjectId
from pydantic import BaseModel, Field
from datetime import datetime


# 🔹 Sub-model for Brand Agnostic Metrics
class BrandAgnosticMetrics(BaseModel):
    description: str = "Metrics from prompts WITHOUT brand name - shows real organic discovery"
    total_prompts: int = 0
    mentions: int = 0
    brand_mention_rate: float = 0.0
    top_3_mentions: int = 0
    top_3_position_rate: float = 0.0
    recommendation_rate: float = 0.0
    positive_sentiment_rate: float = 0.0
    citations_expected: int = 0
    first_party_citations: int = 0
    first_party_citation_rate: float = 0.0
    zero_mention_count: int = 0
    zero_mention_prompts: List[Dict[str, Any]] = []


# 🔹 Sub-model for Brand Included Metrics
class BrandIncludedMetrics(BaseModel):
    description: str = "Metrics from prompts WITH brand name - shows branded query performance"
    total_prompts: int = 0
    mentions: int = 0
    brand_mention_rate: float = 0.0
    top_3_mentions: int = 0
    top_3_position_rate: float = 0.0
    recommendation_rate: float = 0.0
    positive_sentiment_rate: float = 0.0
    citations_expected: int = 0
    first_party_citations: int = 0
    first_party_citation_rate: float = 0.0
    zero_mention_count: int = 0
    zero_mention_prompts: List[Dict[str, Any]] = []


# 🔹 Main GEO Metrics Document
class GeoMetricsModel(Document):
    prompt_question_id: PydanticObjectId  # Reference to prompt_questions document
    brand_name: str
    total_prompts: int = 0
    using_llm_flags: bool = False
    
    # Segmented Metrics
    brand_agnostic_metrics: Optional[BrandAgnosticMetrics] = None
    brand_included_metrics: Optional[BrandIncludedMetrics] = None
    
    # Combined Metrics (legacy support)
    total_mentions: int = 0
    brand_mention_rate: float = 0.0
    top_3_mentions: int = 0
    top_3_position_rate: float = 0.0
    zero_mention_count: int = 0
    
    # Competitive Metrics
    competitor_mentions: Dict[str, int] = {}
    comparison_presence: float = 0.0
    brand_features: List[str] = []
    
    # Timestamps
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "geo_metrics"

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str,
            PydanticObjectId: str,
            datetime: lambda v: v.isoformat()
        }
