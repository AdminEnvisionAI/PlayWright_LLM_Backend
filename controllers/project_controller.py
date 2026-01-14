from models.project import Project
from beanie import PydanticObjectId
from datetime import datetime
from typing import List, Optional


async def get_projects_by_company(company_id: str) -> List[dict]:
    projects = await Project.find(Project.company_id == PydanticObjectId(company_id)).to_list()
    result = []
    for project in projects:
        result.append({
            "_id": str(project.id),
            "id": str(project.id),
            "name": project.name,
            "description": project.description,
            "company_id": str(project.company_id),
            "domain": project.domain,
            "nation": project.nation,
            "state": project.state,
            "created_at": project.created_at,
            "updated_at": project.updated_at
        })
    return result


async def get_project_by_id(project_id: str) -> Optional[dict]:
    project = await Project.get(PydanticObjectId(project_id))
    if not project:
        return None
    return {
        "_id": str(project.id),
        "id": str(project.id),
        "name": project.name,
        "description": project.description,
        "company_id": str(project.company_id),
        "domain": project.domain,
        "nation": project.nation,
        "state": project.state,
        "created_at": project.created_at,
        "updated_at": project.updated_at
    }


async def create_project(
    company_id: str,
    name: str,
    description: Optional[str] = None,
    domain: Optional[str] = None,
    nation: Optional[str] = None,
    state: Optional[str] = None
) -> Project:
    project = Project(
        name=name,
        description=description,
        company_id=PydanticObjectId(company_id),
        domain=domain,
        nation=nation,
        state=state,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    await project.insert()
    return project


async def update_project(
    project_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    domain: Optional[str] = None,
    nation: Optional[str] = None,
    state: Optional[str] = None
) -> Optional[Project]:
    project = await Project.get(PydanticObjectId(project_id))
    if not project:
        return None
    
    if name is not None:
        project.name = name
    if description is not None:
        project.description = description
    if domain is not None:
        project.domain = domain
    if nation is not None:
        project.nation = nation
    if state is not None:
        project.state = state
    project.updated_at = datetime.utcnow()
    
    await project.save()
    return project


async def delete_project(project_id: str) -> bool:
    project = await Project.get(PydanticObjectId(project_id))
    if not project:
        return False
    
    await project.delete()
    return True
