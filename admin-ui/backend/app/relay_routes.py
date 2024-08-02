# relay_routes.py
from fastapi import APIRouter, Request, Depends, HTTPException
from dependencies import verify_token, get_cognito_token
from utils import cognito_token_manager
from config import conf
import requests
from typing import Dict, Any, Type
from pydantic import BaseModel, create_model
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



router = APIRouter()
EXTERNAL_API_URL = conf.PLATFORM_BASE_URL.rstrip("/")

def generate_post_endpoints(openapi_spec: Dict[str, Any]):
    for path, path_item in openapi_spec.get("paths", {}).items():
        for method, operation in path_item.items():
            if method not in ["get", "post", "put", "delete"]:
                continue

            request_model = None
            if "requestBody" in operation:
                request_body = operation["requestBody"]
                if "application/json" in request_body["content"]:
                    schema = request_body["content"]["application/json"]["schema"]
                    request_model = create_model("")
                    
                path = '/admin' + path
                endpoint_function = create_relay_endpoint_function(path, method, request_model)
                router.add_api_route(path, endpoint_function, methods=[method.upper()])
            elif method == "post":
                path = '/admin' + path
                endpoint_function = create_relay_endpoint_function(path, method)
                router.add_api_route(path, endpoint_function, methods=[method.upper()])

def generate_get_endpoints():
    services = conf.PLARFORM_SERVICES
    for service, details in services.items():
        base_path = details.get("base_path") + "{full_path:path}" # => /admin/document/{full_path:path}
        endpoint_function = create_get_endpoint_function(base_path)
        router.add_api_route(base_path, endpoint_function, methods=["GET"])

def create_get_endpoint_function(path: str):
    async def get_ep(full_path: str, request: Request, payload: dict = Depends(verify_token), token: str = Depends(get_cognito_token)):
        headers = {"Authorization": f"Bearer {token}"}
        logger.info(f"Full path: {full_path}")
        logger.info(f"Eternal API URL: {EXTERNAL_API_URL}")
        logger.info(f"Base path: {path}")
        base_path = path.split("{")[0]
        url = f"{EXTERNAL_API_URL}{path}{full_path}".replace("/admin", "").replace("{full_path:path}", "")

        logger.info(f"Making GET request to {url} with headers {headers}")

        try:
            response = requests.get(url, headers=headers, timeout=120)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise HTTPException(status_code=500, detail="Internal Server Error")

        try:
            response_json = response.json()
        except ValueError:
            raise HTTPException(status_code=500, detail="Internal Server Error")

        return response_json

    return get_ep

def create_relay_endpoint_function(path: str, method: str, request_model: Type[BaseModel] = None):
    async def relay_ep(request: Request, payload: dict = Depends(verify_token), token: str = Depends(get_cognito_token)):
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{EXTERNAL_API_URL}{path}".replace("/admin", "")
        # url = f"{EXTERNAL_API_URL}{path}"
        response = None

        logger.info(f"Making {method.upper()} request to {url} with headers {headers}")

        if method == "get":
            response = requests.get(url, headers=headers, timeout=120)
            response.raise_for_status()
        elif method == "post":
            try:
                json_payload = await request.json() if request_model else {}
                response = requests.post(url, headers=headers, json=json_payload, timeout=120)
                response.raise_for_status()
            except Exception as e:
                json_payload = {}
        elif method == "put":
            json_payload = await request.json() if request_model else {}
            response = requests.put(url, headers=headers, json=json_payload, timeout=120)
            response.raise_for_status()
        elif method == "delete":
            response = requests.delete(url, headers=headers, timeout=120)
            response.raise_for_status()

        if response:
            return response.json()
        else:
            raise HTTPException(status_code=500, detail="Internal Server Error")

    return relay_ep

def init_relay_router():
    logger.info("Initializing relay router")
    spec = conf.OPENAPI_SPEC
    generate_post_endpoints(spec)
    generate_get_endpoints()
    logger.info("Relay router initialized")
    logger.info(router.routes)