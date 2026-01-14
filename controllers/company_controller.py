from models.company import Company
from models.project import Project
from beanie import PydanticObjectId
from datetime import datetime
from typing import List, Optional


async def get_all_companies() -> List[dict]:
    companies = await Company.find_all().to_list()
    result = []
    for company in companies:
        project_count = await Project.find(Project.company_id == company.id).count()
        result.append({
            "_id": str(company.id),
            "id": str(company.id),
            "name": company.name,
            "description": company.description,
            "website": company.website,
            "created_at": company.created_at,
            "updated_at": company.updated_at,
            "project_count": project_count
        })
    return result


async def get_company_by_id(company_id: str) -> Optional[dict]:
    company = await Company.get(PydanticObjectId(company_id))
    if not company:
        return None
    
    projects = await Project.find(Project.company_id == company.id).to_list()
    project_list = []
    for project in projects:
        project_list.append({
            "_id": str(project.id),
            "id": str(project.id),
            "name": project.name,
            "description": project.description,
            "domain": project.domain,
            "nation": project.nation,
            "state": project.state
        })
    
    return {
        "_id": str(company.id),
        "id": str(company.id),
        "name": company.name,
        "description": company.description,
        "website": company.website,
        "created_at": company.created_at,
        "updated_at": company.updated_at,
        "project_count": len(project_list),
        "projects": project_list
    }


async def create_company(name: str, description: Optional[str] = None, website: Optional[str] = None) -> Company:
    company = Company(
        name=name,
        description=description,
        website=website,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    await company.insert()
    return company


async def update_company(company_id: str, name: Optional[str] = None, description: Optional[str] = None, website: Optional[str] = None) -> Optional[Company]:
    company = await Company.get(PydanticObjectId(company_id))
    if not company:
        return None
    
    if name is not None:
        company.name = name
    if description is not None:
        company.description = description
    if website is not None:
        company.website = website
    company.updated_at = datetime.utcnow()
    
    await company.save()
    return company


async def delete_company(company_id: str) -> bool:
    company = await Company.get(PydanticObjectId(company_id))
    if not company:
        return False
    
    await Project.find(Project.company_id == PydanticObjectId(company_id)).delete()
    
    await company.delete()
    return True
