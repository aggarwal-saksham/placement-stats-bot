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
      "Company": "Company Name (use standard clean company name e.g. Thorogood Associates, WWT)",
      "CGPA_criteria": 7.5 (float, default to 0.0 if not specified),
      "Offer_Type": "6M + PPO" | "6M + FTE" | "FTE" | "PPO",
      "Role": "Job Title (e.g. Data and AI Consultant)",
      "Count": null (float or null),
      "CTC_in_LPA": 14.8 (float or null, higher if range given),
      "Base_in_LPA": null (float or null),
      "Stipend_in_K": 45.0 (float in thousands or null e.g. 45.0 for 45k/month),
      "Category": "TECH" | "NON TECH" | "CORE",
      "Comments": "Location / Breakdown notes or null"
    }
  ],
  "students": [
    {
      "Roll_No": "23/IT/145" (or null if unstated),
      "Name": "Student Name" (or null if unstated),
      "Company": "Company Name",
      "Role": "Job Title" (or null if unstated),
      "Offer_Type": "6M + PPO" | "6M + FTE" | "FTE" | "PPO"
    }
  ]
}

### CRITICAL PARSING RULES:
1. **BTECH ONLY**: Always extract the **BTech** CGPA Cutoff if separate BTech and MTech cutoffs are given (e.g. "CGPA CUTOFF : 7.5 (BTech) / 7 (MTech)" -> 7.5). Ignore MTech criteria completely.
2. **DEFAULT CGPA CUTOFF**: If CGPA cutoff is not stated in the message, set `"CGPA_criteria": 0.0`.
3. **Multi-Role Companies**: If a company announcement lists multiple roles (e.g. Software Engineer AND Data Analyst), CREATE SEPARATE COMPANY OBJECTS IN THE ARRAY FOR EACH ROLE with identical CTC/stipend details.
4. **Category**:
   - `NON TECH`: Data Analyst, DA, Business Analyst, Analyst, Consultant, Product Analyst, Operations, Finance, Data and AI Consultant, etc.
   - `TECH`: SDE, SWE, Software Engineer, MLE, Data Science Engineer, Data Scientist, Frontend, Backend, Full Stack, DevOps, Product Engineer, etc.
   - `CORE`: Mechanical, Civil, Electrical, Electronics, VLSI, Embedded, GET, Chemical, etc.
5. Return ONLY valid JSON adhering strictly to the above format.
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
            "gemini-2.5-flash",
            "gemini-2.0-flash",
            "gemini-flash-lite-latest",
            "gemini-flash-latest",
            "gemini-3.6-flash"
        ]
        last_error = None

        # Try API calls with retry handling for rate limits
        for current_key in self.api_keys:
            try:
                from google import genai
                from google.genai import types
                client = genai.Client(api_key=current_key)
                
                for m_name in candidate_models:
                    for attempt in range(2):
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
                                break
                        except Exception as ex:
                            last_error = ex
                            if "429" in str(ex) or "Quota" in str(ex):
                                time.sleep(1)
                                continue
                            break
                    if raw_json_str:
                        break
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
                                break
                        except Exception as ex:
                            last_error = ex
                            continue
                    if raw_json_str:
                        break
                except Exception:
                    pass

        if not raw_json_str:
            raise RuntimeError(f"Gemini API Error: {last_error}")

        # Clean JSON markdown if any
        clean_str = re.sub(r'^```json\s*', '', raw_json_str.strip())
        clean_str = re.sub(r'\s*```$', '', clean_str)

        data = json.loads(clean_str)
        return PlacementParseResult.model_validate(data)
