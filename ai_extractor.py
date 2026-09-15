import os
import json
import re
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional

class CompanyRecord(BaseModel):
    Company: str
    CGPA_criteria: Optional[float] = None
    Offer_Type: Optional[str] = "FTE"
    Role: Optional[str] = None
    Count: Optional[float] = None
    CTC_in_LPA: Optional[float] = None
    Base_in_LPA: Optional[float] = None
    Stipend_in_K: Optional[float] = None
    Category: Optional[str] = "TECH"
    Comments: Optional[str] = None

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
      "Company": "Company Name (use standard abbreviations e.g. WWT)",
      "CGPA_criteria": 7.5 (float or null),
      "Offer_Type": "6M + PPO" | "6M + FTE" | "FTE" | "PPO",
      "Role": "Job Title (or null if unstated)",
      "Count": null (float or null),
      "CTC_in_LPA": 23.0 (float or null, higher if range given),
      "Base_in_LPA": 17.0 (float or null),
      "Stipend_in_K": 110.0 (float in thousands or null e.g. 110.0 for Rs 1,10,000),
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

### CRITICAL RULES:
1. **Multi-Role Companies**: If a company announcement lists multiple roles (e.g. Software Engineer AND Data Analyst), CREATE SEPARATE COMPANY OBJECTS IN THE ARRAY FOR EACH ROLE with identical CTC/stipend details.
2. **Category**:
   - `NON TECH`: Data Analyst, DA, Business Analyst, Analyst, Consultant, Product Analyst, Operations, Finance, etc.
   - `TECH`: SDE, SWE, Software Engineer, MLE, Data Science, Frontend, Backend, Full Stack, DevOps, Product Engineer, etc.
   - `CORE`: Mechanical, Civil, Electrical, Electronics, VLSI, Embedded, GET, Chemical, etc.
3. Return ONLY valid JSON adhering strictly to the above format.
"""

class AIExtractor:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")

    def parse_message(self, text: str) -> PlacementParseResult:
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is missing! Please set GEMINI_API_KEY environment variable or in config.py.")

        raw_json_str = ""
        candidate_models = [
            "gemini-2.5-flash",
            "gemini-flash-latest",
            "gemini-3.6-flash",
            "gemini-2.0-flash",
            "gemini-2.5-pro"
        ]
        last_error = None

        # 1. Try google.genai SDK (New Google GenAI SDK)
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=self.api_key)
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
                        break
                except Exception as ex:
                    last_error = ex
                    continue
        except Exception as e1:
            last_error = e1

        # 2. Try google.generativeai SDK (Legacy SDK fallback)
        if not raw_json_str:
            try:
                import google.generativeai as genai_old
                genai_old.configure(api_key=self.api_key)
                for m_name in ["gemini-2.5-flash", "gemini-flash-latest", "gemini-3.6-flash"]:
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
            except ImportError:
                pass
            except Exception as e2:
                last_error = e2

        if not raw_json_str:
            raise RuntimeError(f"Failed to call Gemini API across models: {last_error}")

        # Clean JSON markdown if any
        clean_str = re.sub(r'^```json\s*', '', raw_json_str.strip())
        clean_str = re.sub(r'\s*```$', '', clean_str)

        data = json.loads(clean_str)
        return PlacementParseResult.model_validate(data)
