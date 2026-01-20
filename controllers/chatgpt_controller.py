import asyncio
import os
import random
import json
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from models.prompt_questions import PromptQuestionsModel
from models.questionsCategory import QuestionsCategoryModel
from models.website_analysis import WebsiteAnalysisResponse
from global_db_opretions import find_one,update_one
from bson import ObjectId
import uuid
from typing import Optional
USER_DATA_DIR = os.path.join(os.getcwd(), "user_data")
COOKIES_FILE = os.path.join(os.getcwd(), "chatgpt_cookies.json")

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
]

def cookies_exist():
    return os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 10

async def save_cookies(context):
    cookies = await context.cookies()
    with open(COOKIES_FILE, "w") as f:
        json.dump(cookies, f)
    print(f"Cookies saved to {COOKIES_FILE}")

async def load_cookies(context):
    if cookies_exist():
        with open(COOKIES_FILE, "r") as f:
            cookies = json.load(f)
        await context.add_cookies(cookies)
        print(f"Cookies loaded from {COOKIES_FILE}")
        return True
    return False

async def human_delay(min_ms=500, max_ms=2000):
    await asyncio.sleep(random.randint(min_ms, max_ms) / 1000)

async def human_type(page, selector, text):
    element = await page.wait_for_selector(selector, timeout=60000)
    await element.click()
    await human_delay(200, 500)
    for char in text:
        await page.keyboard.type(char, delay=random.randint(30, 100))
        if random.random() < 0.1:
            await human_delay(100, 300)

async def wait_for_cloudflare(page, timeout=30000):
    print("Waiting for Cloudflare challenge to resolve...")
    start_time = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start_time) * 1000 < timeout:
        cf_selectors = [
            'iframe[src*="challenges.cloudflare.com"]', '#challenge-running',
            '#challenge-stage', '.cf-turnstile', '[data-testid="cf-turnstile"]',
            '#cf-challenge-running', '.cf-browser-verification',
        ]
        
        cf_found = False
        for selector in cf_selectors:
            try:
                if await page.query_selector(selector):
                    cf_found = True
                    break
            except:
                pass
        
        if not cf_found:
            try:
                await page.wait_for_selector("#prompt-textarea", timeout=1000)
                print("Cloudflare challenge passed!")
                return True
            except:
                pass
        
        await asyncio.sleep(1)
        await page.mouse.move(random.randint(100, 800), random.randint(100, 600))
    
    return False

async def handle_welcome_popup(page):
    try:
        stay_logged_out_button = page.get_by_role("link", name="Stay logged out")
        await stay_logged_out_button.wait_for(state="visible", timeout=5000)
        print("'Stay logged out' popup found. Clicking it.")
        await stay_logged_out_button.click()
        await human_delay(1000, 2000)
    except Exception:
        print("'Stay logged out' popup not found, continuing normally.")

async def run_chatgpt_session(question: str, headless: bool, is_retry: bool = False) -> str:
    context = None
    try:
        async with async_playwright() as p:
            user_agent = random.choice(USER_AGENTS)
            
            mode_text = "headless" if headless else "visible browser"
            print(f"Starting {mode_text} mode...")
            
            browser_args = [
                "--disable-blink-features=AutomationControlled", "--window-size=1920,1080",
                "--start-maximized", "--disable-dev-shm-usage", "--no-first-run",
                "--no-default-browser-check", "--disable-infobars",
                "--ignore-certificate-errors", "--lang=en-US",
            ]
            
            if headless:
                browser_args.append("--headless=new")
            
            context = await p.chromium.launch_persistent_context(
                USER_DATA_DIR,
                headless=headless,
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent,
                locale="en-US",
                timezone_id="America/New_York",
                geolocation={"latitude": 40.7128, "longitude": -74.0060},
                permissions=["geolocation"],
                color_scheme="light",
                args=browser_args,
                ignore_https_errors=True,
                java_script_enabled=True,
                bypass_csp=True,
            )

            page = context.pages[0] if context.pages else await context.new_page()
            
            await Stealth().apply_stealth_async(page)
            
            if headless:
                await load_cookies(context)
            
            await page.set_extra_http_headers({
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
                "sec-ch-ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"macOS"',
            })

            print("Opening ChatGPT...")
            await page.goto("https://chatgpt.com", wait_until="domcontentloaded")
            
            await human_delay(2000, 3000)
            
            cf_passed = await wait_for_cloudflare(page, timeout=30000)
            
            if not cf_passed and headless:
                print("Cloudflare challenge not resolved in headless mode!")
                await context.close()
                return "CAPTCHA_RETRY"
            
            await handle_welcome_popup(page)

            if not headless:
                print("Please solve any captcha/login manually in the browser window...")
                print("Waiting for input box (timeout: 120s)...")
            
            await human_delay(1000, 2000)
            await page.mouse.move(random.randint(100, 500), random.randint(100, 500))
            await human_delay(500, 1000)
            
            await page.wait_for_selector("#prompt-textarea", timeout=120000)
            await page.press("#prompt-textarea", "Enter")
            
            if not headless:
                await save_cookies(context)
                print("Cookies saved! Next requests will use headless mode.")
            
            await human_delay(1000, 2000)
            
            print(f"Typing question: {question[:50]}...")
            await human_type(page, "#prompt-textarea", question)
            
            await human_delay(500, 1000)
            
            try:
                await page.press("#prompt-textarea", "Enter")
            except Exception:
                submit_btn = await page.query_selector("button#composer-submit-button")
                if submit_btn:
                    await submit_btn.click()

            print("Waiting for response...")
            response_text = ""
            last_len = 0
            stable = 0
            max_wait = 120
            elapsed = 0

            while stable < 3 and elapsed < max_wait:
                await page.wait_for_timeout(2000)
                elapsed += 2
                responses = await page.query_selector_all('div[data-message-author-role="assistant"]')

                if responses:
                    response_text = await responses[-1].inner_text()
                    if len(response_text) == last_len and len(response_text) > 10:
                        stable += 1
                    else:
                        stable = 0
                        last_len = len(response_text)
                    print(f"...generating ({len(response_text)} chars)...")

            if not response_text:
                return "No response captured. ChatGPT may require login or selectors changed."

            await save_cookies(context)

            print("Response captured successfully!")
            return response_text.strip()

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return f"Error in ask_chatgpt: {str(e)}"

    finally:
        if context:
            try:
                await context.close()
            except:
                pass

SESSION_LOCK = asyncio.Lock()


import json
import re
from models.website_analysis import WebsiteAnalysis

async def analyze_website_chatgpt(domain: str, nation: str, state: str, query_context: str = "", company_id: str = "", project_id: str = ""):
    context_section = ""
    if query_context and query_context.strip():
        context_section = (
            f"The user has provided the following additional context about their website: --- "
            f"{query_context.strip()} --- Use this context to make your analysis more accurate."
        )

    prompt = (
        f'Analyze the website with domain "{domain}". The target audience is in {state}, {nation}. '
        f'{context_section} '
        'Identify its core brand name, market niche, main purpose, and key products/services. '
        'Based strictly on the website content and the given context, identify: '
        '- What the website is known or used for '
        '- The industry or area it operates in '
        '- Its primary purpose '
        '- The main services or offerings it provides. '
        'If the website is not well-known or has limited information, make a reasonable best-guess '
        'based on the domain name, URL structure, branding cues, and common industry patterns. '
        'Return the response as a valid JSON object ONLY (no markdown, no comments, no extra text) '
        'with these exact fields: brandName: string, niche: string, purpose: string, services: array of strings. '
        'The output must be pure JSON only.'
    )

    async with SESSION_LOCK:
        has_cookies = cookies_exist()
        if has_cookies:
            result = await run_chatgpt_session(prompt, headless=True)
        else:
            result = await run_chatgpt_session(prompt, headless=True)
        
        if result == "CAPTCHA_RETRY":
            result = await run_chatgpt_session(prompt, headless=True, is_retry=True)
    
    try:
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', result)
        if json_match:
            result = json_match.group(1).strip()
        
        if result.startswith('[') or result.startswith('{'):
            parsed = json.loads(result)
        else:
            json_pattern = r'[\[\{][\s\S]*[\]\}]'
            match = re.search(json_pattern, result)
            if match:
                parsed = json.loads(match.group())
            else:
                parsed = json.loads(result)
        clean_json_str = json.dumps(parsed, ensure_ascii=False)
        prompt_questions = PromptQuestionsModel(context=query_context,website_url=domain,nation=nation,state=state,company_id=company_id,project_id=project_id,chatgpt_website_analysis=clean_json_str)
        await prompt_questions.insert()
        return WebsiteAnalysisResponse(
    website_analysis=WebsiteAnalysis(**parsed),
    prompt_questions_id=str(prompt_questions.id)
)

    except Exception as e:
        print("Error", e)
        return WebsiteAnalysisResponse(
        website_analysis=WebsiteAnalysis(
            brandName=domain.split('.')[0].capitalize(),
            niche=domain,
            purpose=str(e),
            services=[domain]
        ),
        prompt_questions_id=""
    )


from models.website_analysis import Question


def extract_json(text: str):
    """Extract JSON from text that may contain markdown code blocks"""
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


async def generate_questions_chatgpt(analysis: WebsiteAnalysis, domain: str, nation: str, state: str, prompt_questions_id: str) -> list:
    """
    🔥 DYNAMIC AEO/GEO Question Generation using ChatGPT
    - Categories are generated dynamically based on website/business type
    - Questions are tailored for each category
    - Uses ChatGPT via Playwright automation
    """
    
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
        async with SESSION_LOCK:
            has_cookies = cookies_exist()
            if has_cookies:
                print("Cookies found! Generating questions in headless mode...")
                result = await run_chatgpt_session(prompt, headless=True)
            else:
                print("No cookies found. Starting in visible mode for initial setup/login...")
                result = await run_chatgpt_session(prompt, headless=True)
            
            if result == "CAPTCHA_RETRY":
                print("Cloudflare challenge failed. Retrying once...")
                result = await run_chatgpt_session(prompt, headless=True, is_retry=True)
        
        # Parse the response
        categories_data = extract_json(result)
        
        if not isinstance(categories_data, dict):
            print("Error: ChatGPT did not return a valid JSON object.")
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
                    "category_id": ObjectId(),
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


async def ask_chatgpt_with_location(question: str, nation: str, state: str) -> str:
    """
    Ask ChatGPT with location context (replacement for ask_gemini)
    """
    full_prompt = f"""{question} 
    Please recommend specific websites that best address this query for a user specifically in {state}, {nation}. 
    Ensure the recommendations are highly relevant to this geographical location."""
    
    async with SESSION_LOCK:
        has_cookies = cookies_exist()
        if has_cookies:
            result = await run_chatgpt_session(full_prompt, headless=True)
        else:
            result = await run_chatgpt_session(full_prompt, headless=True)
        
        if result == "CAPTCHA_RETRY":
            result = await run_chatgpt_session(full_prompt, headless=True, is_retry=True)
    
    return result if result else "No response from ChatGPT."


async def ask_chatgpt(question: str,prompt_questions_id: str,category_id: str,qna_uuid: Optional[str]=None) -> str:
    async with SESSION_LOCK:
        has_cookies = cookies_exist()
        
        if has_cookies:
            print("Cookies found! Starting headless mode...")
            # Set headless to True if cookies exist
            result = await run_chatgpt_session(question, headless=True)
        else:
            print("No cookies found. Starting in visible mode for initial setup/login...")
            # Set headless to False if no cookies exist
            result = await run_chatgpt_session(question, headless=True)
        
        if result == "CAPTCHA_RETRY":
            print("Cloudflare challenge failed. Retrying once in visible mode...")
            result = await run_chatgpt_session(question, headless=True, is_retry=True)
        if qna_uuid:
            await update_one(
    PromptQuestionsModel,
    {"_id": ObjectId(prompt_questions_id)},
    {
        "$set": {
            "qna.$[item].answer": result,
            "qna.$[item].question": question
        }
    },
    array_filters=[
        {"item.uuid": qna_uuid}
    ]
)   
        else:
            await update_one(
    PromptQuestionsModel,
    {"_id": ObjectId(prompt_questions_id)},
    {
        "$push": {
            "qna": {
                "question": question,
                "answer": result,
                "category_id": ObjectId(category_id),
                "uuid": str(uuid.uuid4())
            }
        }
    }
)



        return result
