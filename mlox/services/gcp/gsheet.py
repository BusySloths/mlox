"""Functions to handle google spreadsheets.

Resources:
    - GSheet API limitations:
        https://developers.google.com/sheets/api/limits#quota
        "Google recommends a 2-MB maximum payload. "
        Read requests
            Per minute per project 	300
            Per minute per user per project 	60
        Write requests
            Per minute per project 	300
            Per minute per user per project 	60

Nomenclature:
    A _spreadsheet_ is a whole google spreadsheet document containing one or
    more _worksheets_.

Author: nicococo | mlox
"""

import sys
import time
import math
import logging
import pandas as pd
import numpy as np

from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple

import gspread
import gspread.utils as gspread_utils

from google.oauth2.service_account import Credentials

from mlox.services.gcp.secret_manager import (
    load_secret_from_gcp,
    dict_to_service_account_credentials,
)

# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

GOOGLE_SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# These are Google Sheets API hard limits
GOOGLE_SHEETS_API_MAX_CELLS = 10000000
GOOGLE_SHEETS_API_MAX_NEW_ROWS = 40000
GOOGLE_SHEETS_API_MAX_COLS = 18278
GOOGLE_SHEETS_API_MAX_PAYLOAD = (
    2 * 1024 * 1024
)  # "Google recommends a 2-MB maximum payload. "
GOOGLE_SHEETS_API_MAX_WORKSHEETS = 200
GOOGLE_SHEETS_API_MAX_READ_USER_PER_MIN_PER_PROJECT = 60
GOOGLE_SHEETS_API_MAX_WRITE_USER_PER_MIN_PER_PROJECT = 60

# These are our limits
MAX_WRITE_ROWS = 20000


@dataclass
class GCPSheets:
    keyfile_dict: Dict = field(default_factory=dict, init=True)
    _project_id: str = field(default="", init=False)
    _credentials: Credentials | None = field(default=None, init=False)

    def __post_init__(self):
        base_credentials = dict_to_service_account_credentials(self.keyfile_dict)
        self._credentials = base_credentials.with_scopes(GOOGLE_SHEETS_SCOPES)
        self._project_id = self.keyfile_dict.get("project_id", "")

    def _get_spreadsheet(self, gname: str) -> gspread.Spreadsheet | None:
        if not self._credentials:
            return None
        file = gspread.authorize(self._credentials)
        sheet = None
        try:
            if gname.startswith("http"):
                sheet = file.open_by_url(gname)
            else:
                sheet = file.open(gname)
        except BaseException as e:
            logger.warning(f"Could not open spreadsheet {gname} due to {str(e)}.")
        return sheet

    def _get_worksheet(self, gname: str, sheet_name: str) -> gspread.Worksheet | None:
        """Open a google spreadsheet and load the worksheet with name 'sheet_name'. For access
            service account Credentialss with gsheet roles are neccessary.

        Args:
            gname (str): Name of the google spreadsheet or link to the spreadsheet (gname must start with 'http' for this).
                        Sheet must be shared with the service account email as provided
                        in the service account Credentials dict.
            sheet_name (str): worksheet name (google default is 'Sheet1')

        Returns:
            [gspread.Worksheet]: worksheet (or None if not found)
        """
        spreadsheet = self._get_spreadsheet(gname)
        if spreadsheet is None:
            return None
        return spreadsheet.worksheet(sheet_name)

    def create_spreadsheet(
        self,
        gname: str,
        share_emails_writer: Optional[List[str]] = None,
        share_emails_reader: Optional[List[str]] = None,
    ) -> gspread.Spreadsheet | None:
        """Create a new google spreadsheet. For access
        service account Credentialss with gsheet roles are neccessary.
        """
        if not self._credentials:
            return None
        file = gspread.authorize(self._credentials)
        sheet = file.create(gname)
        if share_emails_writer is not None:
            for email in share_emails_writer:
                sheet.share(email, perm_type="user", role="writer")
        if share_emails_reader is not None:
            for email in share_emails_reader:
                sheet.share(email, perm_type="user", role="reader")
        return sheet

    def exists_spreadsheet(self, gname: str) -> bool:
        """Check if a google spreadsheet exists. For access
            service account Credentialss with gsheet roles are neccessary.

        Args:
            gname (str): Name of the google spreadsheet.
        Returns:
            [bool]: Does the spreadsheet exist?
        """
        sheet = self._get_spreadsheet(gname)
        return sheet is not None

    def share_spreadsheet(
        self,
        gname: str,
        emails_read_only: Optional[List[str]],
        emails_write: Optional[List[str]],
        msg: str | None = None,
    ) -> None:
        """Share spreadsheets with other account. Choose between read-only and read/write access. For access
            service account Credentialss with gsheet roles are neccessary.

        Args:
            gname (str): Name of the google spreadsheet.
            emails_read_only (List): (Optional) List of emails to share the document for read-only purposes
            emails_write (List): (Optional) List of emails to share the document for read/write purposes
            msg (str): (Optional) Notification message
        """
        sheet = self._get_spreadsheet(gname)
        if sheet and emails_read_only is not None:
            for email in emails_read_only:
                sheet.share(email, perm_type="user", role="reader", email_message=msg)
        if sheet and emails_write is not None:
            for email in emails_write:
                sheet.share(email, perm_type="user", role="writer", email_message=msg)

    def exists_worksheet(self, gname: str, sheet_name: str) -> bool:
        """Check if a worksheet in an existing google spreadsheet exists. For access
            service account Credentialss with gsheet roles are neccessary.

        Args:
            gname (str): Name/URL of the google spreadsheet.
            sheet_name (str): The worksheet name to test
        Returns:
            [bool]: Does the worksheet exist?
        """
        sheet_names = self.get_worksheet_names(gname)
        return sheet_name in sheet_names

    def whats_my_email_again(self) -> str:
        if not self._credentials:
            return ""
        email = self._credentials.service_account_email
        logger.info(
            f"Your Gsheet service account email is {email}. Use this address to share your spreadsheets with."
        )
        return email

    def extract_id_from_url(self, gsheet_url: str) -> str:
        return gspread_utils.extract_id_from_url(gsheet_url)

    def get_worksheet_names(self, gname: str) -> List[str]:
        sheet = self._get_spreadsheet(gname)
        if sheet is None:
            return list()
        return [sheet.title for sheet in sheet.worksheets()]

    def get_spreadsheet_url_from_name(self, name: str) -> str:
        sheet = self._get_spreadsheet(name)
        if sheet is None:
            return ""
        return sheet.url

    def add_worksheet(self, gname: str, sheet: str) -> None:
        spreadsheet = self._get_spreadsheet(gname)
        if spreadsheet:
            spreadsheet.add_worksheet(title=sheet, rows=0, cols=0)

    def remove_worksheet(self, gname: str, sheet: str) -> None:
        worksheet = self._get_worksheet(gname, sheet)
        spreadsheet = self._get_spreadsheet(gname)
        if spreadsheet and worksheet:
            spreadsheet.del_worksheet(worksheet)

    def rename_worksheet(self, gname: str, sheet: str, new_title: str) -> None:
        worksheet = self._get_worksheet(gname, sheet)
        if worksheet:
            worksheet.update_title(new_title)

    def copy_worksheet(
        self, src_gname: str, src_sheet: str, target_gname: str
    ) -> str | None:
        worksheet = self._get_worksheet(src_gname, src_sheet)
        if worksheet is None:
            return None
        id = self.extract_id_from_url(target_gname)
        res = worksheet.copy_to(id)
        return res["title"]

    def read_worksheet(
        self, gname: str, sheet_name: str, empty_cells_to_nan: bool = True
    ) -> pd.DataFrame:
        worksheet = self._get_worksheet(gname, sheet_name)
        if worksheet is None:
            return pd.DataFrame()
        # Difference: get_all_records returns a dict while get_all_values return list-of-list direct from api
        # Problem: unexpected behavior of get_all_records in >5.2.0 version (cannot cope with multiple empty headers anymore)
        # df = pd.DataFrame(worksheet.get_all_records())
        all_values = worksheet.get_all_values()
        df = pd.DataFrame(all_values[1:], columns=all_values[0])
        if empty_cells_to_nan:
            df = df.replace("", pd.NA)
            # df = df.replace('^$|None', pd.NA, regex=True)
        return df

    def write_worksheet(
        self,
        gname: str,
        sheet_name: str,
        df: pd.DataFrame,
        format_header: bool = True,
    ) -> None:
        has_sheet = any(
            [name == sheet_name for name in self.get_worksheet_names(gname)]
        )
        if not has_sheet:
            logger.info(
                f"Worksheet {sheet_name} does not exist. Creating new worksheet."
            )
            self.add_worksheet(gname, sheet_name)
        worksheet = self._get_worksheet(gname, sheet_name)
        if worksheet is None:
            return
        worksheet.clear()
        end_col = self.int2a1(len(df.columns) - 1)
        logger.info(
            f"Column size in data frame is {len(df.columns)} which corresponds to column name '{end_col}'."
        )

        inc = MAX_WRITE_ROWS
        parts = int(np.ceil(df.shape[0] / inc))
        start = 0
        for i in range(parts):
            end = int(np.min([start + inc, df.shape[0]]))
            df_part = df.iloc[start:end]
            logger.info(
                f"Writing part {i + 1} of {parts} in gsheet {gname}. Position {start}-{end}."
            )
            if i == 0:
                worksheet.update(
                    [df.columns.values.tolist()] + df_part.fillna("").values.tolist()
                )
            else:
                worksheet.update(
                    f"A{start}:{end_col}{end}", df_part.fillna("").values.tolist()
                )
            start += inc
            time.sleep(1)
        if format_header:
            fmt = {
                "backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9},
                "horizontalAlignment": "CENTER",
                "textFormat": {
                    "foregroundColor": {"red": 0.0, "green": 0.0, "blue": 0.0},
                    "fontSize": 11,
                    "bold": True,
                },
            }
            worksheet.format(f"A1:{end_col}1", fmt)
            # worksheet.columns_auto_resize(0, df.shape[1])

    def int2a1(self, number: int) -> str:
        out = ""
        while number >= 0:
            out = f"{chr(65 + (number % 26))}{out}"
            number = math.floor(number / 26) - 1
        return out

    def format_worksheet(
        self, gname: str, sheet_name: str, fmts: List[Tuple[str, Dict]]
    ) -> None:
        worksheet = self._get_worksheet(gname, sheet_name)
        if not worksheet:
            return
        formats = list()
        for area, fmt in fmts:
            props = {}
            if "width" in fmt:
                width = fmt.pop("width")
                props["column_size_px"] = width
            if "height" in fmt:
                height = fmt.pop("height")
                props["row_size_px"] = height
            if len(fmt) > 0:
                props.update(fmt)  # Merge other formatting options

            if props:
                # formats.append({"range": area, "format": props})
                format = gspread.worksheet.CellFormat(range=area, format=props)
                formats.append(format)
        try:
            if formats:
                worksheet.batch_format(formats)
            # No longer auto-resize, as we handle width manually
            # worksheet.columns_auto_resize(0, worksheet.col_count)
        except Exception as e:
            logger.error(f"Error applying formats: {e}")
            # Depending on your needs, you might want to re-raise or handle differently

    def update_entry_in_worksheet(
        self,
        gname: str,
        sheet_name: str,
        df: pd.DataFrame,
        query: str,
        col_name: str,
    ) -> None:
        worksheet = self._get_worksheet(gname, sheet_name)
        if worksheet is None:
            return
        ind = df.columns.to_list().index(col_name)
        cell = worksheet.find(query, in_column=ind + 1)
        if cell is not None:
            row = cell.row
            end_col = self.int2a1(len(df.columns) - 1)
            worksheet.update(f"A{row}:{end_col}{row}", df.fillna("").values.tolist())

    def append_to_worksheet(
        self, gname: str, sheet_name: str, df: pd.DataFrame
    ) -> None:
        worksheet = self._get_worksheet(gname, sheet_name)
        if worksheet is None:
            return
        num_rows = df.shape[0]

        inc = MAX_WRITE_ROWS
        parts = int(np.ceil(num_rows / inc))
        start = 0
        for i in range(parts):
            end = int(np.min([start + inc, df.shape[0]]))
            df_part = df.iloc[start:end]
            worksheet.append_rows(
                df_part.fillna("").values.tolist(),
                value_input_option=gspread.utils.ValueInputOption.user_entered,
            )
            start += inc
            time.sleep(0.5)

    def write_multiple_worksheets(
        self, gname: str, sheets: Dict[str, pd.DataFrame]
    ) -> None:
        for sheet_name in sheets:
            self.write_worksheet(gname, sheet_name, sheets[sheet_name])

    def export_as_excel(self, gname: str, path: str, output_name: str) -> None:
        sheets = self.get_worksheet_names(gname)
        with pd.ExcelWriter(
            f"{path}/{output_name}.xlsx", engine="xlsxwriter"
        ) as writer:
            for sheet_name in sheets:
                sheet = self.read_worksheet(gname, sheet_name)
                sheet.to_excel(writer, sheet_name=sheet_name, index=False)

    def list_spreadsheets(self) -> List:
        """Returns the names and ids of files the service account has access to.
            Paginated.
        Args:
            creds (Credentials) : OAuth Credentialss
        Returns:
            [List]: list of files and properties
        """
        if not self._credentials:
            return list()
        client = gspread.authorize(
            self._credentials
        )  # authenticate the JSON key with gspread
        return client.list_spreadsheet_files()
        # Alternative using drive API:
        # return list_files(
        #     creds,
        #     mimeType="application/vnd.google-apps.spreadsheet",
        #     fields=["id", "name", "size", "modifiedTime", "createdTime"],
        # )

    def get_last_update_time(self, gname: str) -> Tuple[datetime, str, str]:
        gsheet = self._get_spreadsheet(gname)
        if gsheet is None:
            return datetime.now(), "", ""
        # return datetime.fromisoformat(gsheet.lastUpdateTime[:-1] + '+00:00')
        return (
            datetime.fromisoformat(gsheet.lastUpdateTime[:-1]),
            gsheet.id,
            gsheet.title,
        )

    def get_a1_from_column_name(
        self, gname: str, sheet_name: str, column_name: str
    ) -> str | None:
        sheet = self._get_worksheet(gname, sheet_name)
        if sheet is None:
            return None
        values = sheet.get_values("1:1")[0]
        idx = -1
        try:
            idx = values.index(column_name)
        except Exception as e:
            return None
        res = self.int2a1(idx)
        if len(res) < 1:
            return None
        return res

    def convert_to_formula_column(
        self, gname: str, sheet_name: str, column_name: str
    ) -> None:
        sheet = self._get_worksheet(gname, sheet_name)
        if sheet is None:
            return
        a1 = self.get_a1_from_column_name(gname, sheet_name, column_name)
        logger.info(a1)
        cells = sheet.range(f"{a1}2:{a1}")
        sheet.update_cells(
            cells, value_input_option=gspread_utils.ValueInputOption.user_entered
        )

    def convert_to_raw_column(
        self, gname: str, sheet_name: str, column_name: str
    ) -> None:
        sheet = self._get_worksheet(gname, sheet_name)
        if sheet is None:
            return
        a1 = self.get_a1_from_column_name(gname, sheet_name, column_name)
        logger.info(a1)
        cells = sheet.range(f"{a1}2:{a1}")
        sheet.update_cells(cells, value_input_option=gspread_utils.ValueInputOption.raw)


if __name__ == "__main__":
    secret = load_secret_from_gcp("./keyfile.json", "FLOW_GSHEET_CREDENTIALS")
    if not secret:
        logger.error("Could not load secret.")
        sys.exit(1)
    if not isinstance(secret, dict):
        logger.error("Could not load secret as keyfile dictionary.")
        sys.exit(1)
    sheets = GCPSheets(secret)

    df = sheets.read_worksheet(
        "https://docs.google.com/spreadsheets/d/1OorfebrsPcss16iJoP2BwJiTZhOiovarjAR0WBvb2f0/edit#gid=0",
        "Sheet2",
    )
    # df["formulas"] = "=SUM(A2:A4)"
    # print(df)
    # df["col1"] = df["col1"].astype("int")
    # df["formulas"] = df["formulas"].astype("object")
    # df.info()
    # write_worksheet(
    #     creds,
    #     "https://docs.google.com/spreadsheets/d/1OorfebrsPcss16iJoP2BwJiTZhOiovarjAR0WBvb2f0/edit#gid=0",
    #     "Sheet3",
    #     df,
    # )

    # convert_to_formula_column(creds, 'https://docs.google.com/spreadsheets/d/1OorfebrsPcss16iJoP2BwJiTZhOiovarjAR0WBvb2f0/edit#gid=0', 'Sheet3', 'formulas')

    # df = read_worksheet(
    #     creds,
    #     "https://docs.google.com/spreadsheets/d/1OorfebrsPcss16iJoP2BwJiTZhOiovarjAR0WBvb2f0/edit#gid=0",
    #     "Sheet3",
    # )
    # print(df)

    logger.info(sheets.list_spreadsheets())
    # print(whats_my_email_again(creds))

    # ts1 = get_modified_time(creds, '1USfTluR_J0HE4iO30sCbyNzxKx7VVtM79tnKMwxaj5s')
    # ts2, id, title = get_last_update_time(creds, 'https://docs.google.com/spreadsheets/d/1USfTluR_J0HE4iO30sCbyNzxKx7VVtM79tnKMwxaj5s')

    # print('TIMES: ')
    # print(ts1)
    # print(ts2)
    # print(ts1 == ts2)

    # print('Missing spreadsheet: ',
    #       exists_spreadsheet(creds, 'https://docs.google.com/spreadsheets/d/1USfTluR_J0HE4iO30sCbyNzxKx7VVtM79tnKMwxaj5s1'))
    # print('Not a missing spreadsheet: ',
    #       exists_spreadsheet(creds, 'https://docs.google.com/spreadsheets/d/1USfTluR_J0HE4iO30sCbyNzxKx7VVtM79tnKMwxaj5s'))

    # print(create_spreadsheet(cred, 'flow_test_sheet2', ['nico.goernitz@gmail.com']))

    # for gsheet in list_spreadsheets(creds):
    #     print(gsheet)

    # append_to_worksheet("flow_test_sheet", "Sheet1", _append_test_dataframe(None))

    # df = read_worksheet(creds, 'flow_test_sheet', 'Sheet1')
    # print(df.head())
    # df.iloc[1,1] = 'name'
    # print(df.fillna('').values.tolist())
    # print(df.fillna('').to_numpy())
    # write_worksheet(creds, 'flow_test_sheet', 'Sheet3', pd.DataFrame([[1,2,3],[4,3,1]]))
    # single_entry = pd.DataFrame([['a','b','c']], columns=['0','1','2'])
    # update_entry_in_worksheet(creds, 'flow_test_sheet', 'Sheet3',
    #                           single_entry, query='2', col_name='1')
    # append_to_worksheet(creds, 'flow_test_sheet', 'Sheet1', pd.DataFrame([[1,2,3],[4,3,1]]))

    # test external oauth accounts
    # sheet = _get_spreadsheet('https://docs.google.com/spreadsheets/d/1jjez2oqyaBVT3gVElrdRzfMNFMND_bHfDwlrMNkfE6c/edit#gid=0')
    # print(sheet)
    # print(sheet.worksheets())
