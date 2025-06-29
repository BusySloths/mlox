import os
import requests  # type: ignore

from mlox.session import MloxSession


password = os.environ.get("MLOX_CONFIG_PASSWORD", None)
if not password:
    print("Error: MLOX_CONFIG_PASSWORD environment variable is not set.")
    exit(1)

session = MloxSession("mlox", password)
# session.load_infrastructure()
infra = session.infra

service = infra.get_service("litellm-ollama-1.73.0")
if not service:
    print("Service not found")
    exit(1)

base_url = service.service_urls["LiteLLM UI"][:-3]
base_url += "/v1/chat/completions"
# URL and API key
# base_url = f"{os.environ['TEST_LITELLM_URI']}
api_key = service.api_key


# Headers for authentication
headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

# Data for the chat completion request
data = {
    "model": "tinyllama",
    "messages": [
        {"role": "user", "content": "this is a test request, write a short poem"}
    ],
}

# Send the request, disabling SSL verification
response = requests.post(base_url, headers=headers, json=data, verify=False)

# Print the response
if response.status_code == 200:
    print(response.json())
else:
    print(f"Error: {response.status_code}, {response.text}")
