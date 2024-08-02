import requests
import json
import logging
import time
import base64
import os
import re
import shutil
import tempfile

class CognitoTokenManager:
    def __init__(self):
        self.client_id = os.getenv('COGNITO_CLIENT_ID')
        self.client_secret = os.getenv('COGNITO_CLIENT_SECRET')
        self.user_pool_id = os.getenv('COGNITO_USER_POOL_ID')
        self.region = os.getenv('COGNITO_REGION')
        self.domain = os.getenv('COGNITO_DOMAIN')
        self.token = None
        self.expiry = 0

    def get_token(self):
        current_time = time.time()
        if self.token is None or current_time >= self.expiry:
            self.token = self._fetch_token_with_secret()
        return self.token

    def _fetch_token_with_secret(self):
        auth_header = base64.b64encode(f'{self.client_id}:{self.client_secret}'.encode('utf-8')).decode('utf-8')
        token_url = f'https://{self.domain}/oauth2/token'
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {auth_header}'
        }
        data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'scope': 'genaifoundations/read'
        }
        response = requests.post(token_url, headers=headers, data=data, timeout=60)
        if response.status_code == 200:
            token_data = response.json()
            self.expiry = time.time() + token_data['expires_in'] - 60  # Subtract 60 seconds to handle latency
            return token_data['access_token']
        else:
            raise Exception(f"Failed to get access token: {response.status_code} {response.text}")

class BaseService:
    def __init__(self, token_manager):
        self.base_url = os.getenv('PLATFORM_API_URL')
        # if base_url has a trailing slash, remove it
        if self.base_url[-1] == '/':
            self.base_url = self.base_url[:-1]
        self.token_manager = token_manager
        self.headers = {
            'Content-Type': 'application/json'
        }
        logging.basicConfig(level=logging.INFO)

    def _update_token(self):
        token = self.token_manager.get_token()
        self.headers['Authorization'] = f'Bearer {token}'

    def _request(self, method, endpoint, **kwargs):
        self._update_token()
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.request(method, url, headers=self.headers, **kwargs, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            logging.error(f"HTTP error occurred: {http_err}")
            raise
        except Exception as err:
            logging.error(f"An error occurred: {err}")
            raise

class HealthService(BaseService):
    def check_health(self, service):
        return self._request("GET", f"/{service}/service/health")

class ModelService(BaseService):
    def list_models(self):
        return self._request("GET", "/model/list_models")

    def invoke_model(self, model_name, prompt, **kwargs):
        data = {
            "model_name": model_name,
            "prompt": prompt,
        }
        data.update(kwargs)
        return self._request("POST", "/model/invoke", json=data)

    def invoke_model_with_raw_input(self, model_id, raw_input):
        data = {
            "model_id": model_id,
            "raw_input": raw_input
        }
        return self._request("POST", "/model/invoke_with_raw_input", json=data)

    def invoke_embed(self, model_name, input_text):
        data = {
            "model_name": model_name,
            "input_text": input_text
        }
        return self._request("POST", "/model/embed", json=data)

class DocumentService(BaseService):
    ALLOWED_FILE_TYPES = {'pdf', 'jpg', 'jpeg', 'png', 'tiff', 'txt', 'md', 'html'}

    def sanitize_filename(self, filename):
        safe_filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)
        return safe_filename

    def is_allowed_file_type(self, filename):
        ext = filename.split('.')[-1].lower()
        return ext in self.ALLOWED_FILE_TYPES

    def initiate_extraction_from_folder(self, local_folder_path):
        if not os.path.isdir(local_folder_path):
            raise ValueError(f"The provided path '{local_folder_path}' is not a valid directory.")
        
        extraction_job = self.create_extraction_job()
        extraction_job_id = extraction_job['extraction_job_id']

        with tempfile.TemporaryDirectory() as tmp_dir:
            for file_name in os.listdir(local_folder_path):
                if os.path.isfile(os.path.join(local_folder_path, file_name)) and self.is_allowed_file_type(file_name):
                    safe_file_name = self.sanitize_filename(file_name)
                    shutil.copy(os.path.join(local_folder_path, file_name), os.path.join(tmp_dir, safe_file_name))
                    
                    register_response = self.register_file_for_extraction(extraction_job_id, safe_file_name)
                    upload_url = register_response['upload_url']
                    
                    with open(os.path.join(tmp_dir, safe_file_name), 'rb') as f:
                        response = requests.put(upload_url, data=f)
                        if response.status_code != 200:
                            raise Exception(f"Failed to upload {safe_file_name} to {upload_url}")
            
            self.start_extraction_job(extraction_job_id)
        
        return extraction_job_id

    def get_extraction_job_status(self, extraction_job_id):
        return self._request("GET", f"/document/extraction/job_status/{extraction_job_id}")

    def create_extraction_job(self):
        return self._request("GET", "/document/extraction/create_job")

    def create_chunking_job(self, extraction_job_id, chunking_strategy, chunking_params=None):
        data = {
            "extraction_job_id": extraction_job_id,
            "chunking_strategy": chunking_strategy
        }
        if chunking_params is not None:
            data["chunking_params"] = chunking_params
        
        return self._request("POST", "/document/chunking/create_job", json=data)

    def register_file_for_extraction(self, extraction_job_id, file_name):
        data = {
            "extraction_job_id": extraction_job_id,
            "file_name": file_name
        }
        return self._request("POST", "/document/extraction/register_file", json=data)

    def start_extraction_job(self, extraction_job_id):
        data = {
            "extraction_job_id": extraction_job_id
        }
        return self._request("POST", "/document/extraction/start_job", json=data)

    def get_files_for_extraction_job(self, extraction_job_id):
        return self._request("GET", f"/document/extraction/job_files/{extraction_job_id}")

    def get_file_status(self, extraction_job_id, file_name):
        data = {
            "extraction_job_id": extraction_job_id,
            "file_name": file_name
        }
        return self._request("POST", "/document/extraction/file_status", json=data)

    def get_chunking_job_status(self, job_id):
        return self._request("GET", f"/document/chunking/job_status/{job_id}")

    def get_files_for_chunking_job(self, job_id):
        return self._request("GET", f"/document/chunking/job_files/{job_id}")

    def get_chunking_results(self, chunking_job_id, file_name):
        data = {
            "chunking_job_id": chunking_job_id,
            "file_name": file_name
        }
        return self._request("POST", "/document/chunking/chunk_file_url", json=data)

    def get_extraction_job_results(self, extraction_job_id):
        return self._request("GET", f"/document/extraction/job_results/{extraction_job_id}")

class VectorService(BaseService):
    def create_vector_store(self, store_name, store_type, description=None, tags=None):
        data = {
            "store_name": store_name,
            "store_type": store_type
        }
        if description is not None:
            data["description"] = description
        if tags is not None:
            data["tags"] = tags
        
        return self._request("POST", "/vector/store/create", json=data)

    def get_vector_store_status(self, store_id):
        data = {
            "store_id": store_id
        }
        return self._request("POST", "/vector/store/status", json=data)

    def get_vector_index_status(self, index_id):
        data = {
            "index_id": index_id
        }
        return self._request("POST", "/vector/store/index/status", json=data)

    def create_vector_index(self, store_id, index_name):
        data = {
            "store_id": store_id,
            "index_name": index_name
        }
        return self._request("POST", "/vector/store/index/create", json=data)

    def vectorize(self, chunking_job_id, index_id):
        data = {
            "chunking_job_id": chunking_job_id,
            "index_id": index_id
        }
        return self._request("POST", "/vector/store/vectorize", json=data)

    def get_vectorize_job_status(self, vectorize_job_id):
        return self._request("GET", f"/vector/job/status/{vectorize_job_id}")

    def semantic_search(self, query, index_id):
        data = {
            "query": query,
            "index_id": index_id
        }
        return self._request("POST", "/vector/search", json=data)

class PromptService(BaseService):
    def create_prompt_template(self, name, prompt_template):
        data = {
            "name": name,
            "prompt_template": prompt_template
        }
        return self._request("POST", "/prompt/template/save", json=data)

    def get_prompt_template(self, name):
        data = {
            "name": name
        }
        return self._request("POST", "/prompt/template/get", json=data)

    def get_all_prompt_templates(self, name):
        data = {
            "name": name
        }
        return self._request("POST", "/prompt/template/versions", json=data)

    def get_prompt_template_version(self, name, vnum):
        data = {
            "name": name,
            "vnum": vnum
        }
        return self._request("POST", "/prompt/template/version", json=data)

    def list_prompt_templates(self):
        return self._request("GET", "/prompt/template/list")

class GenerativeAIAccelerator:
    def __init__(self):
        token_manager = CognitoTokenManager()
        self.health_service = HealthService(token_manager)
        self.model_service = ModelService(token_manager)
        self.document_service = DocumentService(token_manager)
        self.vector_service = VectorService(token_manager)
        self.prompt_service = PromptService(token_manager)
