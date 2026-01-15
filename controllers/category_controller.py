from fastapi import HTTPException
from models.questionsCategory import QuestionsCategoryModel
from models.prompt_questions import PromptQuestionsModel, LLMFlags
from fastapi import Request
from bson import ObjectId
from global_db_opretions import find_one, update_one
import google.generativeai as genai
import os
import json
import re

# Configure Gemini
API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("API_KEY", "")
if API_KEY:
    genai.configure(api_key=API_KEY)

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
        
        model = genai.GenerativeModel("gemini-2.5-flash")
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
            model = genai.GenerativeModel("gemini-2.5-flash")
            
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
                    print(f"✅ Tagged Q&A {idx + 1}/{len(qna_list)}")
                    
                except Exception as e:
                    print(f"❌ LLM tagging failed for Q&A {idx + 1}: {e}")
                
                updated_qna.append(qna_dict)
            
            # Save tagged data to DB
            await update_one(
                PromptQuestionsModel,
                {"_id": ObjectId(prompt_question_id)},
                {"$set": {"qna": updated_qna}}
            )
            
            # Refresh doc with updated data
            doc = await find_one(PromptQuestionsModel, {"_id": ObjectId(prompt_question_id)})
            qna_list = doc.qna or []
        

        # Initialize counters
        mentions = 0
        top_3_mentions = 0
        zero_mention_prompts = []
        first_party_citations = 0
        recommended_count = 0
        positive_sentiment_count = 0
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
                
                if llm_flags.brand_mentioned:
                    mentions += 1
                    
                    # Top-3 position from LLM tag
                    if llm_flags.brand_rank and llm_flags.brand_rank <= 3:
                        top_3_mentions += 1
                    
                    # First-party citation from LLM
                    if llm_flags.citation_type == "first_party":
                        first_party_citations += 1
                    
                    # Recommendation & sentiment
                    if llm_flags.is_recommended:
                        recommended_count += 1
                    if llm_flags.sentiment == "positive":
                        positive_sentiment_count += 1
                    
                    # Features from LLM
                    if llm_flags.features_mentioned:
                        brand_features.update(llm_flags.features_mentioned)
                    
                    # Competitors mentioned by LLM
                    if llm_flags.competitors_mentioned:
                        for comp in llm_flags.competitors_mentioned:
                            if comp in competitor_mentions:
                                competitor_mentions[comp] += 1
                else:
                    # Zero mention
                    zero_mention_prompts.append({
                        "question": question,
                        "answer_snippet": answer[:200] + "..." if len(answer) > 200 else answer,
                        "category_name": category_name
                    })
            else:
                # 🔹 Fallback: Regex-based detection (slower, less accurate)
                brand_pattern = re.compile(re.escape(brand_name), re.IGNORECASE)
                brand_match = brand_pattern.search(answer)
                
                if brand_match:
                    mentions += 1
                    brand_pos = brand_match.start()
                    
                    # Simple heuristic for top-3
                    lines = [l.strip() for l in answer.split('\n') if l.strip()]
                    numbered_items = [l for l in lines if re.match(r'^[\d\.\-\*]+', l)]
                    
                    if numbered_items:
                        first_3_items = ' '.join(numbered_items[:3])
                        if brand_pattern.search(first_3_items):
                            top_3_mentions += 1
                    elif brand_pos < len(answer) * 0.3:
                        top_3_mentions += 1
                    
                    # First-party citation check
                    if brand_url and brand_url.lower() in answer.lower():
                        first_party_citations += 1
                else:
                    zero_mention_prompts.append({
                        "question": question,
                        "answer_snippet": answer[:200] + "..." if len(answer) > 200 else answer,
                        "category_name": category_name
                    })
        
        # Calculate metrics
        brand_mention_rate = round((mentions / total_prompts) * 100, 2) if total_prompts > 0 else 0
        top_3_position_rate = round((top_3_mentions / mentions) * 100, 2) if mentions > 0 else 0
        first_party_citation_rate = round((first_party_citations / mentions) * 100, 2) if mentions > 0 else 0
        recommendation_rate = round((recommended_count / mentions) * 100, 2) if mentions > 0 else 0
        positive_sentiment_rate = round((positive_sentiment_count / mentions) * 100, 2) if mentions > 0 else 0
        
        # Comparison presence (how often brand appears with competitors)
        comparison_presence = 0
        prompts_with_comparison = sum(1 for comp, count in competitor_mentions.items() if count > 0)
        if competitors and mentions > 0:
            comparison_presence = round((prompts_with_comparison / len(competitors)) * 100, 2)
        
        return {
            "brand_name": brand_name,
            "total_prompts": total_prompts,
            "using_llm_flags": using_llm_flags,
            
            # Brand Mention Rate
            "total_mentions": mentions,
            "brand_mention_rate": brand_mention_rate,
            
            # Top-3 Position Rate
            "top_3_mentions": top_3_mentions,
            "top_3_position_rate": top_3_position_rate,
            
            # Zero-Mention Gap
            "zero_mention_count": len(zero_mention_prompts),
            "zero_mention_prompts": zero_mention_prompts,
            
            # First-Party Citation
            "first_party_citations": first_party_citations,
            "first_party_citation_rate": first_party_citation_rate,
            
            # 🆕 LLM-based metrics (only accurate when using_llm_flags=True)
            "recommendation_rate": recommendation_rate,
            "positive_sentiment_rate": positive_sentiment_rate,
            
            # Competitive Metrics
            "competitor_mentions": competitor_mentions,
            "comparison_presence": comparison_presence,
            "brand_features": list(brand_features)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))      