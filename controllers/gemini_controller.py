import os
import json
import re
from dotenv import load_dotenv
import google.generativeai as genai
from models.website_analysis import WebsiteAnalysis, Question, Category

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


async def generate_questions(analysis: WebsiteAnalysis, domain: str, nation: str, state: str) -> list[Question]:
    model = genai.GenerativeModel("gemini-2.5-flash")
    
    services_str = ", ".join(analysis.services) if analysis.services else analysis.niche
    first_service = analysis.services[0] if analysis.services else analysis.niche
    
    prompt = f"""Based on this website analysis for {domain}:
    Brand Name: {analysis.brandName}
    Niche: {analysis.niche}
    Purpose: {analysis.purpose}
    Services: {services_str}
    Location Context: {state}, {nation}

    Your goal is to generate questions that seek direct recommendations, lists of top providers, or ask who the "best" is. Avoid questions that only ask for general information.

    Generate exactly 1 question for each of the following 4 categories.
    IMPORTANT: Each question must naturally invite a recommendation of multiple websites or companies and MUST explicitly include the location context "{state}" or "{nation}".

    1. {Category.GENERAL.value}: A broad question asking for a list of the best options in the niche.
       (e.g., "What are the top-rated companies for {analysis.niche} in {state}?")
    2. {Category.INTENT.value}: A high-intent question from a user ready to hire or purchase, asking for the single best provider.
       (e.g., "Who is the absolute best provider for {first_service} in {nation}?")
    3. {Category.BRAND.value}: A question asking how "{analysis.brandName}" ranks against other top competitors in the area.
       (e.g., "How does {analysis.brandName} compare to other top-tier providers for {analysis.niche} in {state}?")
    4. {Category.COMPARISON.value}: A direct comparison question asking for a definitive choice between the brand and its competitors for a specific need.
       (e.g., "For {analysis.niche} services in {state}, should I choose {analysis.brandName} or are there better local alternatives?")

    Return exactly 4 questions as a valid JSON array ONLY (no markdown, no extra text) with objects containing:
    - category: string
    - text: string
    
    Response must be pure JSON only."""

    response = model.generate_content(
        prompt,
        generation_config=genai.GenerationConfig(
            temperature=0.7
        )
    )
    
    raw_questions = extract_json(response.text)
    questions = []
    for idx, q in enumerate(raw_questions):
        questions.append(Question(
            id=f"q-{idx}",
            category=q.get("category", "General / Discovery"),
            text=q.get("text", "")
        ))
    
    return questions


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
