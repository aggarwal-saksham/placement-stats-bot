import os
import openpyxl
from company_matcher import CompanyMatcher
from student_lookup import StudentLookup

class SheetManager:
    def __init__(self, excel_path=None, google_sheet_credentials=None, google_sheet_url=None):
        self.excel_path = excel_path or r"C:\Users\DELL\Downloads\2027 unoff stats (1).xlsx"
        self.company_matcher = CompanyMatcher(self.excel_path)
        self.student_lookup = StudentLookup(self.excel_path)
        self.use_google_sheets = False
        self.gspread_client = None
        self.spreadsheet = None

        if google_sheet_credentials and os.path.exists(google_sheet_credentials):
            try:
                import gspread
                self.gspread_client = gspread.service_account(filename=google_sheet_credentials)
                if google_sheet_url:
                    self.spreadsheet = self.gspread_client.open_by_key(google_sheet_url) if "/" not in google_sheet_url else self.gspread_client.open_by_url(google_sheet_url)
                    self.use_google_sheets = True
                    print("Connected to Google Sheets successfully!")
            except Exception as e:
                print("Failed to initialize Google Sheets, falling back to local Excel mode:", e)

    def refresh_matchers(self):
        """Reload matchers from current spreadsheet/excel data."""
        self.company_matcher = CompanyMatcher(self.excel_path)
        self.student_lookup = StudentLookup(self.excel_path)

    def append_company_record(self, company_dict: dict) -> dict:
        """
        Appends a Company record into Companies sheet.
        Replaces company name with exact matching name from Companies sheet if present.
        """
        raw_company = company_dict.get('Company', '').strip()
        exact_company_name = self.company_matcher.get_exact_company_name(raw_company)

        row_data = [
            exact_company_name,
            company_dict.get('CGPA_criteria'),
            company_dict.get('Offer_Type', 'FTE'),
            company_dict.get('Role', ''),
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
        return processed

    def append_student_record(self, student_dict: dict) -> dict:
        """
        Appends a Student record into Students sheet.
        Replaces Company name with EXACT matching string from Companies sheet so XLOOKUP works 100%.
        Appends ONLY [Roll No, Name, Company, Role, Offer Type].
        Leaves CGPA, Stipend, CTC, Base, Category, Branch, Count BLANK for ArrayFormulas to calculate.
        """
        raw_company = student_dict.get('Company', '').strip()
        # Strictly match exact string present in Companies sheet
        exact_company_name = self.company_matcher.get_exact_company_name(raw_company)

        # 1. Role Fallback: If role missing, check Companies sheet for single matching role
        role = student_dict.get('Role')
        if not role or str(role).lower() in ['none', 'null', 'nan', 'auto-fetch']:
            existing_roles = self.company_matcher.find_roles_for_company(exact_company_name)
            if len(existing_roles) >= 1:
                role = existing_roles[0]  # Auto-fill single/primary registered role from Companies sheet
            else:
                role = "Software Engineer"  # Default fallback if company not found in sheet yet

        # 2. CGPA_Master Roll No / Name Auto-Lookup
        enriched = self.student_lookup.enrich_student_data(
            input_roll=student_dict.get('Roll_No', ''),
            input_name=student_dict.get('Name', '')
        )

        roll_no = enriched.get('Roll No', '')
        name = enriched.get('Name', '')
        offer_type = student_dict.get('Offer_Type', 'FTE')

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
