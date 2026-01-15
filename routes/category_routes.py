from fastapi import APIRouter, HTTPException
from controllers.category_controller import get_all_category_controller,get_prompt_questions_data_controller
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


