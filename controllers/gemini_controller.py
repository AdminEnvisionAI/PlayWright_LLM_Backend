import os
import json
import re
from dotenv import load_dotenv
import google.generativeai as genai
from models.website_analysis import WebsiteAnalysis, Question
from models.questionsCategory import QuestionsCategoryModel
from models.prompt_questions import PromptQuestionsModel
from global_db_opretions import update_one
from bson import ObjectId
import uuid
load_dotenv()

API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("API_KEY", "")

if not API_KEY:
    raise ValueError(
        "No API_KEY or GOOGLE_API_KEY found. Please set the GOOGLE_API_KEY environment variable "
        "in your .env file or system environment."
    )

genai.configure(api_key=API_KEY)


def extract_json(text: str):
    text = text.strip()
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if json_match:
        text = json_match.group(1).strip()
    
    if text.startswith('[') or text.startswith('{'):
        return json.loads(text)
    
    json_pattern = r'[\[\{][\s\S]*[\]\}]'
    match = re.search(json_pattern, text)
    if match:
        return json.loads(match.group())
    
    return json.loads(text)


async def analyze_website(domain: str, nation: str, state: str) -> WebsiteAnalysis:
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = f"""Analyze the website with domain "{domain}". The target audience is in {state}, {nation}. 
    Identify its core brand name, market niche, main purpose, and key products/services. 
    Be as accurate as possible. If the website is obscure, make a best-guess based on the URL structure or common naming patterns.
    
    Return the response as a valid JSON object ONLY (no markdown, no extra text) with these exact fields:
    - brandName: string
    - niche: string
    - purpose: string
    - services: array of strings
    
    Response must be pure JSON only."""
    
    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.7
        )
    )
    
    result = extract_json(response.text)
    return WebsiteAnalysis(**result)


async def generate_questions(analysis: WebsiteAnalysis, domain: str, nation: str, state: str, prompt_questions_id: str) -> list[Question]:
    """
    🔥 DYNAMIC AEO/GEO Question Generation
    - Categories are generated dynamically based on website/business type
    - Questions are tailored for each category
    - No static DB categories used
    """
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    # 🔥 Step 1: Generate dynamic categories and questions based on business type
    prompt = f"""You are an AEO (Answer Engine Optimization) and GEO (Generative Engine Optimization) expert.

Analyze this business and generate test prompts to evaluate its AI visibility:

Website: {domain}
Brand Name: {analysis.brandName}
Niche: {analysis.niche}
Purpose: {analysis.purpose}
Services: {", ".join(analysis.services)}
Location: {state}, {nation}

Generate a comprehensive set of AEO/GEO test questions organized by categories.
Each category should be a SINGLE WORD that describes the intent type.

Guidelines:
1. Create 6-8 relevant categories based on this specific business type
2. Each category should have 4-6 questions
3. Questions should be the type users would ask AI assistants (ChatGPT, Gemini, Perplexity)
4. Mix brand-specific questions with generic discovery questions
5. Include location-based queries with "{state}" or "{nation}"
6. Focus on questions that could lead to recommendations

Example categories for a restaurant/resort:
- Discovery: "What is [brand] known for?"
- LocalIntent: "Best restaurant near me for fine dining"
- Dining: "What cuisine does [brand] serve?"
- Stay: "Does [brand] offer accommodation?"
- Occasions: "Best place for anniversary celebration"
- Planning: "How to book a table at [brand]?"
- Comparison: "Best luxury dining in [city]"
- Trust: "Is [brand] worth visiting?"

Return ONLY a valid JSON object with this exact structure:
{{
  "CategoryName1": ["question1", "question2", "question3", ...],
  "CategoryName2": ["question1", "question2", "question3", ...],
  ...
}}

IMPORTANT:
- Category names must be single words (PascalCase)
- Each category must have 4-6 questions
- Replace [brand] with "{analysis.brandName}" in questions
- Include location "{state}, {nation}" in relevant questions
- Response must be pure JSON only, no markdown or explanations"""

    try:
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.7,
                response_mime_type="application/json"
            )
        )
        
        categories_data = extract_json(response.text)
        
        if not isinstance(categories_data, dict):
            print("Error: AI did not return a valid JSON object.")
            return []
        
        print(f"🔥 Generated {len(categories_data)} dynamic categories: {list(categories_data.keys())}")
        
        questions = []
        qna_list = []
        
        for category_name, category_questions in categories_data.items():
            if not isinstance(category_questions, list):
                continue
                
            for question_text in category_questions:
                if not question_text or not isinstance(question_text, str):
                    continue
                
                uuid_id = str(uuid.uuid4())
                
                # Create Question object for frontend
                questions.append(Question(
                    id=uuid_id,
                    category=category_name,
                    text=question_text,
                    category_name=category_name,
                    category_id=uuid_id,
                    uuid=uuid_id
                ))
                
                # Create QnA entry for database
                qna_list.append({
                    "question": question_text,
                    "answer": "Not available yet",
                    "category_id": ObjectId(),  # Generate new ObjectId for each
                    "category_name": category_name,
                    "uuid": uuid_id
                })
        
        print(f"✅ Generated {len(questions)} total questions across {len(categories_data)} categories")
        
        # Save to database
        if qna_list:
            await update_one(
                PromptQuestionsModel,
                {"_id": ObjectId(prompt_questions_id)},
                {"$set": {"qna": qna_list}}
            )
        
        return questions
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"An error occurred during question generation: {e}")
        return []

async def ask_gemini(question: str, nation: str, state: str) -> str:
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    prompt = f"""{question} 
    Please recommend specific websites that best address this query for a user specifically in {state}, {nation}. 
    Ensure the recommendations are highly relevant to this geographical location."""
    
    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.7,
            top_p=0.8,
            top_k=40
        )
    )
    
    return response.text if response.text else "No response from model."
