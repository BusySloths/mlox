
sudo docker compose -f "docker-compose-airflow-VERSION.yaml" down --remove-orphans

sudo docker compose --env-file /home/USER/airflow/.env -f "docker-compose-airflow-VERSION.yaml" up -d --build


## Dot-env
export `cat .env`


Get this by typing `id -u` for the airflow linux user
`AIRFLOW_UID=1000`

Names of the self-signed certificates and location:
`_AIRFLOW_SSL_CERT_NAME=airflow.crt`
`_AIRFLOW_SSL_KEY_NAME=airflow.key`
`_AIRFLOW_SSL_FILE_PATH=/HERE/ARE/THE/CERTFICATES/`

IP address and port of the server and secret path
`_AIRFLOW_BASE_URL=https://12.10.23.2:1234/kdfkjjdfsaljfoeienvf`
`_AIRFLOW_OUT_PORT=1234`

Username and password
`_AIRFLOW_WWW_USER_USERNAME=USERNAME`
`_AIRFLOW_WWW_USER_PASSWORD=PASSWORD`

Airflow outputs are stored here:
`_AIRFLOW_OUT_FILE_PATH=/AIRFLOW/OUT/DIR`

Where are the dags path? 
`_AIRFLOW_DAGS_FILE_PATH=/HERE/ARE/THE/DAGS`

Options
`_AIRFLOW_LOAD_EXAMPLES=false`