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
    """
    🚀 FAST typing - uses keyboard.type with minimal delay (1ms)
    Much faster than character-by-character but still triggers ChatGPT events
    """
    element = await page.wait_for_selector(selector, timeout=60000)
    await element.click()
    await human_delay(100, 200)
    # Type entire text at once with minimal delay (1ms per char = ~1 second for 1000 chars)
    await page.keyboard.type(text, delay=1)
    await human_delay(100, 200)

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
        print("result--->",result)
        # --- START: ROBUST JSON EXTRACTION ---
        # Strategy 1: Find JSON within markdown code blocks first
        json_match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', result)
        if json_match:
            json_str = json_match.group(1).strip()
            print("Extracted JSON from markdown block.")
        else:
            # Strategy 2: Find the first '{' and its matching '}'
            start_index = result.find('{')
            if start_index == -1:
                raise json.JSONDecodeError("No JSON object found in the response.", result, 0)
            
            end_index = -1
            open_braces = 0
            for i in range(start_index, len(result)):
                if result[i] == '{':
                    open_braces += 1
                elif result[i] == '}':
                    open_braces -= 1
                    if open_braces == 0:
                        end_index = i + 1
                        break
            
            if end_index == -1:
                raise json.JSONDecodeError("Could not find matching closing brace for JSON object.", result, 0)

            json_str = result[start_index:end_index]
            print(f"Extracted JSON from raw text (indices {start_index}-{end_index}).")
        # --- END: ROBUST JSON EXTRACTION ---
        parsed = json.loads(json_str)
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
    """Extract JSON from text that may contain markdown code blocks or extra text"""
    if not text or not text.strip():
        print(f"⚠️ extract_json received empty text")
        raise ValueError("Empty text provided to extract_json")
    
    original_text = text
    text = text.strip()
    
    # Debug: Show first 200 chars of response
    print(f"📝 Parsing response ({len(text)} chars): {text[:200]}...")
    
    # Strategy 1: Check for markdown code blocks
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if json_match:
        text = json_match.group(1).strip()
        print(f"📝 Found markdown code block, extracted: {text[:100]}...")
    
    # Strategy 2: Direct JSON parse if starts with [ or {
    if text.startswith('[') or text.startswith('{'):
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"⚠️ Direct JSON parse failed: {e}")
    
    # Strategy 3: Find JSON array pattern
    array_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', text)
    if array_match:
        try:
            return json.loads(array_match.group())
        except json.JSONDecodeError as e:
            print(f"⚠️ Array pattern parse failed: {e}")
    
    # Strategy 4: Find any JSON object or array
    json_pattern = r'[\[\{][\s\S]*[\]\}]'
    match = re.search(json_pattern, text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError as e:
            print(f"⚠️ Generic JSON pattern parse failed: {e}")
    
    # Strategy 5: Try to find individual JSON objects and build array
    objects = re.findall(r'\{[^{}]*\}', text)
    if objects:
        try:
            parsed_objects = [json.loads(obj) for obj in objects]
            print(f"📝 Built array from {len(parsed_objects)} individual objects")
            return parsed_objects
        except json.JSONDecodeError as e:
            print(f"⚠️ Individual objects parse failed: {e}")
    
    # Last resort: try the whole text
    print(f"⚠️ All JSON extraction strategies failed, trying raw text...")
    return json.loads(text)




# ===============================
# GLOBAL INSTRUCTIONS
# ===============================

BASE_INSTRUCTION = """
RESPOND WITH ONLY A VALID JSON OBJECT.
NO EXPLANATIONS. NO MARKDOWN. NO INTRODUCTORY TEXT.
START YOUR RESPONSE WITH { AND END WITH }.
"""


# ===============================
# PROMPT BUILDERS
# ===============================

def discovery_prompt(analysis, state, nation):
    print("Analysisdiscovery:", analysis, "state:", state, "nation:", nation)
    return f"""{BASE_INSTRUCTION}

Generate ONLY high-intent "Discovery" category questions optimized for AEO (Answer Engine Optimization) 
and GEO (Generative Engine Optimization).

These questions must:
- Be brand-agnostic (DO NOT mention any brand, product, or company name)
- Be recommendation and discovery focused (LLMs should naturally suggest platforms in answers)
- Target decision-makers evaluating AI platforms
- Reflect real-world buyer search and LLM query behavior

Constraints:
- Generate exactly 5 to 6 questions
- Questions must be location-specific and intent-driven
- Avoid generic definitions or informational questions
- Focus on platform-level discovery, not features in isolation

Context:
- Niche: {analysis.niche}
- Services: {", ".join(analysis.services)}
- Target Location: {state}, {nation}

Return JSON ONLY in the following format:
{{
  "Discovery": [
    "question 1",
    "question 2",
    "question 3",
    "question 4",
    "question 5"
  ]
}}

"""


def brand_prompt(analysis,state, nation):
    print("Analysisbrand:", analysis)
    return f"""{BASE_INSTRUCTION}

Generate ONLY high-intent "Brand" category questions optimized for
AEO (Answer Engine Optimization) and GEO (Generative Engine Optimization).

These questions must:
- Explicitly include the brand name "{analysis.brandName}"
- Reflect real user and buyer intent (not marketing slogans)
- Be suitable for LLM-based discovery, comparison, and evaluation
- Focus on platform-level value, trust, and use cases

Constraints:
- Generate exactly 5 to 6 questions
- Avoid generic or purely informational questions
- Keep wording natural, as real users would ask

Context:
- Niche: {analysis.niche}
- Services: {", ".join(analysis.services)}
- Target Location: {state}, {nation}

Return JSON ONLY in the following format:
{{
  "Brand": [
    "question 1",
    "question 2",
    "question 3",
    "question 4",
    "question 5"
  ]
}}
"""



def trust_prompt(analysis,state, nation):
    print("Analysistrust:", analysis)
    return f"""{BASE_INSTRUCTION}

Generate ONLY high-intent "Trust" category questions optimized for
AEO (Answer Engine Optimization) and GEO (Generative Engine Optimization).

These questions must:
- Explicitly include the brand name "{analysis.brandName}"
- Focus on trust signals such as reliability, security, credibility, and adoption
- Reflect real buyer concerns before choosing an AI platform
- Be suitable for LLM-based evaluation and recommendation contexts

Constraints:
- Generate exactly 4 to 5 questions
- Avoid marketing language or exaggerated claims
- Keep wording natural and unbiased, as real users would ask

Context:
- Niche: {analysis.niche}
- Services: {", ".join(analysis.services)}
- Target Location: {state}, {nation}

Return JSON ONLY in the following format:
{{
  "Trust": [
    "question 1",
    "question 2",
    "question 3",
    "question 4"
  ]
}}
"""



def comparison_prompt(analysis, state,nation):
    print("Analysiscomparison:", analysis, "State:", state)
    return f"""{BASE_INSTRUCTION}

Generate ONLY high-intent "Comparison" category questions optimized for
AEO (Answer Engine Optimization) and GEO (Generative Engine Optimization).

These questions must:
- Explicitly include the brand name "{analysis.brandName}"
- Compare the brand against alternatives, competitors, or traditional solutions
- Reflect real buyer evaluation behavior (pros, cons, suitability, trade-offs)
- Be phrased naturally, as users would ask LLMs during decision-making

Constraints:
- Generate exactly 4 to 5 questions
- Avoid naming specific competitor brands unless necessary
- Avoid promotional or biased language

Context:
- Niche: {analysis.niche}
- Services: {", ".join(analysis.services)}
- Target Location: {state}, {nation}

Return JSON ONLY in the following format:
{{
  "Comparison": [
    "question 1",
    "question 2",
    "question 3",
    "question 4"
  ]
}}
"""



# ===============================
# SINGLE PROMPT RUNNER
# ===============================

async def run_single_prompt(prompt):
    async with SESSION_LOCK:
        result = await run_chatgpt_session(
            prompt,
            headless=True
        )

        if result == "CAPTCHA_RETRY":
            result = await run_chatgpt_session(
                prompt,
                headless=True,
                is_retry=True
            )

    return extract_json(result)


# ===============================
# MAIN CATEGORY GENERATOR
# ===============================

async def generate_all_categories(analysis, state, nation):
    categories_data = {}

    prompts = [
        discovery_prompt(analysis, state, nation),
        brand_prompt(analysis,state, nation),
        trust_prompt(analysis,state, nation),
        comparison_prompt(analysis, state,nation)
    ]

    print("Prompts:", prompts)

    for prompt in prompts:
        parsed = await run_single_prompt(prompt)

        if isinstance(parsed, dict):
            categories_data.update(parsed)
        else:
            print("⚠️ Invalid JSON received, category skipped")

    return categories_data


# ===============================
# USAGE
# ===============================

# categories = await generate_all_categories(analysis, state, nation)
# print(categories)



async def generate_questions_chatgpt(
    analysis: WebsiteAnalysis,
    domain: str,
    nation: str,
    state: str,
    prompt_questions_id: str
) -> list:
    """
    🔥 DYNAMIC AEO/GEO Question Generation using ChatGPT
    - Generates Discovery, Brand, Trust, Comparison categories
    - One prompt at a time
    - Merges all categories
    """

    try:
        # 🔹 Generate all categories (already parsed JSON)
        categories_data = await generate_all_categories(analysis, state, nation)

        if not isinstance(categories_data, dict):
            print("❌ Invalid categories data")
            return []

        print(f"🔥 Generated {len(categories_data)} categories: {list(categories_data.keys())}")

        questions = []
        qna_list = []

        for category_name, category_questions in categories_data.items():
            if not isinstance(category_questions, list):
                continue

            for question_text in category_questions:
                if not question_text or not isinstance(question_text, str):
                    continue

                uuid_id = str(uuid.uuid4())
                category_object_id = ObjectId()

                # 🔹 Frontend Question Object
                questions.append(
                    Question(
                        id=uuid_id,
                        uuid=uuid_id,
                        text=question_text,
                        category=category_name,
                        category_name=category_name,
                        category_id=str(category_object_id)
                    )
                )

                # 🔹 DB QnA Object
                qna_list.append({
                    "question": question_text,
                    "answer": "Not available yet",
                    "category_id": category_object_id,
                    "category_name": category_name,
                    "uuid": uuid_id
                })

        print(f"✅ Generated {len(questions)} total questions")

        # 🔹 Save to DB
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
        print(f"❌ Error during question generation: {e}")
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


async def discover_competitors_chatgpt(brand_name: str, niche: str, nation: str, state: str) -> list:
    """
    🔥 Discover competitors for a brand using ChatGPT
    Same logic as Gemini competitor discovery but using ChatGPT
    """
    prompt = f"""RESPOND WITH ONLY JSON. NO EXPLANATIONS. NO MARKDOWN.

List the top 5 direct competitors of "{brand_name}" in the {niche} space in {nation}.

OUTPUT ONLY A JSON ARRAY OF 5 COMPETITOR NAMES. START WITH [ AND END WITH ]. NOTHING ELSE.
Example: ["Name1", "Name2", "Name3", "Name4", "Name5"]"""
    
    try:
        async with SESSION_LOCK:
            result = await run_chatgpt_session(prompt, headless=True)
            
            if result == "CAPTCHA_RETRY":
                result = await run_chatgpt_session(prompt, headless=True, is_retry=True)
        
        # Parse JSON response - handle ChatGPT's verbose responses
        if not result or result.startswith("Error") or result.startswith("No response"):
            print(f"⚠️ ChatGPT returned no valid response for competitors")
            return []
        
        competitors = extract_json(result)
        if not isinstance(competitors, list):
            print(f"⚠️ ChatGPT competitor discovery did not return a list")
            return []
        
        # Clean competitor names
        competitors = [c.strip() for c in competitors if isinstance(c, str) and c.strip()][:5]
        print(f"🔍 ChatGPT discovered competitors: {competitors}")
        return competitors
        
    except Exception as e:
        print(f"❌ ChatGPT competitor discovery failed: {e}")
        return []


# async def tag_all_qna_chatgpt(qna_list: list, brand_name: str, competitors: list) -> list:
#     """
#     🔥 BATCH TAG all Q&A with semantic flags using ChatGPT in ONE request
#     Super fast - processes all Q&A in a single browser session
#     Returns updated qna_list with llm_flags
#     """
#     competitors_str = ", ".join(competitors) if competitors else "None specified"
    
#     # Separate already tagged and need-to-tag
#     already_tagged = []
#     to_tag = []
#     to_tag_indices = []
    
#     for idx, qna in enumerate(qna_list):
#         qna_dict = qna.dict() if hasattr(qna, 'dict') else dict(qna)
        
#         if qna_dict.get("llm_flags"):
#             already_tagged.append((idx, qna_dict))
#             continue
        
#         question = qna_dict.get("question", "")
#         answer = qna_dict.get("answer", "")
        
#         if not answer or answer == "Not available yet":
#             already_tagged.append((idx, qna_dict))
#             continue
        
#         to_tag.append(qna_dict)
#         to_tag_indices.append(idx)
    
#     if not to_tag:
#         print("✅ All Q&A already tagged, skipping ChatGPT call")
#         return [qna_list[i].dict() if hasattr(qna_list[i], 'dict') else dict(qna_list[i]) for i in range(len(qna_list))]
    
#     print(f"🚀 BATCH tagging {len(to_tag)} Q&A items in ONE ChatGPT request...")
    
#     # Build batch prompt with all Q&As
#     qna_items_text = ""
#     for i, qna_dict in enumerate(to_tag):
#         question = qna_dict.get("question", "")
#         answer = qna_dict.get("answer", "")
#         # Truncate very long answers to avoid token limits
#         if len(answer) > 7000:
#             answer = answer[:7000] + "..."
#         qna_items_text += f"""
# --- ITEM {i} ---
# Question: {question}
# Answer: {answer}
# """
    
#     prompt = f"""RESPOND WITH ONLY JSON. NO EXPLANATIONS. NO MARKDOWN. JUST A RAW JSON ARRAY.

# Analyze these {len(to_tag)} Q&A items for brand "{brand_name}":

# {qna_items_text}

# For each item, return an object with:
# - brand_in_question: boolean
# - brand_mentioned: boolean  
# - brand_rank: number or null
# - is_recommended: boolean
# - sentiment: "positive" or "neutral_positive" or "neutral" or "negative"
# - citation_type: "first_party" or "third_party" or "none"
# - citation_expected: boolean
# - features_mentioned: string array
# - competitors_mentioned: string array
# - other_brands_recommended: string array (ALL other brand/company/business names mentioned or recommended in the answer, excluding "{brand_name}")

# OUTPUT EXACTLY {len(to_tag)} JSON OBJECTS IN AN ARRAY. START YOUR RESPONSE WITH [ AND END WITH ]. NOTHING ELSE."""

#     try:
#         async with SESSION_LOCK:
#             result = await run_chatgpt_session(prompt, headless=True)
            
#             if result == "CAPTCHA_RETRY":
#                 result = await run_chatgpt_session(prompt, headless=True, is_retry=True)
        
#         if not result or result.startswith("Error") or result.startswith("No response"):
#             print(f"⚠️ ChatGPT returned no valid response for batch tagging")
#             # Return original list without tags
#             return [qna_list[i].dict() if hasattr(qna_list[i], 'dict') else dict(qna_list[i]) for i in range(len(qna_list))]
        
#         # Parse the batch response
#         tags_array = extract_json(result)
        
#         if not isinstance(tags_array, list):
#             print(f"⚠️ ChatGPT batch tagging did not return an array, got: {type(tags_array)}")
#             return [qna_list[i].dict() if hasattr(qna_list[i], 'dict') else dict(qna_list[i]) for i in range(len(qna_list))]
        
#         print(f"✅ Received {len(tags_array)} tags from ChatGPT")
        
#         # Apply tags to the Q&A items
#         for i, qna_dict in enumerate(to_tag):
#             if i < len(tags_array):
#                 flags_data = tags_array[i]
#                 if isinstance(flags_data, dict):
#                     llm_flags = {
#                         "brand_in_question": bool(flags_data.get("brand_in_question", False)),
#                         "brand_mentioned": bool(flags_data.get("brand_mentioned", False)),
#                         "brand_rank": flags_data.get("brand_rank"),
#                         "is_recommended": bool(flags_data.get("is_recommended", False)),
#                         "sentiment": flags_data.get("sentiment", "neutral"),
#                         "citation_type": flags_data.get("citation_type", "none"),
#                         "citation_expected": bool(flags_data.get("citation_expected", False)),
#                         "features_mentioned": flags_data.get("features_mentioned", []),
#                         "competitors_mentioned": flags_data.get("competitors_mentioned", []),
#                         "other_brands_recommended": flags_data.get("other_brands_recommended", [])
#                     }
#                     qna_dict["llm_flags"] = llm_flags
#                     print(f"✅ Tagged Q&A {i+1}/{len(to_tag)}: brand_mentioned={llm_flags['brand_mentioned']}")
        
#         # Rebuild the full list in original order
#         updated_qna = [None] * len(qna_list)
        
#         # Place already tagged items
#         for idx, qna_dict in already_tagged:
#             updated_qna[idx] = qna_dict
        
#         # Place newly tagged items
#         for i, idx in enumerate(to_tag_indices):
#             updated_qna[idx] = to_tag[i]
        
#         print(f"🎉 BATCH tagging complete! Tagged {len(to_tag)} items in ONE request")
#         return updated_qna
        
#     except Exception as e:
#         import traceback
#         print(f"❌ ChatGPT batch tagging failed: {e}")
#         traceback.print_exc()
#         # Return original list without tags
#         return [qna_list[i].dict() if hasattr(qna_list[i], 'dict') else dict(qna_list[i]) for i in range(len(qna_list))]

















BATCH_SIZE = 5

async def tag_all_qna_chatgpt(qna_list: list, brand_name: str) -> list:
    """
    ✅ OPTIMIZED to tag Q&A in reliable, small batches.
    Processes Q&A in chunks to avoid token limits and improve accuracy.
    Returns updated qna_list with llm_flags.
    """
    
    # We no longer need a pre-defined list of competitors
    # competitors_str = ", ".join(competitors) if competitors else "None specified"

    items_to_tag = []
    original_indices_map = {} # To map temp index to original index

    # First, filter out items that need tagging
    for idx, qna in enumerate(qna_list):
        qna_dict = qna.dict() if hasattr(qna, 'dict') else dict(qna)
        answer = qna_dict.get("answer", "")
        
        # Skip if already tagged or no answer is present
        if qna_dict.get("llm_flags") or not answer or answer == "Not available yet":
            continue
        
        # Store the item and its original index
        original_indices_map[len(items_to_tag)] = idx
        items_to_tag.append(qna_dict)

    if not items_to_tag:
        print("✅ All Q&A already tagged or have no answer, skipping ChatGPT call.")
        return [q.dict() if hasattr(q, 'dict') else dict(q) for q in qna_list]

    print(f"🚀 Starting optimized tagging for {len(items_to_tag)} Q&A items in batches of {BATCH_SIZE}...")
    
    # Create batches from the items that need tagging
    batches = [items_to_tag[i:i + BATCH_SIZE] for i in range(0, len(items_to_tag), BATCH_SIZE)]
    
    # This will be our final list, we'll populate it as batches complete
    updated_qna_list = [q.dict() if hasattr(q, 'dict') else dict(q) for q in qna_list]

    for batch_num, batch in enumerate(batches):
        print(f"--- Processing Batch {batch_num + 1}/{len(batches)} ---")
        
        qna_items_text = ""
        for i, qna_dict in enumerate(batch):
            question = qna_dict.get("question", "")
            answer = qna_dict.get("answer", "")
            # Truncate long answers
            if len(answer) > 7000:
                answer = answer[:7000] + "..."
            qna_items_text += f"""
--- ITEM {i} ---
Question: {question}
Answer: {answer}
"""
        
        # The prompt is updated to find competitors organically
        prompt = f"""You are a precise JSON data extraction engine. RESPOND WITH ONLY JSON. NO EXPLANATIONS. NO MARKDOWN. JUST A RAW JSON ARRAY.

Analyze these {len(batch)} Q&A items for the brand "{brand_name}":

{qna_items_text}

For each item, return a JSON object with these exact fields:
- "brand_in_question": boolean (is "{brand_name}" mentioned in the Question?)
- "brand_mentioned": boolean (is "{brand_name}" mentioned in the Answer?)
- "brand_rank": number or null (1 if first, 2 if second, etc., null if not mentioned)
- "is_recommended": boolean (is "{brand_name}" positively recommended in the Answer?)
- "sentiment": string ("positive", "neutral", or "negative" sentiment towards "{brand_name}")
- "citation_type": string ("first_party" if the official brand URL is cited, "third_party", or "none")
- "citation_expected": boolean (true if the question implies a specific brand answer is needed)
- "features_mentioned": string array (list specific features mentioned for "{brand_name}")
- "competitors_mentioned": string array (EXTRACT and list any competitor brands mentioned in the Answer. Do NOT include "{brand_name}".)
- "other_brands_recommended": string array (any other business/product names mentioned in the answer, excluding "{brand_name}")

OUTPUT EXACTLY {len(batch)} JSON OBJECTS IN AN ARRAY. START WITH [ AND END WITH ]. NOTHING ELSE."""

        try:
            async with SESSION_LOCK:
                result = await run_chatgpt_session(prompt, headless=True)
                if result == "CAPTCHA_RETRY":
                    print("...CAPTCHA detected, retrying batch...")
                    result = await run_chatgpt_session(prompt, headless=True, is_retry=True)
            
            if not result or result.startswith("Error") or result.startswith("No response"):
                print(f"⚠️ Batch {batch_num + 1} failed: ChatGPT returned no valid response.")
                continue # Skip to the next batch

            tags_array = extract_json(result)
            
            if not isinstance(tags_array, list) or len(tags_array) != len(batch):
                print(f"⚠️ Batch {batch_num + 1} failed: Expected {len(batch)} tags, but received {len(tags_array)}. Skipping.")
                continue

            print(f"✅ Batch {batch_num + 1} successful. Received {len(tags_array)} tags.")
            
            # Apply the tags to the original list
            for i, flags_data in enumerate(tags_array):
                if isinstance(flags_data, dict):
                    # Find the original index of this item
                    temp_index_in_items_to_tag = (batch_num * BATCH_SIZE) + i
                    original_list_idx = original_indices_map[temp_index_in_items_to_tag]
                    
                    # Create the llm_flags object
                    llm_flags = {
                        "brand_in_question": bool(flags_data.get("brand_in_question", False)),
                        "brand_mentioned": bool(flags_data.get("brand_mentioned", False)),
                        "brand_rank": flags_data.get("brand_rank"),
                        "is_recommended": bool(flags_data.get("is_recommended", False)),
                        "sentiment": flags_data.get("sentiment", "neutral"),
                        "citation_type": flags_data.get("citation_type", "none"),
                        "citation_expected": bool(flags_data.get("citation_expected", False)),
                        "features_mentioned": flags_data.get("features_mentioned", []),
                        "competitors_mentioned": flags_data.get("competitors_mentioned", []),
                        "other_brands_recommended": flags_data.get("other_brands_recommended", [])
                    }
                    
                    # Update the correct item in our final list
                    updated_qna_list[original_list_idx]["llm_flags"] = llm_flags

        except Exception as e:
            import traceback
            print(f"❌ An error occurred while processing Batch {batch_num + 1}: {e}")
            traceback.print_exc()
            continue # Move to the next batch on error

    print(f"🎉 Tagging complete! Processed {len(items_to_tag)} items.")
    return updated_qna_list