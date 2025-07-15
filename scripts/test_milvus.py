import os
import sys
from pymilvus import utility, connections, MilvusClient, DataType  # type: ignore

from mlox.services.gcp_secrets.secret_manager import GCPSecretManager, read_keyfile


def load_connection_parameters(keyfile: str, secret_name: str) -> dict:
    keyfile_dict = read_keyfile(keyfile)
    sm = GCPSecretManager(keyfile_dict)
    if not sm.is_working():
        print("Error: GCP Secret Manager is not working. Check your keyfile.")
        sys.exit(1)
    value = sm.load_secret(secret_name)
    if not value:
        print(f"Error: Could not load secret '{secret_name}' from GCP Secret Manager.")
        sys.exit(1)
    if not isinstance(value, dict):
        print(f"Error: Secret '{secret_name}' is not a dictionary.")
        sys.exit(1)
    return value


# Milvus Connection Test
def test_milvus_connection():
    params = load_connection_parameters("./keyfile.json", "MLOX_MILVUS_MILVUS-STORE")
    # Write the certificate content to a temp file
    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".pem", delete=False
    ) as cert_file:
        cert_file.write(params["certificate"])
        cert_file_path = cert_file.name

    try:
        connections.connect(
            alias="default",
            # user="Milvus",
            # password="",
            uri=params["url"],
            # uri=os.environ["TEST_MILVUS_URI"],
            # user=os.environ["TEST_MILVUS_USER"],
            # password=os.environ["TEST_MILVUS_PW"],
            secure=True,
            server_pem_path=cert_file_path,
        )
        print("Connected to Milvus successfully.")
        print(connections.list_connections())

        users = utility.list_usernames(using="default")
        print(users)

        client = MilvusClient(
            uri=params["url"],
            secure=True,
            server_pem_path=cert_file_path,
        )
        # client.create_database(db_name="my_database_2")
        print(client.list_databases())
        print(client.describe_database(db_name="my_database_2"))

        # 3.1. Create schema
        schema = client.create_schema(
            auto_id=False,
            enable_dynamic_field=True,
        )

        # 3.2. Add fields to schema
        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
        schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=5)
        schema.add_field(field_name="color", datatype=DataType.VARCHAR, max_length=512)

        client.create_collection(
            collection_name="customized_setup_3",
            schema=schema,
            index_params=None,
        )

        print(client.list_collections())

        data = [
            {
                "id": 0,
                "vector": [
                    0.3580376395471989,
                    -0.6023495712049978,
                    0.18414012509913835,
                    -0.26286205330961354,
                    0.9029438446296592,
                ],
                "color": "pink_8682",
            },
            {
                "id": 1,
                "vector": [
                    0.19886812562848388,
                    0.06023560599112088,
                    0.6976963061752597,
                    0.2614474506242501,
                    0.838729485096104,
                ],
                "color": "red_7025",
            },
            {
                "id": 2,
                "vector": [
                    0.43742130801983836,
                    -0.5597502546264526,
                    0.6457887650909682,
                    0.7894058910881185,
                    0.20785793220625592,
                ],
                "color": "orange_6781",
            },
            {
                "id": 3,
                "vector": [
                    0.3172005263489739,
                    0.9719044792798428,
                    -0.36981146090600725,
                    -0.4860894583077995,
                    0.95791889146345,
                ],
                "color": "pink_9298",
            },
            {
                "id": 4,
                "vector": [
                    0.4452349528804562,
                    -0.8757026943054742,
                    0.8220779437047674,
                    0.46406290649483184,
                    0.30337481143159106,
                ],
                "color": "red_4794",
            },
            {
                "id": 5,
                "vector": [
                    0.985825131989184,
                    -0.8144651566660419,
                    0.6299267002202009,
                    0.1206906911183383,
                    -0.1446277761879955,
                ],
                "color": "yellow_4222",
            },
            {
                "id": 6,
                "vector": [
                    0.8371977790571115,
                    -0.015764369584852833,
                    -0.31062937026679327,
                    -0.562666951622192,
                    -0.8984947637863987,
                ],
                "color": "red_9392",
            },
            {
                "id": 7,
                "vector": [
                    -0.33445148015177995,
                    -0.2567135004164067,
                    0.8987539745369246,
                    0.9402995886420709,
                    0.5378064918413052,
                ],
                "color": "grey_8510",
            },
            {
                "id": 8,
                "vector": [
                    0.39524717779832685,
                    0.4000257286739164,
                    -0.5890507376891594,
                    -0.8650502298996872,
                    -0.6140360785406336,
                ],
                "color": "white_9381",
            },
            {
                "id": 9,
                "vector": [
                    0.5718280481994695,
                    0.24070317428066512,
                    -0.3737913482606834,
                    -0.06726932177492717,
                    -0.6980531615588608,
                ],
                "color": "purple_4976",
            },
        ]

        res = client.insert(collection_name="customized_setup_3", data=data)

        print(res)
        #
        # utility.create_user("my_user", "my_password", using="default")
    except Exception as e:
        print(f"Failed to connect to Milvus: {e}")
    finally:
        if os.path.exists(cert_file_path):
            os.remove(cert_file_path)
    connections.disconnect("default")


if __name__ == "__main__":
    print("Testing connections...")

    test_milvus_connection()
