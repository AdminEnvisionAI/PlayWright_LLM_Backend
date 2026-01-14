from beanie import Document, PydanticObjectId
from pydantic import Field, BaseModel
from datetime import datetime
from typing import Optional, List


class Company(Document):
    name: str
    description: Optional[str] = None
    website: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "companies"
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Tech Corp",
                "description": "A technology company",
                "website": "https://techcorp.com"
            }
        }


class CompanyCreate(BaseModel):
    name: str
    description: Optional[str] = None
    website: Optional[str] = None


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None


class CompanyWithProjects(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    website: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    project_count: int = 0
    projects: List[dict] = []
