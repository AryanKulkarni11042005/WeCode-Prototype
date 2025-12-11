import os
import json
import re
import asyncio
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI()

# --- CONFIGURATION ---
BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

# Load keys
API_KEY_1 = os.getenv("key_1")
API_KEY_2 = os.getenv("key_2")
REF_KEY = os.getenv("ref_key")

# Referee Model
REFEREE_MODEL = "google/gemini-2.0-flash-exp:free"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CompetitionRequest(BaseModel):
    prompt: str
    model_1: str
    model_2: str

def clean_json_text(text):
    """Extracts JSON from markdown code blocks."""
    if not text: return "{}"
    text = re.sub(r"^```[a-zA-Z]*\n", "", text.strip())
    text = re.sub(r"\n```$", "", text)
    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        return match.group(1)
    return text

async def fetch_with_key(client, api_key, model, messages, retries=3):
    """
    Fetches data with robust error handling and longer backoff.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5173",
        "X-Title": "IdeaForge"
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
    }

    for i in range(retries):
        try:
            print(f"🔄 Calling {model} (Attempt {i+1})...")
            response = await client.post(BASE_URL, headers=headers, json=payload, timeout=60.0)
            
            if response.status_code == 200:
                data = response.json()
                if "choices" in data and data["choices"]:
                    return data["choices"][0]["message"]["content"]
                return "Error: Empty response."
            
            elif response.status_code == 429:
                # RATE LIMIT HIT: Wait longer (20s, 40s, 60s)
                wait_time = (i + 1) * 20 
                print(f"⚠️ Rate limit (429). Waiting {wait_time}s...")
                await asyncio.sleep(wait_time)
                continue
            
            else:
                return f"Error HTTP {response.status_code}: {response.text}"

        except Exception as e:
            print(f"Connection Error: {e}")
            await asyncio.sleep(5)
    
    return f"Error: Failed to get response from {model} after retries."

@app.post("/run-competition")
async def run_competition(request: CompetitionRequest):
    if not API_KEY_1 or not API_KEY_2 or not REF_KEY:
        raise HTTPException(status_code=500, detail="Missing API keys in .env")

    async with httpx.AsyncClient() as client:
        print(f"\n🚀 STARTING: {request.model_1} vs {request.model_2}")

        # --- STEP 1: CONTESTANT 1 ---
        prompt_1 = f"Write a comprehensive startup idea for: {request.prompt}. Do not use markdown headers, just plain text pitch."
        res1 = await fetch_with_key(client, API_KEY_1, request.model_1, [{"role": "user", "content": prompt_1}])
        
        # Fallback if failed
        if res1.startswith("Error"):
            print(f"❌ Model 1 Failed: {res1}")
            res1 = f"Failed to generate idea. Reason: {res1}"
        else:
            print(f"✅ Model 1 Done")

        # Safety Buffer
        await asyncio.sleep(5) 

        # --- STEP 2: CONTESTANT 2 ---
        prompt_2 = f"Write a comprehensive startup idea for: {request.prompt}. Do not use markdown headers, just plain text pitch."
        res2 = await fetch_with_key(client, API_KEY_2, request.model_2, [{"role": "user", "content": prompt_2}])
        
        # Fallback if failed
        if res2.startswith("Error"):
            print(f"❌ Model 2 Failed: {res2}")
            res2 = f"Failed to generate idea. Reason: {res2}"
        else:
            print(f"✅ Model 2 Done")

        # Safety Buffer
        await asyncio.sleep(5)

        # --- STEP 3: REFEREE ---
        referee_prompt = f"""
        Act as a Venture Capitalist Judge. 
        Evaluate these two startup pitches based on the User Prompt: "{request.prompt}"

        === PITCH 1 ({request.model_1}) ===
        {res1[:3000]}

        === PITCH 2 ({request.model_2}) ===
        {res2[:3000]}

        INSTRUCTIONS:
        1. Compare them on Innovation, Market, and Feasibility.
        2. Assign scores (0-10).
        3. Pick a winner.
        4. Output ONLY valid JSON.

        JSON Structure:
        {{
            "evaluations": {{
                "{request.model_1}": {{ "scores": {{ "innovation": 0, "market": 0, "feasibility": 0 }}, "total_score": 0, "justification": "Short summary" }},
                "{request.model_2}": {{ "scores": {{ "innovation": 0, "market": 0, "feasibility": 0 }}, "total_score": 0, "justification": "Short summary" }}
            }},
            "winner_model": "{request.model_1}"
        }}
        """
        
        print(f"⚖️ Referee ({REFEREE_MODEL}) is Judging...")
        ref_raw = await fetch_with_key(client, REF_KEY, REFEREE_MODEL, [{"role": "user", "content": referee_prompt}])
        
        # CRITICAL FIX: Don't parse if Referee failed
        if ref_raw.startswith("Error"):
            print(f"❌ Referee Failed: {ref_raw}")
            referee_data = {
                "evaluations": {},
                "winner_model": "Referee Failed",
                "raw_output": ref_raw
            }
        else:
            try:
                clean_json = clean_json_text(ref_raw)
                referee_data = json.loads(clean_json)
                print("✅ Referee Judged Successfully")
            except Exception as e:
                print(f"❌ JSON Parsing Failed: {e}")
                referee_data = {
                    "evaluations": {},
                    "winner_model": "Unknown",
                    "raw_output": ref_raw
                }

    print("🏁 Competition Complete.\n")

    return {
        "contestant_outputs": [
            {"model": request.model_1, "idea": res1},
            {"model": request.model_2, "idea": res2}
        ],
        "referee": referee_data
    }