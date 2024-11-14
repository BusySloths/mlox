import os
import requests  # type: ignore

# URL and API key
base_url = f"{os.environ["TEST_LITELLM_URI"]}v1/chat/completions"
api_key = os.environ["TEST_LITELLM_API_KEY"]

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
