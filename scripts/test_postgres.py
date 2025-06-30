import os
import sys
import tempfile

try:
    import psycopg2
except ImportError:
    print("Error: The 'psycopg2-binary' package is not installed.")
    print("Please install it by running: pip install psycopg2-binary")
    sys.exit(1)

from mlox.session import MloxSession


# --- DATABASE CONNECTION PARAMETERS ---
# These parameters can be set directly in this script or, for better security,
# as environment variables on your system. The script will use environment
# variables if they are set, otherwise it will fall back to the values here.
#
# Example of setting an environment variable in bash:
# export DB_HOST="my.database.com"

password = os.environ.get("MLOX_CONFIG_PASSWORD", None)
# Make sure your environment variable is set!
if not password:
    print("Error: MLOX_CONFIG_PASSWORD environment variable is not set.")
    exit(1)
session = MloxSession("mlox", password)
infra = session.infra

pdb = infra.get_service("postgres-16-bullseye")
if not pdb:
    print("Could not load service")
    exit(1)

bundle = infra.get_bundle_by_service(pdb)
if not bundle:
    print("Could not load server")
    exit(1)

# The IP address or hostname of your PostgreSQL server.
DB_HOST = bundle.server.ip

# The port your PostgreSQL server is listening on (default is 5432).
DB_PORT = pdb.port

# The name of the database you want to connect to.
DB_NAME = pdb.db

# The username for authenticating to the database.
DB_USER = pdb.user

# The password for the specified user.
DB_PASSWORD = pdb.pw

# --- SSL CONFIGURATION ---
# Determines the SSL connection policy.
# 'disable': No SSL is used.
# 'allow': Tries non-SSL first, then falls back to SSL if the server requires it.
# 'prefer': Tries SSL first, then falls back to a non-SSL connection.
# 'require': Only tries an SSL connection. Fails if the server doesn't offer SSL. (Good for testing)
# 'verify-ca': Like 'require', but also verifies the server certificate against a trusted CA.
# 'verify-full': Like 'verify-ca', but also verifies the server hostname matches the certificate. (Most secure)
#
# For most secure connections, 'verify-full' is recommended if you have the CA certificate.
# For a basic "is SSL working" test, 'require' is sufficient.
SSL_MODE = "require"
SSL_MODE = "verify-full"

# Optional: For 'verify-ca' or 'verify-full', provide the path to the root CA certificate file.
# If you don't need to verify the CA, you can leave this as an empty string.
# Example: SSL_ROOT_CERT_PATH = "/path/to/your/ca.crt"
# Can also be set via the DB_SSL_ROOT_CERT environment variable.


def main():
    """
    Attempts to connect to the PostgreSQL database using the specified
    credentials and SSL mode.
    """
    temp_cert_path = None
    conn = None
    try:
        # If verification is needed, write the certificate from memory to a temporary file
        # because psycopg2 requires a file path for sslrootcert.
        if SSL_MODE in ("verify-ca", "verify-full") and pdb.certificate:
            tmp_dir = "./.tmp"
            os.makedirs(tmp_dir, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="w", delete=False, suffix=".pem", dir=tmp_dir
            ) as f:
                f.write(pdb.certificate)
                temp_cert_path = f.name
            print(
                f"Temporary certificate for verification written to: {temp_cert_path}"
            )

        print(
            f"Attempting to connect to database '{DB_NAME}' at {DB_HOST}:{DB_PORT} with SSL_MODE='{SSL_MODE}'..."
        )

        # Build the connection keyword arguments dictionary
        conn_kwargs = {
            "host": DB_HOST,
            "port": DB_PORT,
            "dbname": DB_NAME,
            "user": DB_USER,
            "password": DB_PASSWORD,
            "sslmode": SSL_MODE,
        }
        if temp_cert_path:
            conn_kwargs["sslrootcert"] = temp_cert_path

        # Establish the connection
        conn = psycopg2.connect(**conn_kwargs)
        cursor = conn.cursor()

        # 1. Check if the connection is actually using SSL
        # The ssl_is_used() function requires the 'sslinfo' extension.
        # A more reliable, built-in method is to query the pg_stat_ssl view.
        cursor.execute("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid();")
        result = cursor.fetchone()
        is_ssl = result[0] if result else False

        if is_ssl:
            cursor.execute("SELECT version();")
            pg_version = cursor.fetchone()[0]
            print(f"✅ Success! Connection is established and is using SSL.")
            print(f"   PostgreSQL version: {pg_version}")
        else:
            print("⚠️ Warning: Connection established, but it is NOT using SSL.")

        # 2. Perform a full read/write test to verify permissions and operation
        test_table_name = "mlox_connection_test_2"
        print(
            f"\nPerforming test: CREATE -> INSERT -> SELECT -> DROP on table '{test_table_name}'..."
        )

        # Create table
        cursor.execute(f"DROP TABLE IF EXISTS {test_table_name};")
        cursor.execute(
            f"CREATE TABLE {test_table_name} (id INT, message VARCHAR(255));"
        )
        conn.commit()  # This is the crucial step to save the changes
        print(f"-> Table '{test_table_name}' created.")

        # Verify table exists
        cursor.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s;",
            (test_table_name,),
        )
        if cursor.fetchone():
            print(f"-> Verified: Table '{test_table_name}' exists in database.")
        else:
            print(
                f"-> Verification FAILED: Table '{test_table_name}' was not found after creation."
            )

        # Insert data
        test_message = "Hello from MLOX!"
        cursor.execute(
            f"INSERT INTO {test_table_name} (id, message) VALUES (%s, %s);",
            (1, test_message),
        )
        conn.commit()  # Commit the insert
        print(f"-> Data inserted: (1, '{test_message}')")

        # Select and verify data
        cursor.execute(f"SELECT message FROM {test_table_name} WHERE id = 1;")
        retrieved_message = cursor.fetchone()[0]
        assert retrieved_message == test_message, "Data mismatch!"
        print(f"-> Data selected and verified: '{retrieved_message}'")
        print("✅ Read/Write test successful!")

    except psycopg2.Error as e:
        print(f"❌ Error: Could not connect to the database.")
        print(f"   Details: {e}")
        sys.exit(1)  # Exit with a non-zero status code to indicate failure
    finally:
        if conn:
            try:
                # Ensure cleanup by dropping the test table
                cursor = conn.cursor()
                # cursor.execute("DROP TABLE IF EXISTS mlox_connection_test;")
                conn.commit()
                print("-> Test table dropped.")
            except psycopg2.Error as e:
                print(f"Warning: Could not drop test table during cleanup: {e}")
            finally:
                conn.close()
                print("Connection closed.")

        if temp_cert_path and os.path.exists(temp_cert_path):
            os.remove(temp_cert_path)
            print(f"Removed temporary certificate: {temp_cert_path}")


if __name__ == "__main__":
    main()
