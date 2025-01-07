import os
import unittest
from unittest.mock import patch, MagicMock
from pymilvus import connections, utility  # type: ignore


# Milvus Connection Test
def test_milvus_connection():
    try:
        connections.connect(
            alias="default",
            uri=os.environ["TEST_MILVUS_URI"],
            user=os.environ["TEST_MILVUS_USER"],
            password=os.environ["TEST_MILVUS_PW"],
            # secure=True,
        )
        print("Connected to Milvus successfully.")

        users = utility.list_usernames(using="default")
        print(users)

    except Exception as e:
        print(f"Failed to connect to Milvus: {e}")


class TestMilvusConnection(unittest.TestCase):
    @patch("pymilvus.connections")
    @patch("pymilvus.utility")
    def test_connection_success(self, mock_utility, mock_connections):
        # Mock successful connection
        mock_connections.connect.return_value = None
        mock_utility.list_usernames.return_value = ["user1", "user2"]

        with patch.dict(
            os.environ,
            {
                "TEST_MILVUS_URI": "milvus_uri",
                "TEST_MILVUS_USER": "milvus_user",
                "TEST_MILVUS_PW": "milvus_password",
            },
        ):
            test_milvus_connection()

        mock_connections.connect.assert_called_once_with(
            alias="default",
            uri="milvus_uri",
            user="milvus_user",
            password="milvus_password",
        )

        mock_utility.list_usernames.assert_called_once_with(using="default")

    @patch("pymilvus.connections")
    def test_connection_failure(self, mock_connections):
        # Mock failed connection
        mock_connections.connect.side_effect = Exception("Connection error")

        with patch.dict(
            os.environ,
            {
                "TEST_MILVUS_URI": "milvus_uri",
                "TEST_MILVUS_USER": "milvus_user",
                "TEST_MILVUS_PW": "milvus_password",
            },
        ):
            with self.assertLogs() as log:
                test_milvus_connection()

            self.assertIn(
                "Failed to connect to Milvus: Connection error", log.output[0]
            )


if __name__ == "__main__":
    unittest.main()
