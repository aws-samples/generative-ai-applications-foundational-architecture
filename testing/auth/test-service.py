###############################################
# This script tests the GenAI Foundational Architecture's API endpoints for authentication
# It uses the requests library to send HTTP requests to the API and pytest to run the tests.
# We pass valid and invalid JWT tokens in the Authorization header to test the authentication mechanism.
# It does not test the functionality of the endpoints, only the authentication.
# Replace the placeholders with your actual API URL, valid token, and invalid token.
###############################################

import json
import pytest
import requests

# Replace these with your actual API URL and tokens
API_URL = "<platform-api-url>"
VALID_TOKEN = "<valid-token>"
INVALID_TOKEN = "<invalid-token>"

# Sample data for testing the invoke_model endpoint
invoke_model_data = {
    "model_name": "ANTHROPIC_CLAUDE_3_SONNET_V1",
    "prompt": "Translate the following text to French: 'Hello, how are you?'",
    "max_tokens": 100,
    "temperature": 0.7,
    "top_p": 0.9,
    "top_k": 50,
    "stop_sequences": ["\\n"]
}

# Sample data for other endpoints
raw_input_data = {
    "model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
    "raw_input": {
        "text": "Hello, how are you?"
    }
}

embed_model_data = {
    "model_name": "example_model",
    "input_text": "Hello, how are you?"
}

chunking_job_data = {
    "extraction_job_id": "example_extraction_job_id",
    "chunking_strategy": "fixed_size",
    "chunking_params": {
        "chunk_size": 1000,
        "chunk_overlap": 100
    }
}

register_file_data = {
    "extraction_job_id": "example_extraction_job_id",
    "file_name": "example_file.txt"
}

start_job_data = {
    "extraction_job_id": "example_extraction_job_id"
}

file_status_data = {
    "extraction_job_id": "example_extraction_job_id",
    "file_name": "example_file.txt"
}

vector_store_data = {
    "store_type": "opensearchserverless",
    "description": "A vector store for semantic search.",
    "tags": {
        "environment": "production",
        "team": "data"
    }
}

vector_store_status_data = {
    "store_id": "example_store_id"
}

create_index_data = {
    "store_id": "example_store_id",
    "index_name": "my_index"
}

index_status_data = {
    "index_id": "example_index_id"
}

vectorize_data = {
    "chunking_job_id": "example_chunking_job_id",
    "index_id": "example_index_id"
}

semantic_search_data = {
    "query": "what is AWS?",
    "index_id": "example_index_id"
}

prompt_template_data = {
    "name": "CHATBOT_PROMPT",
    "prompt_template": "Given the following information, answer the question. Context {context}. Question {question}"
}

get_prompt_template_data = {
    "name": "CHATBOT_PROMPT"
}

prompt_template_version_data = {
    "name": "CHATBOT_PROMPT",
    "vnum": 1
}

@pytest.fixture
def valid_headers():
    return {"Authorization": f"Bearer {VALID_TOKEN}"}

@pytest.fixture
def invalid_headers():
    return {"Authorization": f"Bearer {INVALID_TOKEN}"}

def test_health_check(valid_headers):
    response = requests.get(f"{API_URL}/model/service/health", headers=valid_headers)
    assert response.status_code == 200
    assert response.json() == {"status": "UP"}

def test_invoke_model_with_valid_token(valid_headers):
    response = requests.post(f"{API_URL}/model/invoke", json=invoke_model_data, headers=valid_headers)
    assert response.status_code == 200
    assert "output_text" in response.json()
    assert "input_tokens" in response.json()
    assert "output_tokens" in response.json()

def test_invoke_model_with_invalid_token(invalid_headers):
    response = requests.post(f"{API_URL}/model/invoke", json=invoke_model_data, headers=invalid_headers)
    assert response.status_code == 401

def test_invoke_model_without_token():
    response = requests.post(f"{API_URL}/model/invoke", json=invoke_model_data)
    assert response.status_code == 401

def test_async_invoke_model_with_valid_token(valid_headers):
    response = requests.post(f"{API_URL}/model/async_invoke", json=invoke_model_data, headers=valid_headers)
    assert response.status_code == 200
    assert "invocation_id" in response.json()

def test_async_invoke_model_with_invalid_token(invalid_headers):
    response = requests.post(f"{API_URL}/model/async_invoke", json=invoke_model_data, headers=invalid_headers)
    assert response.status_code == 401

def test_async_invoke_model_without_token():
    response = requests.post(f"{API_URL}/model/async_invoke", json=invoke_model_data)
    assert response.status_code == 401

def test_invoke_with_raw_input(valid_headers):
    response = requests.post(f"{API_URL}/model/invoke_with_raw_input", json=raw_input_data, headers=valid_headers)
    assert response.status_code in [200, 400, 500]

def test_invoke_embed_with_valid_token(valid_headers):
    response = requests.post(f"{API_URL}/model/embed", json=embed_model_data, headers=valid_headers)
    assert response.status_code in [200, 400, 500]

def test_create_extraction_job_with_invalid_token(invalid_headers):
    response = requests.get(f"{API_URL}/document/extraction/create_job", headers=invalid_headers)
    assert response.status_code == 401

def test_create_extraction_job_without_token():
    response = requests.get(f"{API_URL}/document/extraction/create_job")
    assert response.status_code == 401

def test_register_file_with_invalid_token(invalid_headers):
    response = requests.post(f"{API_URL}/document/extraction/register_file", json=register_file_data, headers=invalid_headers)
    assert response.status_code == 401

def test_register_file_without_token():
    response = requests.post(f"{API_URL}/document/extraction/register_file", json=register_file_data)
    assert response.status_code == 401

def test_start_extraction_job_with_invalid_token(invalid_headers):
    response = requests.post(f"{API_URL}/document/extraction/start_job", json=start_job_data, headers=invalid_headers)
    assert response.status_code == 401

def test_start_extraction_job_without_token():
    response = requests.post(f"{API_URL}/document/extraction/start_job", json=start_job_data)
    assert response.status_code == 401

def test_get_job_files_with_invalid_token(invalid_headers):
    response = requests.get(f"{API_URL}/document/extraction/job_files/example_extraction_job_id", headers=invalid_headers)
    assert response.status_code == 401

def test_get_job_files_without_token():
    response = requests.get(f"{API_URL}/document/extraction/job_files/example_extraction_job_id")
    assert response.status_code == 401

def test_get_job_status_with_invalid_token(invalid_headers):
    response = requests.get(f"{API_URL}/document/extraction/job_status/example_extraction_job_id", headers=invalid_headers)
    assert response.status_code == 401

def test_get_job_status_without_token():
    response = requests.get(f"{API_URL}/document/extraction/job_status/example_extraction_job_id")
    assert response.status_code == 401

def test_get_file_status_with_invalid_token(invalid_headers):
    response = requests.post(f"{API_URL}/document/extraction/file_status", json=file_status_data, headers=invalid_headers)
    assert response.status_code == 401

def test_get_file_status_without_token():
    response = requests.post(f"{API_URL}/document/extraction/file_status", json=file_status_data)
    assert response.status_code == 401

def test_vector_store_with_invalid_token(invalid_headers):
    response = requests.post(f"{API_URL}/vector/store/create", json=vector_store_data, headers=invalid_headers)
    assert response.status_code == 401

def test_vector_store_without_token():
    response = requests.post(f"{API_URL}/vector/store/create", json=vector_store_data)
    assert response.status_code == 401

def test_prompt_template_with_invalid_token(invalid_headers):
    response = requests.post(f"{API_URL}/prompt/template/save", json=prompt_template_data, headers=invalid_headers)
    assert response.status_code == 401

def test_prompt_template_without_token():
    response = requests.post(f"{API_URL}/prompt/template/save", json=prompt_template_data)
    assert response.status_code == 401

if __name__ == "__main__":
    pytest.main(["-v", "test-service.py"])
