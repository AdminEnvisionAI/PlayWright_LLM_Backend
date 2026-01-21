from fastapi import APIRouter, HTTPException
from controllers.category_controller import (
    get_all_category_controller,
    get_prompt_questions_data_controller,
    calculate_geo_metrics_controller,
    tag_qna_with_llm_controller,
    get_genrated_metrics_controller
)
from fastapi import Request
router = APIRouter(prefix="/api/category",tags=["Category"])

@router.post("/get-all-category")
async def get_all_category():
    try:
        result = await get_all_category_controller()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/get-prompt-questions-data")
async def get_prompt_questions_data(request: Request):
    try:
        print("request",request)
        result = await get_prompt_questions_data_controller(request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tag-qna-with-llm")
async def tag_qna_with_llm(request: Request):
    """
    ONE-TIME LLM semantic tagging for Q&A.
    Call this ONCE after answers are generated, then use /calculate-geo-metrics for fast results.
    """
    try:
        result = await tag_qna_with_llm_controller(request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/calculate-geo-metrics")
async def calculate_geo_metrics(request: Request):
    try:
        result = await calculate_geo_metrics_controller(request)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/get-genrated-metrics")
async def get_genrated_metrics(request: Request):
    try:
        result = await get_genrated_metrics_controller(request)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
