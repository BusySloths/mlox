import os
from pymilvus import connections  # type: ignore
from pymilvus import utility


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
        #
        # utility.create_user("my_user", "my_password", using="default")

    except Exception as e:
        print(f"Failed to connect to Milvus: {e}")


if __name__ == "__main__":
    print("Testing connections...")

    test_milvus_connection()
