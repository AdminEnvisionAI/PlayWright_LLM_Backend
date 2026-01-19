from fastapi import HTTPException
from models.questionsCategory import QuestionsCategoryModel
from models.prompt_questions import PromptQuestionsModel, LLMFlags
from models.geo_metrics import GeoMetricsModel, BrandAgnosticMetrics, BrandIncludedMetrics  # 🆕
from fastapi import Request
from bson import ObjectId
from global_db_opretions import find_one, update_one
import google.generativeai as genai
import os
import json
import re
import asyncio  # 🆕 For rate limiting delays
from datetime import datetime,timedelta



# 🆕 API Key Manager for rotation
class GeminiKeyManager:
    """
    Manages multiple Gemini API keys with automatic rotation on rate limit/errors.
    Keys: GOOGLE_API_KEY, GOOGLE_API_KEY_2, ..., GOOGLE_API_KEY_7
    """
    def __init__(self):
        self.keys = []
        self.current_index = 0
        self._load_keys()
        
    def _load_keys(self):
        """Load all available API keys from environment"""
        # First key (GOOGLE_API_KEY)
        key1 = os.getenv("GOOGLE_API_KEY") or os.getenv("API_KEY", "")
        if key1:
            self.keys.append(("GOOGLE_API_KEY", key1))
        
        # Additional keys (GOOGLE_API_KEY_2 through GOOGLE_API_KEY_7)
        for i in range(2, 8):
            key = os.getenv(f"GOOGLE_API_KEY_{i}", "")
            if key:
                self.keys.append((f"GOOGLE_API_KEY_{i}", key))
        
        print(f"🔑 Loaded {len(self.keys)} Gemini API keys")
        
        # Configure with first key
        if self.keys:
            genai.configure(api_key=self.keys[0][1])
            print(f"🔑 Active key: {self.keys[0][0]}")
    
    def get_current_key_name(self):
        """Get current active key name"""
        if self.keys:
            return self.keys[self.current_index][0]
        return None
    
    def switch_to_next_key(self):
        """Switch to next available key. Returns True if switched, False if no more keys."""
        if not self.keys:
            return False
        
        next_index = self.current_index + 1
        if next_index >= len(self.keys):
            print(f"⚠️ All {len(self.keys)} API keys exhausted!")
            return False
        
        self.current_index = next_index
        key_name, key_value = self.keys[self.current_index]
        genai.configure(api_key=key_value)
        print(f"🔄 Switched to key: {key_name} (key {self.current_index + 1}/{len(self.keys)})")
        return True
    
    def reset_to_first_key(self):
        """Reset to first key (useful for new requests)"""
        if self.keys:
            self.current_index = 0
            genai.configure(api_key=self.keys[0][1])
            print(f"🔑 Reset to first key: {self.keys[0][0]}")
    
    def is_rate_limit_error(self, error):
        """Check if error is a rate limit (429) error"""
        error_str = str(error).lower()
        return "429" in error_str or "quota" in error_str or "rate" in error_str
    
    def has_more_keys(self):
        """Check if there are more keys available"""
        return self.current_index < len(self.keys) - 1
    
    def get_model(self, model_name="gemini-3-flash-preview"):
        """Get a GenerativeModel with current key"""
        return genai.GenerativeModel(model_name)


# Initialize global key manager
key_manager = GeminiKeyManager()

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


def extract_json_from_text(text: str):
    """Extract JSON from LLM response text."""
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


async def tag_qna_with_llm_controller(request: Request):
    """
    ONE-TIME LLM semantic tagging for each Q&A.
    Stores llm_flags in DB for fast metrics calculation.
    
    Request body:
        - prompt_question_id: str (required)
        - brand_name: str (required)
        - competitors: list[str] (optional)
        - force_retag: bool (optional - retag even if already tagged)
    """
    try:
        body = await request.json()
        prompt_question_id = body.get("prompt_question_id")
        brand_name = body.get("brand_name", "").strip()
        competitors = body.get("competitors", [])
        force_retag = body.get("force_retag", False)
        
        if not prompt_question_id:
            raise HTTPException(status_code=400, detail="prompt_question_id is required")
        if not brand_name:
            raise HTTPException(status_code=400, detail="brand_name is required")
        
        # Fetch document
        doc = await find_one(PromptQuestionsModel, {"_id": ObjectId(prompt_question_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="Prompt questions document not found")
        
        qna_list = doc.qna or []
        if not qna_list:
            return {"message": "No Q&A data found", "tagged_count": 0}
        
        model = genai.GenerativeModel("gemini-3-flash-preview")
        competitors_str = ", ".join(competitors) if competitors else "None specified"
        
        tagged_count = 0
        updated_qna = []
        
        for idx, qna in enumerate(qna_list):
            qna_dict = qna.dict() if hasattr(qna, 'dict') else dict(qna)
            
            # Skip if already tagged (unless force_retag)
            if qna_dict.get("llm_flags") and not force_retag:
                updated_qna.append(qna_dict)
                continue
            
            question = qna_dict.get("question", "")
            answer = qna_dict.get("answer", "")
            
            if not answer or answer == "Not available yet":
                updated_qna.append(qna_dict)
                continue
            
            # LLM Prompt for semantic tagging
            prompt = f"""You are a GEO (Generative Engine Optimization) analyzer.

Given:
Brand: {brand_name}
Competitors: {competitors_str}

Question:
{question}

Answer:
{answer}

Analyze and return STRICT JSON with these fields ONLY:
- brand_mentioned: boolean (is {brand_name} mentioned in the answer?)
- brand_rank: number or null (position where {brand_name} appears: 1=first, 2=second, etc. null if not mentioned)
- is_recommended: boolean (is {brand_name} positively recommended?)
- sentiment: string (positive/neutral/negative - sentiment towards {brand_name})
- citation_type: string (first_party/third_party/none - does answer cite {brand_name}'s official source?)
- features_mentioned: array of strings (features/qualities mentioned for {brand_name})
- competitors_mentioned: array of strings (which competitors from the list are mentioned?)

Return ONLY valid JSON, no explanations."""

            try:
                response = await model.generate_content_async(
                    prompt,
                    generation_config=genai.GenerationConfig(
                        temperature=0.2,
                        response_mime_type="application/json"
                    )
                )
                
                flags_data = extract_json_from_text(response.text)
                
                # Validate and create LLMFlags
                llm_flags = {
                    "brand_mentioned": bool(flags_data.get("brand_mentioned", False)),
                    "brand_rank": flags_data.get("brand_rank"),
                    "is_recommended": bool(flags_data.get("is_recommended", False)),
                    "sentiment": flags_data.get("sentiment", "neutral"),
                    "citation_type": flags_data.get("citation_type", "none"),
                    "features_mentioned": flags_data.get("features_mentioned", []),
                    "competitors_mentioned": flags_data.get("competitors_mentioned", [])
                }
                
                qna_dict["llm_flags"] = llm_flags
                tagged_count += 1
                print(f"Tagged Q&A {idx + 1}/{len(qna_list)}: brand_mentioned={llm_flags['brand_mentioned']}")
                
            except Exception as e:
                print(f"LLM tagging failed for Q&A {idx + 1}: {e}")
                # Keep qna without flags on error
            
            updated_qna.append(qna_dict)
        
        # Update document with tagged qna
        await update_one(
            PromptQuestionsModel,
            {"_id": ObjectId(prompt_question_id)},
            {"$set": {"qna": updated_qna}}
        )
        
        return {
            "message": "LLM tagging completed",
            "total_qna": len(qna_list),
            "tagged_count": tagged_count,
            "brand_name": brand_name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


async def calculate_geo_metrics_controller(request: Request):
    """
    Calculate GEO (Generative Engine Optimization) metrics from prompt_questions Q&A data.
    Auto-calls LLM tagging if Q&A not tagged yet.
    
    Request body:
        - prompt_question_id: str (required)
        - brand_name: str (optional - if not provided, uses project/company data)
        - brand_url: str (optional - for first-party citation check)
        - competitors: list[str] (optional - for competitive metrics)
    """
    try:
        one_week_ago = datetime.utcnow() - timedelta(days=7)
        body = await request.json()
        prompt_question_id = body.get("prompt_question_id")
        brand_name = body.get("brand_name", "").strip()
        brand_url = body.get("brand_url", "").strip()
        competitors = body.get("competitors", [])
        
        if not prompt_question_id:
            raise HTTPException(status_code=400, detail="prompt_question_id is required")
        
        # Fetch prompt_questions document
        doc = await find_one(PromptQuestionsModel, {"_id": ObjectId(prompt_question_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="Prompt questions document not found")
        brand_url = doc.website_url
        print("brand_url",brand_url)
        # 🔥 Auto-fetch brand_name from website analysis if not provided
        if not brand_name:
            # Try to get brand from chatgpt/gemini website analysis
            if doc.chatgpt_website_analysis:
                try:
                    analysis = json.loads(doc.chatgpt_website_analysis) if isinstance(doc.chatgpt_website_analysis, str) else doc.chatgpt_website_analysis
                    brand_name = analysis.get("brandName", "") or analysis.get("brand_name", "")
                except:
                    pass
            if not brand_name and doc.gemini_website_analysis:
                try:
                    analysis = json.loads(doc.gemini_website_analysis) if isinstance(doc.gemini_website_analysis, str) else doc.gemini_website_analysis
                    brand_name = analysis.get("brandName", "") or analysis.get("brand_name", "")
                except:
                    pass
            if not brand_name and doc.website_url:
                # Fallback to domain name
                brand_name = doc.website_url.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
        
        if not brand_name:
            raise HTTPException(status_code=400, detail="brand_name is required (could not auto-detect)")
        
        # 🔥 Auto-discover competitors if not provided
        niche = ""
        if not competitors:
            # Try to get niche from website analysis
            if doc.chatgpt_website_analysis:
                try:
                    analysis = json.loads(doc.chatgpt_website_analysis) if isinstance(doc.chatgpt_website_analysis, str) else doc.chatgpt_website_analysis
                    niche = analysis.get("niche", "")
                except:
                    pass
            if not niche and doc.gemini_website_analysis:
                try:
                    analysis = json.loads(doc.gemini_website_analysis) if isinstance(doc.gemini_website_analysis, str) else doc.gemini_website_analysis
                    niche = analysis.get("niche", "")
                except:
                    pass
            
            # Use LLM to find competitors based on niche
            if niche:
                try:
                    # 🆕 Use key manager
                    model = key_manager.get_model("gemini-3-flash-preview")
                    comp_prompt = f"""You are a competitive analysis expert.
                    
Brand: {brand_name}
Niche: {niche}
Location: {doc.nation or 'Global'}, {doc.state or ''}

List the top 5 direct competitors of {brand_name} in the {niche} space.
Return ONLY a JSON array of competitor names, no explanations.
Example: ["Competitor1", "Competitor2", "Competitor3"]"""
                    
                    response = await model.generate_content_async(
                        comp_prompt,
                        generation_config=genai.GenerationConfig(
                            temperature=0.3,
                            response_mime_type="application/json"
                        )
                    )
                    competitors = extract_json_from_text(response.text)
                    if not isinstance(competitors, list):
                        competitors = []
                    print(f"🔍 Auto-discovered competitors: {competitors}")
                    # Rate limit delay after competitor discovery
                    print(f"⏳ Waiting 20s for rate limit...")
                    await asyncio.sleep(20)
                except Exception as e:
                    print(f"❌ Competitor discovery failed: {e}")
                    # 🆕 Try switching key if rate limit
                    if key_manager.is_rate_limit_error(e) and key_manager.switch_to_next_key():
                        print("🔄 Switched API key, continuing...")
                    competitors = []
        
        qna_list = doc.qna or []
        total_prompts = len(qna_list)
        
        if total_prompts == 0:
            return {
                "total_prompts": 0,
                "brand_name": brand_name,
                "message": "No Q&A data found"
            }
        
        # 🔥 Check if any Q&A needs LLM tagging
        needs_tagging = False
        for qna in qna_list:
            llm_flags = getattr(qna, 'llm_flags', None)
            answer = qna.answer or ""
            if answer and answer != "Not available yet" and not llm_flags:
                needs_tagging = True
                break
        
        # 🔥 Auto-tag if needed
        if needs_tagging:
            print(f"🔄 Auto-tagging Q&A for brand: {brand_name}")
            competitors_str = ", ".join(competitors) if competitors else "None specified"
            
            # 🆕 Reset to first key for new tagging session
            key_manager.reset_to_first_key()
            model = key_manager.get_model("gemini-3-flash-preview")
            
            updated_qna = []
            for idx, qna in enumerate(qna_list):
                qna_dict = qna.dict() if hasattr(qna, 'dict') else dict(qna)
                
                # Skip if already tagged
                if qna_dict.get("llm_flags"):
                    updated_qna.append(qna_dict)
                    continue
                
                question = qna_dict.get("question", "")
                answer = qna_dict.get("answer", "")
                
                if not answer or answer == "Not available yet":
                    updated_qna.append(qna_dict)
                    continue
                
                # LLM Prompt for semantic tagging
                prompt = f"""You are a GEO (Generative Engine Optimization) analyzer.

Given:
Brand: {brand_name}
Competitors: {competitors_str}

Question:
{question}

Answer:
{answer}

Analyze and return STRICT JSON with these fields ONLY:
- brand_in_question: boolean (does the question itself contain "{brand_name}" or variations of it?)
- brand_mentioned: boolean (is {brand_name} mentioned in the answer?)
- brand_rank: number or null (position where {brand_name} appears: 1=first, 2=second, etc. null if not mentioned)
- is_recommended: boolean (is {brand_name} positively recommended?)
- sentiment: string (positive/neutral_positive/neutral/negative - sentiment towards {brand_name}. Use "neutral_positive" for mildly positive or generally favorable language without strong endorsement)
- citation_type: string (first_party/third_party/none - does answer cite {brand_name}'s official source?)
- citation_expected: boolean (is this a type of question where citations/sources are expected? e.g. factual claims, comparisons, reviews)
- features_mentioned: array of strings (features/qualities mentioned for {brand_name})
- competitors_mentioned: array of strings (which competitors from the list are mentioned?)

Return ONLY valid JSON, no explanations."""

                # 🆕 Try with current key, rotate on rate limit
                max_retries = len(key_manager.keys) if key_manager.keys else 1
                success = False
                
                for retry in range(max_retries):
                    try:
                        response = await model.generate_content_async(
                            prompt,
                            generation_config=genai.GenerationConfig(
                                temperature=0.2,
                                response_mime_type="application/json"
                            )
                        )
                        
                        flags_data = extract_json_from_text(response.text)
                        
                        llm_flags = {
                            "brand_in_question": bool(flags_data.get("brand_in_question", False)),
                            "brand_mentioned": bool(flags_data.get("brand_mentioned", False)),
                            "brand_rank": flags_data.get("brand_rank"),
                            "is_recommended": bool(flags_data.get("is_recommended", False)),
                            "sentiment": flags_data.get("sentiment", "neutral"),
                            "citation_type": flags_data.get("citation_type", "none"),
                            "citation_expected": bool(flags_data.get("citation_expected", False)),
                            "features_mentioned": flags_data.get("features_mentioned", []),
                            "competitors_mentioned": flags_data.get("competitors_mentioned", [])
                        }
                        
                        qna_dict["llm_flags"] = llm_flags
                        print(f"✅ Tagged Q&A {idx + 1}/{len(qna_list)} using {key_manager.get_current_key_name()}")
                        success = True
                        break  # Success, exit retry loop
                        
                    except Exception as e:
                        error_str = str(e)
                        print(f"❌ Error for Q&A {idx + 1} with {key_manager.get_current_key_name()}: {error_str[:100]}")
                        
                        # 🆕 Check if rate limit error
                        if key_manager.is_rate_limit_error(e):
                            print(f"⚠️ Rate limit hit on {key_manager.get_current_key_name()}")
                            
                            # 🆕 Save progress before switching keys
                            if updated_qna:
                                print(f"💾 Saving progress ({len(updated_qna)} items tagged so far)...")
                                await update_one(
                                    PromptQuestionsModel,
                                    {"_id": ObjectId(prompt_question_id)},
                                    {"$set": {"qna": updated_qna + [qna_dict] + [q.dict() if hasattr(q, 'dict') else dict(q) for q in qna_list[idx+1:]]}}
                                )
                            
                            # 🆕 Try switching to next key
                            if key_manager.switch_to_next_key():
                                model = key_manager.get_model("gemini-3-flash-preview")
                                print(f"🔄 Retrying Q&A {idx + 1} with new key...")
                                continue  # Retry with new key
                            else:
                                print(f"⛔ All keys exhausted! Stopping at Q&A {idx + 1}")
                                break
                        else:
                            # Non-rate-limit error, skip this item
                            print(f"⚠️ Non-rate-limit error, skipping Q&A {idx + 1}")
                            break
                
                updated_qna.append(qna_dict)
                
                # 🆕 Rate limiting: Wait 20 seconds to stay within limit
                if idx < len(qna_list) - 1:
                    print(f"⏳ Waiting 20s for rate limit (5 req/min)...")
                    await asyncio.sleep(20)
            
            # Save tagged data to DB
            await update_one(
                PromptQuestionsModel,
                {"_id": ObjectId(prompt_question_id)},
                {"$set": {"qna": updated_qna}}
            )
            
            # Refresh doc with updated data
            doc = await find_one(PromptQuestionsModel, {"_id": ObjectId(prompt_question_id)})
            qna_list = doc.qna or []
        

        # 🆕 Initialize counters for BRAND-AGNOSTIC prompts (real brand discovery)
        agnostic_total = 0
        agnostic_mentions = 0
        agnostic_top_3 = 0
        agnostic_recommended = 0
        agnostic_positive_sentiment = 0
        agnostic_citations = 0
        agnostic_citations_expected = 0
        agnostic_zero_mention_prompts = []
        
        # 🆕 Initialize counters for BRAND-INCLUDED prompts (branded queries)
        included_total = 0
        included_mentions = 0
        included_top_3 = 0
        included_recommended = 0
        included_positive_sentiment = 0
        included_citations = 0
        included_citations_expected = 0
        included_zero_mention_prompts = []
        
        # Common trackers
        competitor_mentions = {comp: 0 for comp in competitors}
        brand_features = set()
        using_llm_flags = False
        
        for qna in qna_list:
            question = qna.question or ""
            answer = qna.answer or ""
            category_name = qna.category_name
            
            # 🔥 Use LLM flags if available (10x faster + accurate)
            llm_flags = getattr(qna, 'llm_flags', None)
            if llm_flags and hasattr(llm_flags, 'brand_mentioned'):
                using_llm_flags = True
                
                # 🆕 Determine which bucket this Q&A belongs to
                is_brand_in_question = getattr(llm_flags, 'brand_in_question', False)
                citation_expected = getattr(llm_flags, 'citation_expected', False)
                
                if is_brand_in_question:
                    # ===== BRAND-INCLUDED BUCKET =====
                    included_total += 1
                    if citation_expected:
                        included_citations_expected += 1
                    
                    if llm_flags.brand_mentioned:
                        included_mentions += 1
                        
                        # Top-3 position
                        if llm_flags.brand_rank and llm_flags.brand_rank <= 3:
                            included_top_3 += 1
                        
                        # First-party citation
                        if llm_flags.citation_type == "first_party":
                            included_citations += 1
                        
                        # Recommendation
                        if llm_flags.is_recommended:
                            included_recommended += 1
                        
                        # 🆕 Include neutral_positive as positive
                        if llm_flags.sentiment in ["positive", "neutral_positive"]:
                            included_positive_sentiment += 1
                        
                        # Features
                        if llm_flags.features_mentioned:
                            brand_features.update(llm_flags.features_mentioned)
                    else:
                        included_zero_mention_prompts.append({
                            "question": question,
                            "answer_snippet": answer[:200] + "..." if len(answer) > 200 else answer,
                            "category_name": category_name
                        })
                else:
                    # ===== BRAND-AGNOSTIC BUCKET (TRUE DISCOVERY) =====
                    agnostic_total += 1
                    if citation_expected:
                        agnostic_citations_expected += 1
                    
                    if llm_flags.brand_mentioned:
                        agnostic_mentions += 1
                        
                        # Top-3 position
                        if llm_flags.brand_rank and llm_flags.brand_rank <= 3:
                            agnostic_top_3 += 1
                        
                        # First-party citation
                        if llm_flags.citation_type == "first_party":
                            agnostic_citations += 1
                        
                        # Recommendation
                        if llm_flags.is_recommended:
                            agnostic_recommended += 1
                        
                        # 🆕 Include neutral_positive as positive
                        if llm_flags.sentiment in ["positive", "neutral_positive"]:
                            agnostic_positive_sentiment += 1
                        
                        # Features
                        if llm_flags.features_mentioned:
                            brand_features.update(llm_flags.features_mentioned)
                        
                        # Competitors (only track in agnostic bucket for fair comparison)
                        if llm_flags.competitors_mentioned:
                            for comp in llm_flags.competitors_mentioned:
                                if comp in competitor_mentions:
                                    competitor_mentions[comp] += 1
                    else:
                        agnostic_zero_mention_prompts.append({
                            "question": question,
                            "answer_snippet": answer[:200] + "..." if len(answer) > 200 else answer,
                            "category_name": category_name
                        })
            else:
                # 🔹 Fallback: Regex-based detection (slower, less accurate)
                # Count as agnostic by default when no LLM flags
                brand_pattern = re.compile(re.escape(brand_name), re.IGNORECASE)
                
                # Check if brand is in question
                brand_in_q = bool(brand_pattern.search(question))
                
                if brand_in_q:
                    included_total += 1
                    bucket_mentions = included_mentions
                else:
                    agnostic_total += 1
                
                brand_match = brand_pattern.search(answer)
                
                if brand_match:
                    if brand_in_q:
                        included_mentions += 1
                    else:
                        agnostic_mentions += 1
                    brand_pos = brand_match.start()
                    
                    # Simple heuristic for top-3
                    lines = [l.strip() for l in answer.split('\n') if l.strip()]
                    numbered_items = [l for l in lines if re.match(r'^[\d\.\-\*]+', l)]
                    
                    is_top_3 = False
                    if numbered_items:
                        first_3_items = ' '.join(numbered_items[:3])
                        if brand_pattern.search(first_3_items):
                            is_top_3 = True
                    elif brand_pos < len(answer) * 0.3:
                        is_top_3 = True
                    
                    if is_top_3:
                        if brand_in_q:
                            included_top_3 += 1
                        else:
                            agnostic_top_3 += 1
                    
                    # First-party citation check
                    if brand_url and brand_url.lower() in answer.lower():
                        if brand_in_q:
                            included_citations += 1
                        else:
                            agnostic_citations += 1
                else:
                    if brand_in_q:
                        included_zero_mention_prompts.append({
                            "question": question,
                            "answer_snippet": answer[:200] + "..." if len(answer) > 200 else answer,
                            "category_name": category_name
                        })
                    else:
                        agnostic_zero_mention_prompts.append({
                            "question": question,
                            "answer_snippet": answer[:200] + "..." if len(answer) > 200 else answer,
                            "category_name": category_name
                        })
        
        # 🆕 Calculate SEGMENTED metrics
        
        # Brand-Agnostic Metrics (TRUE organic discovery)
        agnostic_brand_mention_rate = round((agnostic_mentions / agnostic_total) * 100, 2) if agnostic_total > 0 else 0
        agnostic_top_3_rate = round((agnostic_top_3 / agnostic_mentions) * 100, 2) if agnostic_mentions > 0 else 0
        agnostic_recommendation_rate = round((agnostic_recommended / agnostic_mentions) * 100, 2) if agnostic_mentions > 0 else 0
        agnostic_positive_sentiment_rate = round((agnostic_positive_sentiment / agnostic_mentions) * 100, 2) if agnostic_mentions > 0 else 0
        agnostic_citation_rate = round((agnostic_citations / agnostic_citations_expected) * 100, 2) if agnostic_citations_expected > 0 else 0
        
        # Brand-Included Metrics (branded query performance)
        included_brand_mention_rate = round((included_mentions / included_total) * 100, 2) if included_total > 0 else 0
        included_top_3_rate = round((included_top_3 / included_mentions) * 100, 2) if included_mentions > 0 else 0
        included_recommendation_rate = round((included_recommended / included_mentions) * 100, 2) if included_mentions > 0 else 0
        included_positive_sentiment_rate = round((included_positive_sentiment / included_mentions) * 100, 2) if included_mentions > 0 else 0
        included_citation_rate = round((included_citations / included_citations_expected) * 100, 2) if included_citations_expected > 0 else 0
        
        # Combined metrics (for legacy support)
        total_mentions = agnostic_mentions + included_mentions
        combined_brand_mention_rate = round((total_mentions / total_prompts) * 100, 2) if total_prompts > 0 else 0
        combined_top_3_rate = round(((agnostic_top_3 + included_top_3) / total_mentions) * 100, 2) if total_mentions > 0 else 0
        
        # Comparison presence (how often brand appears with competitors)
        comparison_presence = 0
        prompts_with_comparison = sum(1 for comp, count in competitor_mentions.items() if count > 0)
        if competitors and agnostic_mentions > 0:
            comparison_presence = round((prompts_with_comparison / len(competitors)) * 100, 2)
        print("hello12222")
        
        print("hello122226666")
        # 🆕 Save metrics to database
        metrics_result = {
    "brand_agnostic_metrics": {
        "total_prompts": agnostic_total,
        "mentions": agnostic_mentions,
        "brand_mention_rate": agnostic_brand_mention_rate,
        "top_3_mentions": agnostic_top_3,
        "top_3_position_rate": agnostic_top_3_rate,
        "recommendation_rate": agnostic_recommendation_rate,
        "positive_sentiment_rate": agnostic_positive_sentiment_rate,
        "citations_expected": agnostic_citations_expected,
        "first_party_citations": agnostic_citations,
        "first_party_citation_rate": agnostic_citation_rate,
        "zero_mention_count": len(agnostic_zero_mention_prompts),
    },
    "brand_included_metrics": {
        "total_prompts": included_total,
        "mentions": included_mentions,
        "brand_mention_rate": included_brand_mention_rate,
        "top_3_mentions": included_top_3,
        "top_3_position_rate": included_top_3_rate,
        "recommendation_rate": included_recommendation_rate,
        "positive_sentiment_rate": included_positive_sentiment_rate,
        "citations_expected": included_citations_expected,
        "first_party_citations": included_citations,
        "first_party_citation_rate": included_citation_rate,
        "zero_mention_count": len(included_zero_mention_prompts),
    }
}

        try:
            # Check if metrics already exist for this prompt_question_id
            existing_metrics = await GeoMetricsModel.find_one(
                {"prompt_question_id": ObjectId(prompt_question_id)}
            )
            print("existing_metrics--->",existing_metrics)
            if existing_metrics and existing_metrics.updatedAt > datetime.utcnow() - timedelta(days=7):
                print("hello1")
                # Update existing metrics
                existing_metrics.brand_name = brand_name
                existing_metrics.total_prompts = total_prompts
                existing_metrics.using_llm_flags = using_llm_flags
                existing_metrics.brand_agnostic_metrics = BrandAgnosticMetrics(**metrics_result["brand_agnostic_metrics"])
                existing_metrics.brand_included_metrics = BrandIncludedMetrics(**metrics_result["brand_included_metrics"])
                existing_metrics.total_mentions = total_mentions
                existing_metrics.brand_mention_rate = combined_brand_mention_rate
                existing_metrics.top_3_mentions = agnostic_top_3 + included_top_3
                existing_metrics.top_3_position_rate = combined_top_3_rate
                existing_metrics.zero_mention_count = len(agnostic_zero_mention_prompts) + len(included_zero_mention_prompts)
                existing_metrics.competitor_mentions = {comp: count for comp, count in competitor_mentions.items() if count > 0}
                existing_metrics.comparison_presence = comparison_presence
                existing_metrics.brand_features = list(brand_features)
                existing_metrics.updatedAt = datetime.utcnow()
                await existing_metrics.save()
                print(f"✅ Updated GEO metrics for prompt_question_id: {prompt_question_id}")
            else:
                print("hello2")
                # Create new metrics document
                new_metrics = GeoMetricsModel(
                    prompt_question_id=ObjectId(prompt_question_id),
                    brand_name=brand_name,
                    total_prompts=total_prompts,
                    using_llm_flags=using_llm_flags,
                    brand_agnostic_metrics=BrandAgnosticMetrics(**metrics_result["brand_agnostic_metrics"]),
                    brand_included_metrics=BrandIncludedMetrics(**metrics_result["brand_included_metrics"]),
                    total_mentions=total_mentions,
                    brand_mention_rate=combined_brand_mention_rate,
                    top_3_mentions=agnostic_top_3 + included_top_3,
                    top_3_position_rate=combined_top_3_rate,
                    zero_mention_count=len(agnostic_zero_mention_prompts) + len(included_zero_mention_prompts),
                    competitor_mentions={comp: count for comp, count in competitor_mentions.items() if count > 0},
                    comparison_presence=comparison_presence,
                    brand_features=list(brand_features)
                )
                await new_metrics.insert()
                print(f"✅ Created new GEO metrics for prompt_question_id: {prompt_question_id}")
        except Exception as save_error:
            import traceback
            print(traceback.format_exc())
            print(f"⚠️ Failed to save metrics to DB: {save_error}")
            # Continue and return metrics even if save fails
        
        return {
            "brand_name": brand_name,
            "total_prompts": total_prompts,
            "using_llm_flags": using_llm_flags,
            
            # 🆕 SEGMENTED METRICS - Brand Agnostic (TRUE discovery metrics)
            "brand_agnostic_metrics": {
                "description": "Metrics from prompts WITHOUT brand name - shows real organic discovery",
                "total_prompts": agnostic_total,
                "mentions": agnostic_mentions,
                "brand_mention_rate": agnostic_brand_mention_rate,
                "top_3_mentions": agnostic_top_3,
                "top_3_position_rate": agnostic_top_3_rate,
                "recommendation_rate": agnostic_recommendation_rate,
                "positive_sentiment_rate": agnostic_positive_sentiment_rate,
                "citations_expected": agnostic_citations_expected,
                "first_party_citations": agnostic_citations,
                "first_party_citation_rate": agnostic_citation_rate,
                "zero_mention_count": len(agnostic_zero_mention_prompts),
                "zero_mention_prompts": agnostic_zero_mention_prompts
            },
            
            # 🆕 SEGMENTED METRICS - Brand Included (branded query metrics)
            "brand_included_metrics": {
                "description": "Metrics from prompts WITH brand name - shows branded query performance",
                "total_prompts": included_total,
                "mentions": included_mentions,
                "brand_mention_rate": included_brand_mention_rate,
                "top_3_mentions": included_top_3,
                "top_3_position_rate": included_top_3_rate,
                "recommendation_rate": included_recommendation_rate,
                "positive_sentiment_rate": included_positive_sentiment_rate,
                "citations_expected": included_citations_expected,
                "first_party_citations": included_citations,
                "first_party_citation_rate": included_citation_rate,
                "zero_mention_count": len(included_zero_mention_prompts),
                "zero_mention_prompts": included_zero_mention_prompts
            },
            
            # Combined (legacy support + overall view)
            "total_mentions": total_mentions,
            "brand_mention_rate": combined_brand_mention_rate,
            "top_3_mentions": agnostic_top_3 + included_top_3,
            "top_3_position_rate": combined_top_3_rate,
            "zero_mention_count": len(agnostic_zero_mention_prompts) + len(included_zero_mention_prompts),
            
            # Competitive Metrics (from agnostic bucket only for fair comparison)
            # 🆕 Only include competitors that were actually mentioned in answers
            "competitor_mentions": {comp: count for comp, count in competitor_mentions.items() if count > 0},
            "comparison_presence": comparison_presence,
            "brand_features": list(brand_features)
        }
        
    except HTTPException as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))  
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))      





async def get_genrated_metrics_controller(request: Request):
    """
    Get saved GEO metrics for a specific prompt_question_id
    """
    try:
        body = await request.json()
        prompt_question_id = body.get("prompt_question_id")
        
        if not prompt_question_id:
            raise HTTPException(status_code=400, detail="prompt_question_id is required")
        
        print(f"📊 Fetching GEO metrics for: {prompt_question_id}")
        
        # Fetch from geo_metrics collection
        result = await GeoMetricsModel.find_one(
            {"prompt_question_id": ObjectId(prompt_question_id)}
        )
        
        if not result:
            raise HTTPException(
                status_code=404, 
                detail="GEO metrics not found. Please calculate metrics first using /calculate-geo-metrics endpoint."
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))