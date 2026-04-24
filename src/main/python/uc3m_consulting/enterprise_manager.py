"""Module """
import re
import json

from datetime import datetime, timezone
from freezegun import freeze_time
from uc3m_consulting.enterprise_project import EnterpriseProject
from uc3m_consulting.enterprise_management_exception import EnterpriseManagementException
from uc3m_consulting.enterprise_manager_config import (PROJECTS_STORE_FILE,
                                                       TEST_DOCUMENTS_STORE_FILE,
                                                       TEST_NUMDOCS_STORE_FILE)
from uc3m_consulting.project_document import ProjectDocument

class EnterpriseManager:
    """Class for providing the methods for managing the orders"""
    def __init__(self):
        pass

    def parse_and_validate_date(self, date_str):
        """Shared date validation + parsing"""
        date_pattern = re.compile(r"^(([0-2]\d|3[0-1])\/(0\d|1[0-2])\/\d\d\d\d)$")
        match_result = date_pattern.fullmatch(date_str)
        if not match_result:
            raise EnterpriseManagementException("Invalid date format")

        try:
            return datetime.strptime(date_str, "%d/%m/%Y").date()
        except ValueError as ex:
            raise EnterpriseManagementException("Invalid date format") from ex

    def _load_json_file(self, path):
        try:
            with open(path, "r", encoding="utf-8", newline="") as file:
                return json.load(file)
        except FileNotFoundError as ex:
            raise EnterpriseManagementException("Wrong file  or file path") from ex
        except json.JSONDecodeError as ex:
            raise EnterpriseManagementException("JSON Decode Error - Wrong JSON Format") from ex

    def _write_json_file(self, path, content):
        try:
            with open(path, "w", encoding="utf-8", newline="") as file:
                json.dump(content, file, indent=2)
        except FileNotFoundError as ex:
            raise EnterpriseManagementException("Wrong file  or file path") from ex

    @staticmethod
    def validate_cif(cif: str):
        """validates a cif number """
        if not isinstance(cif, str):
            raise EnterpriseManagementException("CIF code must be a string")
        cif_pattern = re.compile(r"^[ABCDEFGHJKNPQRSUVW]\d{7}[0-9A-J]$")
        if not cif_pattern.fullmatch(cif):
            raise EnterpriseManagementException("Invalid CIF format")

        prefix = cif[0]
        digits = cif[1:8]
        control_digit = cif[8]

        even_sum = 0
        odd_sum = 0

        for i in range(len(digits)):
            if i % 2 == 0:
                doubled = int(digits[i]) * 2
                if doubled > 9:
                    even_sum = even_sum + (doubled // 10) + (doubled % 10)
                else:
                    even_sum = even_sum + doubled
            else:
                odd_sum = odd_sum + int(digits[i])

        total_sum = even_sum + odd_sum
        remainder_digit = total_sum % 10
        calculated_control_value = 10 - remainder_digit

        if calculated_control_value == 10:
            calculated_control_value = 0

        control_letter_map = "JABCDEFGHI"

        if prefix in ('A', 'B', 'E', 'H'):
            if str(calculated_control_value) != control_digit:
                raise EnterpriseManagementException("Invalid CIF character control number")
        elif prefix in ('P', 'Q', 'S', 'K'):
            if control_letter_map[calculated_control_value] != control_digit:
                raise EnterpriseManagementException("Invalid CIF character control letter")
        else:
            raise EnterpriseManagementException("CIF type not supported")
        return True

    def validate_starting_date(self, date_str):
        """validates the  date format  using regex"""
        parsed_date = self.parse_and_validate_date(date_str)
        if parsed_date < datetime.now(timezone.utc).date():
            raise EnterpriseManagementException("Project's date must be today or later.")

        if parsed_date.year < 2025 or parsed_date.year > 2050:
            raise EnterpriseManagementException("Invalid date format")
        return date_str
    #pylint: disable=too-many-arguments, too-many-positional-arguments
    def register_project(self,
                         company_cif: str,
                         project_acronym: str,
                         project_description: str,
                         department: str,
                         date: str,
                         budget: str):
        """registers a new project"""
        self.validate_cif(company_cif)
        acronym_pattern = re.compile(r"^[a-zA-Z0-9]{5,10}")
        match_result = acronym_pattern.fullmatch(project_acronym)
        if not re.fullmatch(r"^[a-zA-Z0-9]{5,10}", project_acronym):
            raise EnterpriseManagementException("Invalid acronym")

        if not re.fullmatch(r"^.{10,30}$", project_description):
            raise EnterpriseManagementException("Invalid description format")

        if not re.fullmatch(r"(HR|FINANCE|LEGAL|LOGISTICS)", department):
            raise EnterpriseManagementException("Invalid department")
        self.validate_starting_date(date)

        try:
            budget_float  = float(budget)
        except ValueError as exc:
            raise EnterpriseManagementException("Invalid budget amount") from exc

        budget_str = str(budget_float)
        if '.' in budget_str:
            decimal_places = len(budget_str.split('.')[1])
            if decimal_places > 2:
                raise EnterpriseManagementException("Invalid budget amount")

        if budget_float < 50000 or budget_float > 1000000:
            raise EnterpriseManagementException("Invalid budget amount")


        new_project = EnterpriseProject(company_cif=company_cif,
                                        project_acronym=project_acronym,
                                        project_description=project_description,
                                        department=department,
                                        starting_date=date,
                                        project_budget=budget)

        try:
            with open(PROJECTS_STORE_FILE, "r", encoding="utf-8", newline="") as file:
                project_list = json.load(file)
        except FileNotFoundError:
            project_list = []
        except json.JSONDecodeError as error:
            raise EnterpriseManagementException("JSON Decode Error - Wrong JSON Format") from ex

        for existing_project in project_list:
            if existing_project == new_project.to_json():
                raise EnterpriseManagementException("Duplicated project in projects list")

        project_list.append(new_project.to_json())

        self._write_json_file(PROJECTS_STORE_FILE, project_list)
        return new_project.project_id

    def _process_document_entry(self, document_entry, date_str):
        timestamp_value = document_entry["register_date"]

        formatted_doc_date = datetime.fromtimestamp(timestamp_value).strftime("%d/%m/%Y")

        if formatted_doc_date != date_str:
            return 0

        frozen_date = datetime.fromtimestamp(timestamp_value, tz=timezone.utc)

        with freeze_time(frozen_date):
            p = ProjectDocument(document_entry["project_id"], document_entry["file_name"])

            if p.document_signature != document_entry["document_signature"]:
                raise EnterpriseManagementException("Inconsistent document signature")

        return 1
    def find_docs(self, date_str):
        """
        Generates a JSON report counting valid documents for a specific date.

        Checks cryptographic hashes and timestamps to ensure historical data integrity.
        Saves the output to 'resultado.json'.

        Args:
            date_str (str): date to query.

        Returns:
            number of documents found if report is successfully generated and saved.

        Raises:
            EnterpriseManagementException: On invalid date, file IO errors,
                missing data, or cryptographic integrity failure.
        """
        self.parse_and_validate_date(date_str)

        documents_list = self._load_json_file(TEST_DOCUMENTS_STORE_FILE)

        result_count = 0

        for document_entry in documents_list:
            result_count += self._process_document_entry(document_entry, date_str)

        if result_count == 0:
            raise EnterpriseManagementException("No documents found")
        # prepare json text
        now_str = datetime.now(timezone.utc).timestamp()
        report_entry  = {"Querydate":  date_str,
             "ReportDate": now_str,
             "Numfiles": result_count
             }

        try:
            report_list = self._load_json_file(TEST_NUMDOCS_STORE_FILE)
        except EnterpriseManagementException as ex:
            if "Wrong file" in str(ex):
                report_list = []
            else:
                raise

        report_list.append(report_entry)

        self._write_json_file(TEST_NUMDOCS_STORE_FILE, report_list)
        return result_count
