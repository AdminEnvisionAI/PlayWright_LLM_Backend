from beanie import Document, PydanticObjectId
from pydantic import Field, BaseModel
from datetime import datetime
from typing import Optional


class Project(Document):
    name: str
    description: Optional[str] = None
    company_id: PydanticObjectId
    domain: Optional[str] = None
    nation: Optional[str] = None
    state: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Settings:
        name = "projects"
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Website Analysis",
                "description": "Main website analysis project",
                "domain": "example.com",
                "nation": "USA",
                "state": "California"
            }
        }


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    domain: Optional[str] = None
    nation: Optional[str] = None
    state: Optional[str] = None


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    domain: Optional[str] = None
    nation: Optional[str] = None
    state: Optional[str] = None
