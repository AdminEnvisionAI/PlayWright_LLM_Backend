from fastapi import APIRouter, HTTPException
from models.website_analysis import (
    AnalyzeRequest, 
    GenerateQuestionsRequest, 
    AskRequest, 
    AskResponse,
    WebsiteAnalysis,
    Question,
    AskChatGPTRequest
)
from controllers.gemini_controller import generate_questions, ask_gemini
from controllers.chatgpt_controller import ask_chatgpt, analyze_website_chatgpt
from typing import List


router = APIRouter(prefix="/api", tags=["API"])


@router.post("/analyze", response_model=WebsiteAnalysis)
async def analyze_endpoint(request: AnalyzeRequest):
    try:
        result = await analyze_website_chatgpt(
            request.domain, 
            request.nation, 
            request.state,
            request.queryContext or ""
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-questions", response_model=List[Question])
async def generate_questions_endpoint(request: GenerateQuestionsRequest):
    try:
        result = await generate_questions(
            request.analysis, 
            request.domain, 
            request.nation, 
            request.state
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ask", response_model=AskResponse)
async def ask_endpoint(request: AskRequest):
    try:
        answer = await ask_gemini(request.question, request.nation, request.state)
        return AskResponse(answer=answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ask-chatgpt", response_model=AskResponse)
async def ask_chatgpt_endpoint(request: AskChatGPTRequest):
    try:
        answer = await ask_chatgpt(request.question)
        return AskResponse(answer=answer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
