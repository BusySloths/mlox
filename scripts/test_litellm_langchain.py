import os
import httpx
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage

os.environ["OPENAI_API_KEY"] = os.environ["TEST_LITELLM_API_KEY"]

# Create an HTTP client with SSL verification disabled
http_client = httpx.Client(verify=False)

# Initialize the ChatOpenAI instance with the custom HTTP client
chat = ChatOpenAI(
    base_url=os.environ["TEST_LITELLM_URI"],
    model="tinyllama",
    temperature=0.1,
    http_client=http_client,
)

# Define the messages
messages = [
    SystemMessage(
        content="You are a helpful assistant that I'm using to make a test request to."
    ),
    HumanMessage(
        content="Test from LiteLLM. Tell me why it's amazing in one sentence."
    ),
]

# Get the response
response = chat.invoke(messages)

# Print the response
print(response)
