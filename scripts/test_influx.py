import os

from influxdb import InfluxDBClient

from mlox.session import MloxSession


def main():
    password = os.environ.get("MLOX_CONFIG_PASSWORD", None)
    # Make sure your environment variable is set!
    if not password:
        print("Error: MLOX_CONFIG_PASSWORD environment variable is not set.")
        exit(1)
    session = MloxSession("mlox", password)
    session.load_infrastructure()
    infra = session.infra

    dbs = infra.filter_by_group("database")
    my_influx = None
    for db in dbs:
        print(f"Database: {db.config.name}")
        if db.config.name.lower() == "influxdb":
            my_influx = db

    bundle = None
    if my_influx:
        bundle = infra.get_bundle_by_service(my_influx.service)
    else:
        print("No InfluxDB service found in the infrastructure.")
        exit(1)

    """Instantiate a connection to the InfluxDB."""
    host = bundle.server.ip
    port = my_influx.service.port
    user = my_influx.service.user
    password = my_influx.service.pw
    dbname = "test_02_db"
    # dbuser = "smly"
    # dbuser_password = "my_secret_password"
    # query = "select Float_value from cpu_load_short;"
    # query_where = "select Int_value from cpu_load_short where host=$host;"
    # bind_params = {"host": "server01"}
    json_body = [
        {
            "measurement": "cpu_load_short",
            "tags": {"host": "server01", "region": "us-west"},
            "time": "2009-11-10T23:00:00Z",
            "fields": {
                "Float_value": 0.64,
                "Int_value": 3,
                "String_value": "Text",
                "Bool_value": True,
            },
        }
    ]

    client = InfluxDBClient(
        host, port, user, password, dbname, ssl=True, verify_ssl=False
    )
    print(client.get_list_database())

    print("Create database: " + dbname)
    client.create_database(dbname)

    #     print("Create a retention policy")
    #     client.create_retention_policy("awesome_policy", "3d", 3, default=True)

    #     print("Switch user: " + dbuser)
    #     client.switch_user(dbuser, dbuser_password)

    print("Write points: {0}".format(json_body))
    client.write_points(json_body)


#     print("Querying data: " + query)
#     result = client.query(query)

#     print("Result: {0}".format(result))

#     print("Querying data: " + query_where)
#     result = client.query(query_where, bind_params=bind_params)

#     print("Result: {0}".format(result))

#     print("Switch user: " + user)
#     client.switch_user(user, password)

#     print("Drop database: " + dbname)
#     client.drop_database(dbname)


# def parse_args():
#     """Parse the args."""
#     parser = argparse.ArgumentParser(description="example code to play with InfluxDB")
#     parser.add_argument(
#         "--host",
#         type=str,
#         required=False,
#         default="localhost",
#         help="hostname of InfluxDB http API",
#     )
#     parser.add_argument(
#         "--port",
#         type=int,
#         required=False,
#         default=8086,
#         help="port of InfluxDB http API",
#     )
#     return parser.parse_args()


if __name__ == "__main__":
    main()
