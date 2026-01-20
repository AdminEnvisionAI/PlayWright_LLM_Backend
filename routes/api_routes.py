from fastapi import APIRouter, HTTPException
from models.website_analysis import (
    AnalyzeRequest, 
    GenerateQuestionsRequest, 
    AskRequest, 
    AskResponse,
    WebsiteAnalysis,
    WebsiteAnalysisResponse,
    Question,
    AskChatGPTRequest
)
# All endpoints now use ChatGPT controller instead of Gemini
from controllers.chatgpt_controller import (
    ask_chatgpt, 
    analyze_website_chatgpt, 
    generate_questions_chatgpt,
    ask_chatgpt_with_location
)
from typing import List


router = APIRouter(prefix="/api", tags=["API"])


@router.post("/analyze", response_model=WebsiteAnalysisResponse)
async def analyze_endpoint(request: AnalyzeRequest):
    try:
        print("hello--->",request)
        result = await analyze_website_chatgpt(
            request.domain, 
            request.nation, 
            request.state,
            request.queryContext or "",
            request.company_id,
            request.project_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-questions", response_model=List[Question])
async def generate_questions_endpoint(request: GenerateQuestionsRequest):
    try:
        # Now using ChatGPT for question generation
        result = await generate_questions_chatgpt(
            request.analysis, 
            request.domain, 
            request.nation, 
            request.state,
            request.prompt_questions_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ask", response_model=AskResponse)
async def ask_endpoint(request: AskRequest):
    try:
        # Now using ChatGPT instead of Gemini
        answer = await ask_chatgpt_with_location(request.question, request.nation, request.state)
        return AskResponse(answer=answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ask-chatgpt", response_model=AskResponse)
async def ask_chatgpt_endpoint(request: AskChatGPTRequest):
    try:
        answer = await ask_chatgpt(request.question,request.prompt_questions_id,request.category_id,request.uuid)
        return AskResponse(answer=answer,prompt_questions_id=request.prompt_questions_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




