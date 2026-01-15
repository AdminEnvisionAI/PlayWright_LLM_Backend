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
    # 1. Fetch all available question categories from the database.
    categories = await QuestionsCategoryModel.find_all().to_list()
    print("categories--->", categories)
    
    if not categories:
        print("No question categories found in the database. Returning empty list.")
        return []

    # --- SOLUCIÓN: Crear un mapa de búsqueda para acceder a las categorías por su nombre ---
    # Esto nos permitirá encontrar el ID correcto fácilmente después de la respuesta de la IA.
    category_map = {category.name: category for category in categories}

    model = genai.GenerativeModel("gemini-2.5-flash")
    
    # --- Dynamic Prompt Construction ---
    first_service = analysis.services[0] if analysis.services else analysis.niche
    
    category_instructions = []
    for i, category in enumerate(categories):
        formatted_instruction = category.prompt_instruction.format(
            brandName=analysis.brandName,
            niche=analysis.niche,
            first_service=first_service,
            state=state,
            nation=nation
        )
        instruction_line = f"{i + 1}. {category.name}: {formatted_instruction}"
        category_instructions.append(instruction_line)
        
    category_instructions_str = "\n".join(category_instructions)
    num_questions = len(categories)

    prompt = f"""Based on this website analysis for {domain}:
Brand Name: {analysis.brandName}
Niche: {analysis.niche}
Purpose: {analysis.purpose}
Services: {", ".join(analysis.services)}
Location Context: {state}, {nation}

Your goal is to generate questions that seek direct recommendations, lists of top providers, or ask who the "best" is. Avoid questions that only ask for general information.

Generate exactly {num_questions} question(s), one for each of the following categories.
IMPORTANT: Each question must naturally invite a recommendation of multiple websites or companies and MUST explicitly include the location context "{state}" or "{nation}".

{category_instructions_str}

Return exactly {num_questions} questions as a valid JSON array ONLY (no markdown, no extra text) with objects containing:
- category: string (use the exact category name from the list above)
- text: string

Response must be pure JSON only."""

    try:
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.7,
                response_mime_type="application/json"
            )
        )
        
        raw_questions = extract_json(response.text)
        
        if not isinstance(raw_questions, list):
            print("Error: AI did not return a valid JSON array.")
            return []

        questions = []
        qna_list = [] # Mover la creación de qna_list aquí para construirla al mismo tiempo

        for q_data in raw_questions:
            category_name = q_data.get("category")
            question_text = q_data.get("text")

            # --- SOLUCIÓN: Usar el mapa para encontrar la categoría correcta ---
            matching_category = category_map.get(category_name)

            if matching_category and question_text:
                # Si encontramos una categoría que coincide, usamos su ID
                correct_category_id = str(matching_category.id)
                
                # Creamos el objeto Question con el ID correcto
                questions.append(Question(
                    id=correct_category_id,
                    category=category_name,
                    text=question_text,
                    category_name=category_name
                ))
                
                # Creamos la entrada qna con el ID correcto
                qna_list.append({
                    "question": question_text,
                    "answer": "Not available yet",
                    "category_id": ObjectId(correct_category_id), # Usar el ID correcto aquí
                    "category_name": category_name,
                    "uuid": str(uuid.uuid4())
                })
            else:
                print(f"Warning: AI returned an unknown category ('{category_name}') or empty text. Skipping.")

        print("questions", questions)
        print("prompt_questions_id", prompt_questions_id)

        # Si se generó alguna pregunta, actualizamos la base de datos
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
