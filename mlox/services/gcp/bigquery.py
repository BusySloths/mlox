"""Provides GCP BigQuery access.

Requires BQ service account saved as FLOW_BIGQUERY_CREDENTIALS secret.
Requires:
    - BigQuery Data Editor
    - BigQuery Job User
    - BigQuery Read Session User
    - Storage Object Admin

Author: nicococo
"""

import sys
import pandas as pd

from google.cloud import bigquery
from typing import Dict
from dataclasses import dataclass, field

from google.oauth2.service_account import Credentials

from mlox.services.gcp.secret_manager import (
    dict_to_service_account_credentials,
    load_secret_from_gcp,
)


@dataclass
class BigQuery:
    keyfile_dict: Dict = field(default_factory=dict, init=True)
    _project_id: str = field(default="", init=False)
    _credentials: Credentials | None = field(default=None, init=False)
    _client: bigquery.Client | None = field(default=None, init=False)

    def __post_init__(self):
        self._credentials = dict_to_service_account_credentials(self.keyfile_dict)
        self._project_id = self.keyfile_dict.get("project_id", "")
        self._client = bigquery.Client(
            project=self._project_id, credentials=self._credentials
        )

    def query_to_df(self, query: str) -> pd.DataFrame:
        return pd.read_gbq(
            query,
            credentials=self._credentials,
            project_id=self._project_id,
            progress_bar_type="tqdm",
        )

    def list_tables(self, dataset: str) -> pd.DataFrame:
        """Lists tables in a dataset using the BigQuery client API.

        This is more robust than using INFORMATION_SCHEMA, as it uses the
        native GCP API call.
        """
        if not self._client:
            return pd.DataFrame()
        tables = self._client.list_tables(f"{self._project_id}.{dataset}")
        table_list = [
            {
                "project_id": table.project,
                "dataset_id": table.dataset_id,
                "table_id": table.table_id,
                "type": table.table_type,
                "creation_time": table.created,
                "expiration_time": table.expires,
            }
            for table in tables
        ]
        return pd.DataFrame(table_list)

    def list_datasets(self) -> pd.DataFrame:
        """Lists all datasets in the project using the BigQuery client API.

        This is the correct method for listing project-level datasets, as it
        is not region-specific like an INFORMATION_SCHEMA query.
        """
        if not self._client:
            return pd.DataFrame()
        datasets = self._client.list_datasets()
        dataset_list = [
            {"project_id": ds.project, "dataset_id": ds.dataset_id} for ds in datasets
        ]
        return pd.DataFrame(dataset_list)

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
    secret = load_secret_from_gcp("./keyfile.json", "FLOW_BIGQUERY_CREDENTIALS")
    if not secret:
        print("Could not load secret.")
        sys.exit(1)
    if not isinstance(secret, dict):
        print("Could not load secret as keyfile dictionary.")
        sys.exit(1)
    bq = BigQuery(keyfile_dict=secret)
    res = bq.list_datasets()
    print(res)
    res = bq.list_tables("sheetcloud")
    print(res)

    # df = pd.DataFrame(["A", "b", "c"], columns=["c1"])
    # _bq_df_table_interaction('dev', 'tbl_my_test_1', df)
    # bq_append_df_to_table('dev', 'tbl_my_test_1', df)
    # bq_create_table_from_df('sheetcloud', 'tbl_my_test_1', df)
