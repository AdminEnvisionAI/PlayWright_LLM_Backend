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
#     prompt = f"""You are an AEO (Answer Engine Optimization) and GEO (Generative Engine Optimization) expert.

# Analyze this business and generate test prompts to evaluate its AI visibility:

# Website: {domain}
# Brand Name: {analysis.brandName}
# Niche: {analysis.niche}
# Purpose: {analysis.purpose}
# Services: {", ".join(analysis.services)}
# Location: {state}, {nation}

# Generate a comprehensive set of AEO/GEO test questions organized by categories.

# ⚠️ CRITICAL RULES FOR CATEGORIES:

# 1. **Discovery** (REQUIRED - 5-6 questions):
#    - Questions must be GENERIC - NO brand name at all
#    - These test if AI recommends the brand without being asked
#    - Examples: "Best fine dining restaurants in {state}", "Romantic restaurants in {state} for couples"
#    - NEVER include "{analysis.brandName}" in Discovery questions

# 2. **Brand** (REQUIRED - 5-6 questions):
#    - Questions MUST contain the brand name "{analysis.brandName}"
#    - These test AI's knowledge about the brand specifically
#    - Examples: "What is {analysis.brandName} known for?", "Is {analysis.brandName} good for romantic dinner?"
#    - ALWAYS include "{analysis.brandName}" in Brand questions

# 3. **Other Categories** (3-5 business-specific categories):
#    - Create categories based on this specific business type ({analysis.niche})
#    - Mix of branded and non-branded questions
#    - Examples for restaurant: Dining, Occasions, Booking, Reviews
#    - Examples for hotel: Stay, Amenities, Location, Pricing
#    - Each category should have 3-5 questions

# Return ONLY a valid JSON object with this exact structure:
# {{
#   "Discovery": ["generic question 1 (NO brand name)", "generic question 2", ...],
#   "Brand": ["question with {analysis.brandName}", "another with {analysis.brandName}", ...],
#   "CategoryName3": ["question1", "question2", ...],
#   ...
# }}

# IMPORTANT:
# - Discovery category: NEVER use brand name - pure generic queries
# - Brand category: ALWAYS use brand name "{analysis.brandName}"
# - Category names must be single words (PascalCase)
# - Include location "{state}, {nation}" in relevant questions
# - Response must be pure JSON only, no markdown or explanations"""


    prompt = f"""
You are a world-class AEO (Answer Engine Optimization) and GEO (Generative Engine Optimization) strategist. 
Your task is to generate a diverse and highly relevant set of test prompts to evaluate an AI's understanding and ranking of a specific business within its local context.

**Business Analysis:**
- Website: {domain}
- Brand Name: {analysis.brandName}
- Niche: {analysis.niche}
- Purpose: {analysis.purpose}
- Services: {", ".join(analysis.services)}
- Primary Location: {state}, {nation}

**Your Mission:**
Generate a JSON object containing categories of questions. Follow these rules and examples meticulously.

**CRITICAL RULES FOR CATEGORIES:**

1.  **"Discovery" Category (REQUIRED - 5 to 6 questions):**
    *   **Rule:** ABSOLUTELY NO use of the brand name "{analysis.brandName}". Questions must be generic.
    *   **Focus:** Create realistic, intent-driven queries specific to the location and niche.
    *   **Examples (emulate this style):**
        - "what are the best fine dining restaurants in {state}"
        - "what are the best romantic restaurants in {state} for couples"
        - "what are the best luxury dining experiences in {state}"
        - "what are the best restaurants for date night in {state}"
        - "what are the best restaurants in {state} for special occasions"

2.  **"Brand" Category (REQUIRED - 5 to 6 questions):**
    *   **Rule:** MUST ALWAYS include the brand name "{analysis.brandName}".
    *   **Focus:** Ask practical, specific questions a potential customer would have.
    *   **Examples (emulate this style):**
        - "What is {analysis.brandName} known for?"
        - "Is {analysis.brandName} good for a romantic dinner?"
        - "Who should visit {analysis.brandName}?"
        - "What cuisine does {analysis.brandName} serve?"
        - "Is {analysis.brandName} a luxury restaurant?"

3.  **Other Business-Specific Categories (Generate 3 to 4 additional categories):**
    *   **Rule:** Create relevant category names (PascalCase, single word) based on the business niche. Suggestions: `Comparison`, `Experience`, `Local/GEO`, `Booking`, `Events`.
    *   **Content:** Questions can be a mix of branded ("{analysis.brandName}") and non-branded queries.
    *   **Focus on GEO-SPECIFICITY and USER INTENT, inspired by these examples:**
        - **For a `Comparison` category:** "{analysis.brandName} vs a well-known competitor in {state} - which is better for couples?", "Best alternative to {analysis.brandName} in {state}?", "Which is more luxurious: {analysis.brandName} or another popular spot?"
        - **For a `Local/GEO` category:** "Best restaurants near a specific neighborhood in {state}?", "Fine dining restaurants near my location in {state}", "Restaurants open late night in {state}", "Romantic restaurants near the beach in {state}"
        - **For an `Experience` category:** "Restaurants in {state} with a romantic ambience", "Instagrammable luxury restaurants in {state}", "Restaurants in {state} for a calm elegant evening"

**Final Output Requirement:**
Return ONLY a valid JSON object with the specified structure. No introductory text, no markdown.

{{
  "Discovery": ["question 1", "question 2", ...],
  "Brand": ["question 1", "question 2", ...],
  "Comparison": ["question 1", "question 2", ...],
  "Experience": ["question 1", "question 2", ...],
  "Local/GEO": ["question 1", "question 2", ...],
  "Other Category": ["question 1", "question 2", ...]
}}
"""

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
