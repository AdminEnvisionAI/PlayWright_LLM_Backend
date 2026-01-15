from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from controllers.company_controller import (
    get_all_companies,
    get_company_by_id,
    create_company,
    update_company,
    delete_company
)


router = APIRouter(prefix="/api/companies", tags=["Companies"])


class CompanyCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    website: Optional[str] = None


class CompanyUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None


@router.post("")
async def list_companies():
    try:
        companies = await get_all_companies()
        return {"companies": companies}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{company_id}")
async def get_company(company_id: str):
    try:
        company = await get_company_by_id(company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        return company
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def add_company(request: CompanyCreateRequest):
    try:
        company = await create_company(
            name=request.name,
            description=request.description,
            website=request.website
        )
        return {"message": "Company created successfully", "company": company}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{company_id}")
async def edit_company(company_id: str, request: CompanyUpdateRequest):
    try:
        company = await update_company(
            company_id=company_id,
            name=request.name,
            description=request.description,
            website=request.website
        )
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        return {"message": "Company updated successfully", "company": company}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{company_id}")
async def remove_company(company_id: str):
    try:
        success = await delete_company(company_id)
        if not success:
            raise HTTPException(status_code=404, detail="Company not found")
        return {"message": "Company and all its projects deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
