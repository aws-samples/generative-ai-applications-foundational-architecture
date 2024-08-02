import pytest
import requests
import time

# Set the base URL for the FastAPI app
BASE_URL = "<your_api_url>"

# Set the Authorization token
AUTH_TOKEN = "<your_auth_token>"

# Define headers with the token
headers = {
    "Authorization": f"Bearer {AUTH_TOKEN}",
    "Content-Type": "application/json"
}

# call /list_models to get the list of models
response = requests.get(f"{BASE_URL}/list_models", headers=headers)
model_names = [model["model_name"] for model in response.json()['text_models']]
embed_model_names = [model["model_name"] for model in response.json()['embed_models']]

# Standard request data for invoke and async_invoke endpoints
standard_request_data_string = {
    "model_name": "example_model",
    "prompt": "Translate the following text to French: 'Hello, how are you?'",
    "max_tokens": 100,
    "temperature": 0.7,
    "top_p": 0.9,
    "top_k": 50
}

standard_request_data_json = {
    "model_name": "example_model",
    "prompt": [
        {
            "role": "user",
            "content": [{"text": "What is the weather like today?"}]
        },
        {
            "role": "assistant",
            "content": [{"text": "The weather is sunny with a high of 25°C."}]
        },
        {
            "role": "user",
            "content": [{"text": "Farenheit or Celsius?"}]
        }
    ],
    "max_tokens": 100,
    "temperature": 0.7,
    "top_p": 0.9,
    "top_k": 50,
    "system": [ 
            { 
                "text": "Your assistant is here to help you with your questions." 
            } 
    ]
}

standard_request_embed_data = {
    "model_name": "example_model",
    "input_text": "Translate the following text to French: 'Hello, how are you?'"
}

@pytest.mark.parametrize("model_name", model_names)
@pytest.mark.parametrize("request_data", [standard_request_data_string, standard_request_data_json])
def test_invoke(model_name, request_data):
    data = request_data.copy()
    data["model_name"] = model_name

    if model_name.startswith("TITAN"):
        data["stop_sequences"] = ["User:"]
    else:
        data["stop_sequences"] = ["\\n"]

    response = requests.post(f"{BASE_URL}/invoke", headers=headers, json=data)
    print("*"*50)
    print(response.text)
    print("*"*50)
    assert response.status_code == 200
    print(f"Response for /invoke with model {model_name}: {response.json()}")

# Test Embed models
@pytest.mark.parametrize("model_name", embed_model_names)
@pytest.mark.parametrize("request_data", [standard_request_embed_data])
def test_invoke_embed(model_name, request_data):
    print(f"Testing /invoke with model {model_name}")
    data = request_data.copy()
    data["model_name"] = model_name

    response = requests.post(f"{BASE_URL}/embed", headers=headers, json=data)
    print("*"*50)
    print(response.text)
    print("*"*50)
    assert response.status_code == 200
    print(f"Response for /invoke with model {model_name}: {response.json()}")

@pytest.mark.parametrize("model_name", model_names)
@pytest.mark.parametrize("request_data", [standard_request_data_string])
def test_async_invoke(model_name, request_data):
    data = request_data.copy()
    data["model_name"] = model_name

    if model_name.startswith("TITAN"):
        data["stop_sequences"] = ["User:"]
    else:
        data["stop_sequences"] = ["\\n"]

    response = requests.post(f"{BASE_URL}/async_invoke", headers=headers, json=data)
    assert response.status_code == 200
    invocation_id = response.json().get("invocation_id")
    print(f"Invocation ID for /async_invoke with model {model_name}: {invocation_id}")

    # Poll for the result
    time.sleep(10)
    result_response = requests.get(f"{BASE_URL}/async_output/{invocation_id}", headers=headers)
    assert result_response.status_code == 200
    print(f"Result for async_invoke with model {model_name}: {result_response.json()}")


if __name__ == "__main__":
    print("Running tests")
    pytest.main(["-s", "test_model_invoke.py"])
