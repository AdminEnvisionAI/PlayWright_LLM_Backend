from fastapi import HTTPException
from models.questionsCategory import QuestionsCategoryModel
from models.prompt_questions import PromptQuestionsModel
from fastapi import Request
from bson import ObjectId
from global_db_opretions import find_one

async def get_all_category_controller():
    try:
        result = await QuestionsCategoryModel.find_all().to_list()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_prompt_questions_data_controller(request: Request):
    try:
        body = await request.json()
        project_id = body.get("project_id")
        result = await find_one(PromptQuestionsModel,{"project_id": ObjectId(project_id)})
        return result
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))      