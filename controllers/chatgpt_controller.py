import asyncio
import os
import random
import json
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

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

async def analyze_website_chatgpt(domain: str, nation: str, state: str, query_context: str = ""):
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
        
        return WebsiteAnalysis(**parsed)
    except Exception:
        return WebsiteAnalysis(
            brandName=domain.split('.')[0].capitalize(),
            niche="Unknown",
            purpose="Unknown",
            services=["Unknown"]
        )


async def ask_chatgpt(question: str) -> str:
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
        
        return result
