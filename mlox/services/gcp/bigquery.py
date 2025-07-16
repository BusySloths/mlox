"""Provides GCP BigQuery access.

Requires BQ service account saved as FLOW_BIGQUERY_CREDENTIALS secret.
Requires:
    - BigQuery Data Editor
    - BigQuery Job User
    - BigQuery Read Session User
    - Storage Object Admin

Author: nicococo
"""

import pandas as pd

from typing import Dict
from dataclasses import dataclass, field

from google.oauth2.service_account import Credentials

from mlox.services.gcp.secret_manager import dict_to_service_account_credentials


@dataclass
class BigQuery:
    keyfile_dict: Dict = field(default_factory=dict, init=True)
    _project_id: str = field(default="", init=False)
    _credentials: Credentials | None = field(default=None, init=False)

    def __post_init__(self):
        self._credentials = dict_to_service_account_credentials(self.keyfile_dict)
        self._project_id = self.keyfile_dict.get("project_id", "")

    def query_to_df(self, query: str) -> pd.DataFrame:
        return pd.read_gbq(
            query,
            credentials=self._credentials,
            project_id=self._project_id,
            progress_bar_type="tqdm",
        )

    def list_tables(self, dataset: str) -> pd.DataFrame:
        return self.query_to_df(
            f"SELECT * FROM `{self._project_id}.{dataset}.__TABLES__`"
        )

    def list_datasets(self) -> pd.DataFrame:
        return self.query_to_df(f"SELECT * FROM `{self._project_id}.__TABLES__`")

    def _df_table_interaction(
        self, dataset: str, table: str, df: pd.DataFrame, if_exists="fail"
    ) -> None:
        df.to_gbq(
            dataset + "." + table,
            credentials=self._credentials,
            project_id=self._project_id,
            if_exists=if_exists,
            progress_bar=True,
        )

    def replace_table_with_df(self, dataset: str, table: str, df: pd.DataFrame) -> None:
        self._df_table_interaction(dataset, table, df, if_exists="replace")

    def create_table_from_df(self, dataset: str, table: str, df: pd.DataFrame) -> None:
        self._df_table_interaction(dataset, table, df, if_exists="fail")

    def append_df_to_table(self, dataset: str, table: str, df: pd.DataFrame) -> None:
        self._df_table_interaction(dataset, table, df, if_exists="append")


if __name__ == "__main__":
    df = pd.DataFrame(["A", "b", "c"], columns=["c1"])
    # _bq_df_table_interaction('dev', 'tbl_my_test_1', df)
    # bq_append_df_to_table('dev', 'tbl_my_test_1', df)
    # bq_create_table_from_df('sheetcloud', 'tbl_my_test_1', df)
