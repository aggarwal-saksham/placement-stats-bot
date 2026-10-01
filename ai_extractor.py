import os
import json
import re
import time
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional

class CompanyRecord(BaseModel):
    Company: str
    CGPA_criteria: float = 0.0
    Offer_Type: Optional[str] = "FTE"
    Role: Optional[str] = None
    Count: Optional[float] = None
    CTC_in_LPA: Optional[float] = None
    Base_in_LPA: Optional[float] = None
    Stipend_in_K: Optional[float] = None
    Category: Optional[str] = "TECH"
    Comments: Optional[str] = None

    @field_validator("CGPA_criteria", mode="before")
    def default_cgpa(cls, v):
        if v is None or str(v).strip().lower() in ['', 'none', 'null', 'nan']:
            return 0.0
        try:
            return float(v)
        except Exception:
            return 0.0

    @field_validator("Role", mode="before")
    def default_role(cls, v):
        return v if v else None

    @field_validator("Offer_Type", mode="before")
    def default_offer_type(cls, v):
        return v if v else "FTE"

    @field_validator("Category", mode="before")
    def default_category(cls, v):
        return v if v else "TECH"

class StudentRecord(BaseModel):
    Roll_No: Optional[str] = None
    Name: Optional[str] = None
    Company: str
    Role: Optional[str] = None
    Offer_Type: Optional[str] = "FTE"

    @field_validator("Role", mode="before")
    def default_role(cls, v):
        return v if v else None

    @field_validator("Offer_Type", mode="before")
    def default_offer_type(cls, v):
        return v if v else "FTE"

class PlacementParseResult(BaseModel):
    message_type: str  # 'COMPANY_ANNOUNCEMENT', 'STUDENT_PLACEMENT', 'BOTH'
    companies: List[CompanyRecord] = []
    students: List[StudentRecord] = []

SYSTEM_PROMPT = """
You are a specialized Placement & Internship Data Parser for a college placement portal.
Convert unstructured placement text into structured JSON.

### REQUIRED JSON OUTPUT FORMAT:
{
  "message_type": "COMPANY_ANNOUNCEMENT" | "STUDENT_PLACEMENT" | "BOTH",
  "companies": [
    {
      "Company": "Exact Company Name as written in the announcement (CRITICAL: Extract VERBATIM. NEVER abbreviate, expand, rename, or standardize)",
      "CGPA_criteria": 7.5 (float, default to 0.0 if not specified),
      "Offer_Type": "6M + PPO" | "6M + FTE" | "FTE" | "PPO",
      "Role": "Job Title (e.g. Data and AI Consultant)",
      "Count": null (float or null),
      "CTC_in_LPA": 14.8 (float, upper limit if range given, e.g. 10.0 for 8-10 LPA),
      "Base_in_LPA": null (float, upper limit if range given),
      "Stipend_in_K": 45.0 (float in thousands, upper limit if range given, e.g. 20.0 for 15,000-20,000/M or 45.0 for 45k/month),
      "Category": "TECH" | "NON TECH" | "CORE",
      "Comments": "Location / original salary ranges if given e.g. 'Location: Bengaluru | Stipend: 15k-20k/M | CTC: 8-10 LPA'"
    }
  ],
  "students": [
    {
      "Roll_No": "23/IT/145" (or null if unstated),
      "Name": "Student Name" (or null if unstated),
      "Company": "Exact Company Name as written in the announcement",
      "Role": "Job Title" (or null if unstated),
      "Offer_Type": "6M + PPO" | "6M + FTE" | "FTE" | "PPO"
    }
  ]
}

### CRITICAL PARSING RULES:
1. **EXACT COMPANY NAME (STRICT RULE)**:
   - Extract the company name **EXACTLY as written in the announcement message**.
   - NEVER abbreviate (e.g. do NOT change "World Wide Technology" to "WWT").
   - NEVER expand abbreviations (e.g. do NOT change "WWT" to "World Wide Technology").
   - NEVER replace, standardize, clean up, or alter company names.
   - Preserve the exact words, spelling, and phrasing as typed in the message.
2. **STRICTLY BTECH ONLY (IGNORE MTECH COMPLETELY)**:
   - This portal is strictly for BTech placements.
   - Ignore ALL MTech, Dual Degree, PhD, or postgraduate branches, roles, cutoffs, and criteria.
   - If separate cutoffs are given (e.g. "CGPA CUTOFF: 7.5 (BTech) / 7 (MTech)"), extract ONLY the BTech cutoff (7.5).
   - If eligibility lists BTech and MTech separately, only extract/consider BTech criteria.
   - NEVER include MTech notes or MTech criteria in the "Comments" field.
3. **CTC & STIPEND RANGE RULE (UPPER LIMIT + RECORD IN COMMENTS)**:
   - If a range is given for CTC (e.g. "8-10 LPA", "15 - 18 LPA", "12 to 14 LPA"):
     - Set `CTC_in_LPA` to the **UPPER LIMIT** (e.g. 10.0, 18.0, 14.0).
     - You MUST record the original range in `Comments` (e.g. "CTC: 8-10 LPA").
   - If a range is given for Stipend (e.g. "INR 15,000-20,000 /M", "15k-20k/month", "30-40k"):
     - Set `Stipend_in_K` to the **UPPER LIMIT** in thousands (e.g. 20.0 for 15,000-20,000/M, 40.0 for 30-40k).
     - You MUST record the original range in `Comments` (e.g. "Stipend: 15,000-20,000 /M").
   - If a range is given for Base, set `Base_in_LPA` to the upper limit and record in `Comments`.
   - any other info about ctc or stipend if mention in message should also be added to comments.
   - Preserve existing location or other notes in `Comments` alongside the range (e.g. "Location: Noida | CTC: 8-10 LPA | Stipend: 15k-20k/M").
4. **DEFAULT CGPA CUTOFF**: If CGPA cutoff is not stated in the message, set `"CGPA_criteria": 0.0`.
5. **Multi-Role Companies**: If a company announcement lists multiple roles (e.g. Software Engineer AND Data Analyst), CREATE SEPARATE COMPANY OBJECTS IN THE ARRAY FOR EACH ROLE with identical CTC/stipend details.
6. **Category**:
   - `NON TECH`: Data Analyst, DA, Business Analyst, Analyst, Consultant, Product Analyst, Operations, Finance, Data and AI Consultant, etc.
   - `TECH`: SDE, SWE, Software Engineer, MLE, Data Science Engineer, Data Scientist, Frontend, Backend, Full Stack, DevOps, Product Engineer, etc.
   - `CORE`: Mechanical, Civil, Electrical, Electronics, VLSI, Embedded, GET, Chemical, etc.
7. Return ONLY valid JSON adhering strictly to the above format.
"""

class AIExtractor:
    def __init__(self, api_key: str = None):
        env_keys = os.getenv("GEMINI_API_KEYS", "") or os.getenv("GEMINI_API_KEY", "")
        if api_key:
            self.api_keys = [api_key]
        elif env_keys:
            self.api_keys = [k.strip() for k in env_keys.split(",") if k.strip()]
        else:
            self.api_keys = []

    def parse_message(self, text: str) -> PlacementParseResult:
        if not self.api_keys:
            raise ValueError("GEMINI_API_KEY is missing! Please set GEMINI_API_KEY in .env.")

        raw_json_str = ""
        candidate_models = [
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite",
            "gemini-3.8-flash",
            "gemini-flash-latest",
            "gemini-3.7-flash",
            "gemini-flash-lite-latest",
            "gemini-pro-latest",
        ]
        last_error = None

        # Try API calls across API keys and auto-fallback models
        for current_key in self.api_keys:
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=current_key)
                
                for m_name in candidate_models:
                    try:
                        response = client.models.generate_content(
                            model=m_name,
                            contents=f"{SYSTEM_PROMPT}\n\nParse the following placement text:\n\n{text}",
                            config=types.GenerateContentConfig(
                                response_mime_type='application/json',
                                temperature=0.1
                            )
                        )
                        if response and response.text:
                            raw_json_str = response.text
                            print(f"✅ Successfully parsed using Gemini model: {m_name}")
                            break
                    except Exception as ex:
                        last_error = ex
                        err_msg = str(ex).lower()
                        if any(kw in err_msg for kw in ["429", "quota", "resource_exhausted", "limit", "rate"]):
                            print(f"⚠️ Model '{m_name}' hit rate/quota limit. Auto-spinning down to next LLM...")
                        else:
                            print(f"⚠️ Model '{m_name}' failed ({ex}). Spinning down to next LLM...")
                        continue

                if raw_json_str:
                    break
            except Exception as e1:
                last_error = e1

        # Fallback to legacy SDK if needed
        if not raw_json_str:
            for current_key in self.api_keys:
                try:
                    import google.generativeai as genai_old
                    genai_old.configure(api_key=current_key)
                    for m_name in candidate_models:
                        try:
                            model = genai_old.GenerativeModel(m_name)
                            response = model.generate_content(
                                f"{SYSTEM_PROMPT}\n\nParse the following placement text:\n\n{text}",
                                generation_config={"response_mime_type": "application/json", "temperature": 0.1}
                            )
                            if response and response.text:
                                raw_json_str = response.text
                                print(f"✅ Successfully parsed using legacy SDK model: {m_name}")
                                break
                        except Exception as ex:
                            last_error = ex
                            print(f"⚠️ Legacy model '{m_name}' failed/quota exceeded. Spinning down to next...")
                            continue
                    if raw_json_str:
                        break
                except Exception:
                    pass

        if not raw_json_str:
            raise RuntimeError(f"Gemini API Error (all fallback models exhausted): {last_error}")

        # Clean JSON markdown if any
        clean_str = re.sub(r'^```json\s*', '', raw_json_str.strip())
        clean_str = re.sub(r'\s*```$', '', clean_str)

        data = json.loads(clean_str)
        result = PlacementParseResult.model_validate(data)

        # Post-process parsed companies for range safety and BTech enforcement
        ctc_range_match = re.search(r'(?:CTC|Package)[^\n:]*:\s*([^\n]+)', text, re.IGNORECASE)
        ctc_range_str = None
        ctc_upper = None
        if ctc_range_match:
            raw_val = ctc_range_match.group(1).replace('*', '').strip()
            m = re.search(r'(\d+(?:\.\d+)?)\s*[-–to]+\s*(\d+(?:\.\d+)?)\s*(?:LPA|L)?', raw_val, re.IGNORECASE)
            if m:
                ctc_range_str = f"CTC: {raw_val}"
                ctc_upper = float(m.group(2))

        stipend_range_match = re.search(r'(?:Stipend)[^\n:]*:\s*([^\n]+)', text, re.IGNORECASE)
        stipend_range_str = None
        stipend_upper = None
        if stipend_range_match:
            raw_val = stipend_range_match.group(1).replace('*', '').strip()
            m1 = re.search(r'(\d{1,3}(?:,\d{3})+|\d+)\s*[-–to]+\s*(\d{1,3}(?:,\d{3})+|\d+)', raw_val, re.IGNORECASE)
            m2 = re.search(r'(\d+(?:\.\d+)?)\s*k?\s*[-–to]+\s*(\d+(?:\.\d+)?)\s*k', raw_val, re.IGNORECASE)
            if m1 and not m2:
                stipend_range_str = f"Stipend: {raw_val}"
                u_val = float(m1.group(2).replace(',', ''))
                stipend_upper = u_val / 1000.0 if u_val >= 1000 else u_val
            elif m2:
                stipend_range_str = f"Stipend: {raw_val}"
                stipend_upper = float(m2.group(2))

        for c in result.companies:
            if ctc_upper and (c.CTC_in_LPA is None or c.CTC_in_LPA < ctc_upper):
                c.CTC_in_LPA = ctc_upper
            if stipend_upper and (c.Stipend_in_K is None or c.Stipend_in_K < stipend_upper):
                c.Stipend_in_K = stipend_upper

            comments = c.Comments or ""
            # Strip any accidental MTech mentions from comments
            comments = re.sub(r'(?:m\.?tech|postgraduate)[^|;\n]*', '', comments, flags=re.IGNORECASE).strip(" |;,")

            range_notes = []
            if ctc_range_str and ctc_range_str.lower() not in comments.lower():
                range_notes.append(ctc_range_str)
            if stipend_range_str and stipend_range_str.lower() not in comments.lower():
                range_notes.append(stipend_range_str)

            if range_notes:
                note_str = " | ".join(range_notes)
                c.Comments = f"{comments} | {note_str}".strip(" |") if comments else note_str
            else:
                c.Comments = comments if comments else None

        return result
