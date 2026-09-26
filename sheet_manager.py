import os
import openpyxl
from company_matcher import CompanyMatcher
from student_lookup import StudentLookup

class SheetManager:
    def __init__(self, excel_path=None, google_sheet_credentials=None, google_sheet_url=None):
        self.excel_path = excel_path or r"C:\Users\DELL\Downloads\2027 unoff stats (1).xlsx"
        self.google_sheet_credentials = google_sheet_credentials
        self.google_sheet_url = google_sheet_url
        self.use_google_sheets = False
        self.gspread_client = None
        self.spreadsheet = None
        self._company_matcher = None
        self._student_lookup = None

    def _connect(self):
        if self.spreadsheet:
            return
        if self.google_sheet_credentials:
            try:
                import gspread
                import json
                if os.path.exists(self.google_sheet_credentials):
                    self.gspread_client = gspread.service_account(filename=self.google_sheet_credentials)
                elif self.google_sheet_credentials.strip().startswith("{"):
                    creds_dict = json.loads(self.google_sheet_credentials)
                    self.gspread_client = gspread.service_account_from_dict(creds_dict)
                if self.gspread_client and self.google_sheet_url:
                    self.spreadsheet = self.gspread_client.open_by_key(self.google_sheet_url) if "/" not in self.google_sheet_url else self.gspread_client.open_by_url(self.google_sheet_url)
                    self.use_google_sheets = True
                    print("Connected to Google Sheets successfully!")
            except Exception as e:
                print("Failed to initialize Google Sheets, falling back to local Excel mode:", e)

    @property
    def company_matcher(self):
        if self._company_matcher is None:
            self.refresh_company_matcher()
        return self._company_matcher

    @property
    def student_lookup(self):
        if self._student_lookup is None:
            self.refresh_student_lookup()
        return self._student_lookup

    def refresh_company_matcher(self):
        self._connect()
        if self.use_google_sheets and self.spreadsheet:
            try:
                comp_ws = self.spreadsheet.worksheet("Companies")
                self._company_matcher = CompanyMatcher(gspread_worksheet=comp_ws)
                return
            except Exception as e:
                print("Error loading company matcher from Google Sheets:", e)
        self._company_matcher = CompanyMatcher(excel_path=self.excel_path)

    def refresh_student_lookup(self):
        self._connect()
        if self.use_google_sheets and self.spreadsheet:
            try:
                master_ws = self.spreadsheet.worksheet("CGPA_Master")
                self._student_lookup = StudentLookup(gspread_worksheet=master_ws)
                return
            except Exception as e:
                print("Error loading student lookup from Google Sheets:", e)
        self._student_lookup = StudentLookup(excel_path=self.excel_path)

    def refresh_matchers(self):
        self.refresh_company_matcher()
        self.refresh_student_lookup()

    def append_company_record(self, company_dict: dict) -> dict:
        """
        Appends a Company record into Companies sheet.
        Replaces company name with exact matching name from Companies sheet if present.
        """
        raw_company = company_dict.get('Company', '').strip()
        exact_company_name = self.company_matcher.get_exact_company_name(raw_company)

        # CGPA criteria defaults to 0.0 if not specified
        cgpa_crit = company_dict.get('CGPA_criteria')
        if cgpa_crit is None or str(cgpa_crit).strip().lower() in ['', 'none', 'null', 'nan']:
            cgpa_crit = 0.0

        # If role missing in company announcement, check if company already exists in Companies sheet
        role = company_dict.get('Role')
        if not role or str(role).strip().lower() in ['', 'none', 'null', 'nan']:
            existing_roles = self.company_matcher.find_roles_for_company(exact_company_name)
            role = existing_roles[0] if existing_roles else ""

        row_data = [
            exact_company_name,
            cgpa_crit,
            company_dict.get('Offer_Type', 'FTE'),
            role,
            company_dict.get('Count'),
            company_dict.get('CTC_in_LPA'),
            company_dict.get('Base_in_LPA'),
            company_dict.get('Stipend_in_K'),
            company_dict.get('Category', 'TECH'),
            company_dict.get('Comments', '')
        ]

        if self.use_google_sheets:
            sheet = self.spreadsheet.worksheet("Companies")
            sheet.append_row(row_data)
        else:
            wb = openpyxl.load_workbook(self.excel_path)
            ws = wb['Companies']
            ws.append(row_data)
            wb.save(self.excel_path)
            wb.close()

        self.refresh_matchers()
        processed = dict(company_dict)
        processed['Company'] = exact_company_name
        processed['CGPA_criteria'] = cgpa_crit
        processed['Role'] = role
        return processed

    def append_student_record(self, student_dict: dict) -> dict:
        """
        Appends a Student record into Students sheet.
        Ignores roll numbers starting with '25/'.
        Appends ONLY [Roll No, Name, Company, Role, Offer Type].
        """
        # 1. CGPA_Master Roll No / Name Auto-Lookup & Enrichment
        enriched = self.student_lookup.enrich_student_data(
            input_roll=student_dict.get('Roll_No', ''),
            input_name=student_dict.get('Name', '')
        )

        roll_no = enriched.get('Roll No', '').strip().upper()
        name = enriched.get('Name', '').strip().upper()

        # Check rule: Ignore roll numbers starting with 25/
        if roll_no.startswith("25/"):
            print(f"Skipping student {name} ({roll_no}) because roll number starts with 25/")
            return None

        raw_company = student_dict.get('Company', '').strip()
        exact_company_name = self.company_matcher.get_exact_company_name(raw_company)

        # 2. Dynamic Role Auto-Fetch from Companies Sheet
        role = student_dict.get('Role')
        if not role or str(role).strip().lower() in ['', 'none', 'null', 'nan', 'auto-fetch']:
            existing_roles = self.company_matcher.find_roles_for_company(exact_company_name)
            if existing_roles:
                role = existing_roles[0]  # Auto-fetch exact registered role from Companies sheet!
            else:
                role = ""  # Leave empty if company not found in Companies sheet yet

        offer_type = student_dict.get('Offer_Type', 'FTE') or 'FTE'

        row_data = [
            roll_no,
            name,
            None,                # CGPA (Auto-filled by ArrayFormula)
            exact_company_name,  # Exact Company Name matching Companies sheet!
            role,                # Exact Role matching Companies sheet!
            offer_type,
            None,                # Stipend (Auto-filled by ArrayFormula XLOOKUP)
            None,                # CTC (Auto-filled by ArrayFormula XLOOKUP)
            None,                # Base (Auto-filled by ArrayFormula XLOOKUP)
            None,                # Category (Auto-filled by ArrayFormula XLOOKUP)
            None,                # Branch (Auto-filled by Formula)
            None                 # Count (Auto-filled by ArrayFormula)
        ]

        if self.use_google_sheets:
            sheet = self.spreadsheet.worksheet("Students")
            sheet.append_row(row_data)
        else:
            wb = openpyxl.load_workbook(self.excel_path)
            ws = wb['Students']
            ws.append(row_data)
            wb.save(self.excel_path)
            wb.close()

        return {
            'Roll_No': roll_no,
            'Name': name,
            'Company': exact_company_name,
            'Role': role,
            'Offer_Type': offer_type
        }
