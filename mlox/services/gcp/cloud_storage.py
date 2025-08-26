import sys
import logging
import pandas as pd

from io import StringIO
from typing import List, Dict
from dataclasses import dataclass, field

from google.cloud.storage import Client  # type: ignore
from google.oauth2.service_account import Credentials

from mlox.services.gcp.secret_manager import dict_to_service_account_credentials


# Configure logging (optional, but recommended)
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@dataclass
class GCPStorage:
    keyfile_dict: Dict = field(default_factory=dict, init=True)
    _project_id: str = field(default="", init=False)
    _credentials: Credentials | None = field(default=None, init=False)

    def __post_init__(self):
        self._credentials = dict_to_service_account_credentials(self.keyfile_dict)
        self._project_id = self.keyfile_dict.get("project_id", "")

    def _get_storage_client(self) -> Client:
        return Client(project=self._project_id, credentials=self._credentials)

    def list_buckets(self) -> List:
        """List all buckets in the project.
        Returns:
            List: list of buckets
        """
        buckets = self._get_storage_client().list_buckets()
        return [bucket.name for bucket in buckets]

    def list_objects(self, dir: str, bucket_name: str) -> List:
        """List all objects in a certain directory of a storage bucket.

        Args:
            dir (str): directory
            bucket_name (str): name of the storage bucket (default is DATALAKE_BUCKET_NAME)

        Returns:
            List: list of objects in the given directory
        """
        blobs = self._get_storage_client().list_blobs(bucket_name, prefix=dir)
        return [blob.name for blob in blobs]

    def read_file(self, fname: str, bucket_name: str) -> str:
        """Reads the content of a file (incl. path) in a storage bucket.

        Args:
            fname (str): file name including path
            bucket_name (str): name of the storage bucket (default is DATALAKE_BUCKET_NAME)

        Returns:
            str: content of the file as utf-8 string
        """
        bucket = self._get_storage_client().get_bucket(bucket_name)
        blob = bucket.blob(fname)
        return blob.download_as_string().decode("utf-8")

    def read_csv_as_dataframe(self, fname: str, bucket_name: str) -> pd.DataFrame:
        """Reads the content of a file (incl. path) in a storage bucket and return a dataframe.

        Args:
            fname (str): csv file name including path
            bucket_name (str): name of the storage bucket (default is DATALAKE_BUCKET_NAME)

        Returns:
            pd.DataFrame: pandas representation of the the csv file
        """
        bucket = self._get_storage_client().get_bucket(bucket_name)
        blob = bucket.blob(fname)
        return pd.read_csv(
            StringIO(blob.download_as_string().decode("utf-8")), index_col=0
        )

    def rename_file(self, old_fname: str, new_fname: str, bucket_name: str) -> None:
        """Rename a file (incl. path) in a storage bucket.

        Args:
            old_fname (str): the old file name including path
            new_fname (str): the new file name including path
            bucket_name (str): name of the storage bucket (default is DATALAKE_BUCKET_NAME)
        """
        bucket = self._get_storage_client().get_bucket(bucket_name)
        blob = bucket.blob(old_fname)
        _ = bucket.rename_blob(blob, new_fname)

    def write_dataframe_as_csv(
        self, fname: str, df: pd.DataFrame, bucket_name: str
    ) -> bool:
        """Writes a dataframe as csv to a file (incl. path) in a storage bucket.

        Args:
            fname (str): file name including path
            df (pd.DataFrame): data
            bucket_name (str): name of the storage bucket (default is DATALAKE_BUCKET_NAME)

        Returns:
            bool: True, if successful.
        """
        bucket = self._get_storage_client().get_bucket(bucket_name)
        try:
            bucket.blob(fname).upload_from_string(df.to_csv(), "text/csv")
            logger.info(f"File {fname} uploaded successfully to {bucket_name}.")
        except Exception as e:
            logger.error(f"Could not write file {fname} to bucket.")
            return False
        return True


if __name__ == "__main__":
    from mlox.services.gcp.secret_manager import GCPSecretManager, read_keyfile

    keyfile_dict = read_keyfile("./keyfile.json")
    sm = GCPSecretManager(keyfile_dict=keyfile_dict)
    secret = sm.load_secret("FLOW_STORAGE_CREDENTIALS")
    if not isinstance(secret, dict):
        logger.error("Could not load secret.")
        sys.exit(1)

    DATALAKE_BUCKET_NAME: str = "magical-place"
    storage = GCPStorage(keyfile_dict=secret)
    logger.info(
        storage.write_dataframe_as_csv(
            "test1.csv",
            pd.DataFrame(["A", "b", "c"], columns=["c1"]),
            DATALAKE_BUCKET_NAME,
        )
    )
    df = storage.read_csv_as_dataframe("test1.csv", DATALAKE_BUCKET_NAME)
    logger.info(df)
    fnames = storage.list_objects("", DATALAKE_BUCKET_NAME)
    logger.info(fnames)
    # rename_file('tests/test1.csv', 'tests/new_test1.csv')
    # fnames = list_objects('tests/')
    # print(fnames)
