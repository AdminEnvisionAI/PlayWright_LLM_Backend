from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from controllers.project_controller import (
    get_projects_by_company,
    get_project_by_id,
    create_project,
    update_project,
    delete_project
)


router = APIRouter(tags=["Projects"])


class ProjectCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    domain: Optional[str] = None
    nation: Optional[str] = None
    state: Optional[str] = None


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    domain: Optional[str] = None
    nation: Optional[str] = None
    state: Optional[str] = None


@router.get("/api/companies/{company_id}/projects")
async def list_company_projects(company_id: str):
    try:
        projects = await get_projects_by_company(company_id)
        return {"projects": projects}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/projects/{project_id}")
async def get_project(project_id: str):
    try:
        project = await get_project_by_id(project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return project
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/companies/{company_id}/projects")
async def add_project(company_id: str, request: ProjectCreateRequest):
    try:
        project = await create_project(
            company_id=company_id,
            name=request.name,
            description=request.description,
            domain=request.domain,
            nation=request.nation,
            state=request.state
        )
        return {"message": "Project created successfully", "project": project}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/api/projects/{project_id}")
async def edit_project(project_id: str, request: ProjectUpdateRequest):
    try:
        project = await update_project(
            project_id=project_id,
            name=request.name,
            description=request.description,
            domain=request.domain,
            nation=request.nation,
            state=request.state
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return {"message": "Project updated successfully", "project": project}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/projects/{project_id}")
async def remove_project(project_id: str):
    try:
        success = await delete_project(project_id)
        if not success:
            raise HTTPException(status_code=404, detail="Project not found")
        return {"message": "Project deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
