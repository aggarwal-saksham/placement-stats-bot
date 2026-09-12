import os
import sys

# Ensure UTF-8 stdout encoding on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

from ai_extractor import AIExtractor
from sheet_manager import SheetManager
from config import GEMINI_API_KEY, DEFAULT_LOCAL_EXCEL_PATH, GOOGLE_SHEETS_CREDENTIALS_PATH, GOOGLE_SHEET_ID_OR_URL

def run_test_cli():
    print("=" * 60)
    print("PLACEMENT STATS AUTOMATION - LOCAL TEST RUNNER")
    print("=" * 60)

    api_key = os.getenv("GEMINI_API_KEY") or GEMINI_API_KEY
    if not api_key:
        print("GEMINI_API_KEY is required to test AI parsing.")
        print("Please set GEMINI_API_KEY in .env or environment variables.")
        return

    sheet_mgr = SheetManager(
        excel_path=DEFAULT_LOCAL_EXCEL_PATH,
        google_sheet_credentials=GOOGLE_SHEETS_CREDENTIALS_PATH,
        google_sheet_url=GOOGLE_SHEET_ID_OR_URL
    )
    ai_extractor = AIExtractor(api_key=api_key)

    mode = "Google Sheets (Live)" if sheet_mgr.use_google_sheets else "Local Excel"
    print(f"\nSystem initialized! Mode: [{mode}]")
    print(f"Loaded {len(sheet_mgr.company_matcher.unique_company_names)} companies from Companies sheet.")
    print(f"Loaded {len(sheet_mgr.student_lookup.students)} student records from CGPA_Master sheet.")

    sample_company_msg = """
    World wide Technology is visiting for 2027 batch.
    Roles: Software Engineer and Data Analyst
    CGPA Cutoff: 7.5
    Offer Type: 6M + PPO
    Stipend: Rs 1,10,000 / month
    CTC: 23 LPA (17 Base)
    Category: TECH
    Location: Gurugram
    """

    sample_student_msg = """
    Placements Update:
    NAVI selected 4 students for Data Analyst role:
    1. 23/IT/145 SAKSHAM AGGARWAL (6M + PPO)
    2. Saksham Sapra (23/IT/147) - UnifyApps Product Engineer
    """

    print("\n------------------------------------------------------------")
    print("TEST 1: COMPANY ANNOUNCEMENT PARSING & SYNC")
    print("------------------------------------------------------------")
    print("Input Text:", sample_company_msg.strip())
    
    parsed_co = ai_extractor.parse_message(sample_company_msg)
    print(f"\nMessage Type: {parsed_co.message_type}")
    print(f"Extracted Companies ({len(parsed_co.companies)} records for multiple roles):")
    for c in parsed_co.companies:
        print("  ", c.model_dump())
        processed = sheet_mgr.append_company_record(c.model_dump())
        print(f"  [SUCCESS] Appended to {mode} -> Exact Company Name:", processed['Company'])

    print("\n------------------------------------------------------------")
    print("TEST 2: STUDENT PLACEMENT PARSING & CGPA_MASTER LOOKUP SYNC")
    print("------------------------------------------------------------")
    print("Input Text:", sample_student_msg.strip())

    parsed_st = ai_extractor.parse_message(sample_student_msg)
    print(f"\nMessage Type: {parsed_st.message_type}")
    print(f"Extracted Students ({len(parsed_st.students)} records):")
    for s in parsed_st.students:
        print("  Raw AI Extract:", s.model_dump())
        processed = sheet_mgr.append_student_record(s.model_dump())
        print(f"  [SUCCESS] Appended to {mode} -> Enriched Roll & Name:", processed)

    print(f"\nLOCAL TEST COMPLETE! Synced to {mode}.")

if __name__ == "__main__":
    run_test_cli()
