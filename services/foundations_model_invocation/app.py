import json
import logging
import uuid
import os
from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional, Union
import boto3
from botocore.config import Config
from pydantic import BaseModel, validator, Field
import jwt
from jwt.algorithms import RSAAlgorithm
from boto3.dynamodb.conditions import Key
import datetime
from models import *
import requests
import redis
import asyncio
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi import status
from pydantic import error_wrappers


from adapters import input_adapters, output_adapters, StandardInput, StandardOutput, model_id_map

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants and environment variables
COGNITO_USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')
LOGGING_TABLE = os.getenv('LOGGING_TABLE')
CLIENTS_TABLE = os.getenv('CLIENTS_TABLE')
MAX_RETRIES = 10
ECS_METADATA_URL = os.getenv("ECS_CONTAINER_METADATA_URI_V4", "")
REDIS_URL = os.getenv("REDIS_URL")
REDIS_PORT = os.getenv("REDIS_PORT")


# Global variables. Initialized in the startup event function.
clients_table = None
session = None
bedrock_client = None
dynamodb = None
redis_client = None


app = FastAPI()

retry_config = Config(retries={"max_attempts": MAX_RETRIES, "mode": "standard"})

#################### COGNITO TOKEN PROCESSING ####################

def decode_token_without_verification(token: str):
    try:
        decoded_token = jwt.decode(token, options={"verify_signature": False})
        return decoded_token
    except jwt.DecodeError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_app_id_from_dynamodb(client_id: str):
    response = dynamodb.scan(TableName=CLIENTS_TABLE)
    items = response['Items']
    if not items:
        raise HTTPException(status_code=401, detail="No items found in DynamoDB")
    for item in items:
        if 'client_id' in item and client_id == item['client_id']['S']:
            return item['app_id']['S']
    raise HTTPException(status_code=401, detail="Client ID not found in DynamoDB")

async def get_app_id_from_token(request: Request):

    authorization: str = request.headers.get("Authorization")
    if authorization is None:
        raise HTTPException(status_code=401, detail="Authorization header missing")

    token = authorization.replace("Bearer ", "")
    decoded_token = decode_token_without_verification(token)
    try:
        client_id = decoded_token['client_id']
        app_id = get_app_id_from_dynamodb(client_id)
        return app_id
    except KeyError:
        raise HTTPException(status_code=401, detail="Client ID not found in token")

#################### END COGNITO TOKEN PROCESSING ####################

def save_invocation_log(model_name, model_id, input_tokens, output_tokens, status, error_message, app_id):
    invocation = ModelInvocationLogs(
        model_name=model_name,
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        status=status,
        error_message=error_message,
        app_id=app_id
    )
    invocation.save()
    return invocation.invocation_id



def invoke_model_and_log(model_name: str, model_id: str, adapted_input: dict, app_id: str, log_success=True):
    try:
        logger.info(f"Invoking model: {model_name}")
        response = bedrock_client.invoke_model(
            body=json.dumps(adapted_input),
            modelId=model_id
        )
        logger.info(f"Response: {response}")
        response_body = json.loads(response['body'].read())
        adapted_output = output_adapters[model_name](response_body)

        if log_success:
            save_invocation_log(
                model_name=model_name,
                model_id=model_id,
                input_tokens=adapted_output.input_tokens,
                output_tokens=adapted_output.output_tokens,
                status="SUCCESS",
                error_message="NA",
                app_id=app_id
            )

        return adapted_output

    except Exception as e:
        save_invocation_log(
            model_name=model_name,
            model_id=model_id,
            input_tokens=0,
            output_tokens=0,
            status="FAILED",
            error_message=str(e),
            app_id=app_id
        )
        raise e

def async_invoke_model(model_name: str, model_id: str, adapted_input: dict, app_id: str, invocation_id: str):
    try:

        logger.info(f"Invoking model asynchronously: {model_name}")
        ## Set Redis IN_PROGRESS
        redis_client.set(invocation_id, json.dumps({"status": "IN_PROGRESS"}), ex=3600)
        response = bedrock_client.invoke_model(
            body=json.dumps(adapted_input),
            modelId=model_id
        )
        logger.info(f"Response: {response}")
        response_body = json.loads(response['body'].read())
        adapted_output = output_adapters[model_name](response_body)
        redis_client.set(invocation_id, json.dumps({"status": "SUCCESS", "result": adapted_output.dict(),"app_id": app_id}), ex=3600)
        logger.info(f"Saved result in Redis: {adapted_output.dict()}")

        save_invocation_log(
            model_name=model_name,
            model_id=model_id,
            input_tokens=adapted_output.input_tokens,
            output_tokens=adapted_output.output_tokens,
            status="SUCCESS",
            error_message="NA",
            app_id=app_id
        )
        logger.info(f"Saved invocation log in DynamoDB")
    except Exception as e:
        logger.info(f"Error invoking model: {e}")
        redis_client.set(invocation_id, json.dumps({"status": "FAILED", "error": str(e)}), ex=3600)
        save_invocation_log(
            model_name=model_name,
            model_id=model_id,
            input_tokens=0,
            output_tokens=0,
            status="FAILED",
            error_message=str(e),
            app_id=app_id
        )
        raise e

@app.post("/model/async_invoke", tags=["Model Invocation"])
async def async_invoke_model_endpoint(request: InvokeModelRequest, background_tasks: BackgroundTasks, app_id: str = Depends(get_app_id_from_token)):

    """
    ## Endpoint to Invoke a Model on Bedrock Asynchronously
    This endpoint allows users to invoke a model on Bedrock asynchronously using either a simple text prompt or a series of messages. It returns an invocation ID that can be used to retrieve the result later.

    ***

    ## Request Body

    | Parameter       | Type                                                      | Description                                                                                           |
    |-----------------|-----------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
    | model_name      | str                                                       | The name of the model to invoke. Must be one of the supported models.                                  |
    | prompt          | str                                                       | A simple text prompt (str) or a list of messages (see below for message format).                       |
    | max_tokens      | Optional[int]                                             | The maximum number of tokens to generate in the response.                                             |
    | temperature     | Optional[float]                                           | Sampling temperature to use. Higher values make the output more random.                                |
    | top_p           | Optional[float]                                           | Probability threshold for nucleus sampling.                                                           |
    | top_k           | Optional[int]                                             | The number of highest probability vocabulary tokens to keep for top-k filtering.                       |
    | stop_sequences  | Optional[List[str]]                                       | Sequences where the generation will stop.                                                             |


    ***

    #### Example:

    ```json
    {
        "model_name": "example_model",
        "prompt": "Translate the following text to French: 'Hello, how are you?'",
        "max_tokens": 100,
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 50,
        "stop_sequences": ["\\n"]
    }
    ```
    ***
    ## Response Body

    | Field          | Type   | Description                          |
    |----------------|--------|--------------------------------------|
    | invocation_id  | str    | The ID of the asynchronous invocation.|

    ***
    #### Errors

    - **400 Bad Request**: If the request parameters are invalid.
    - **500 Internal Server Error**: If there is an unexpected error during model invocation.

    """

    try:
        logger.info(f"Received async request: {request.dict()}")
        logger.info(f"App ID: {app_id}")

        if request.model_name not in input_adapters or request.model_name not in output_adapters:
            raise HTTPException(status_code=400, detail=f"Unsupported model: {request.model_name}")

        model_id = model_id_map.get(request.model_name)
        if not model_id:
            raise HTTPException(status_code=400, detail=f"Model ID not found for model: {request.model_name}")

        standard_input = StandardInput(
            model_name=request.model_name,
            prompt=request.prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            top_p=request.top_p,
            top_k=request.top_k,
            stop_sequences=request.stop_sequences
        )

        adapted_input = input_adapters[request.model_name](standard_input)

        invocation_id = str(uuid.uuid4())
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, async_invoke_model, request.model_name, model_id, adapted_input, app_id, invocation_id)

        return {"invocation_id": invocation_id}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error invoking model: {str(e)}")

@app.get("/model/async_output/{invocation_id}", tags=["Model Invocation"])
async def get_async_output(invocation_id: str, app_id: str = Depends(get_app_id_from_token)):
    """
    ## Endpoint to Retrieve the Result of an Asynchronous Model Invocation
    This endpoint allows users to retrieve the result of an asynchronous model invocation using the invocation ID returned by the async_invoke endpoint.

    ***
    ## Path Parameters

    | Parameter       | Type   | Description                          |
    |-----------------|--------|--------------------------------------|
    | invocation_id   | str    | The ID of the asynchronous invocation.|

    ***
    ## Response Body

    | Field          | Type   | Description                          |
    |----------------|--------|--------------------------------------|
    | status         | str    | The status of the invocation (SUCCESS or FAILED).|
    | result         | dict   | The result of the invocation.|

    ***
    #### Errors

    - **404 Not Found**: If the invocation ID is not found or the result has expired.
    - **500 Internal Server Error**: If there is an unexpected error retrieving the result.
    """
    try:
        result = redis_client.get(invocation_id)
        result = json.loads(result) if result else None
        if result:
            invocation_app_id = result.get("app_id") if result else None
            if invocation_app_id:
                if invocation_app_id != app_id:
                    raise HTTPException(status_code=401, detail="Unauthorized access to result")
                else:
                    result = result.get("result")
            else:
                raise HTTPException(status_code=404, detail="Invocation ID not found or result expired")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving result: {str(e)}")
    if result is None:
        raise HTTPException(status_code=404, detail="Invocation ID not found or result expired")
    return JSONResponse(content=result)


@app.exception_handler(RequestValidationError)
async def format_validation_error_as_rfc_7807_json(request: Request, exc: error_wrappers.ValidationError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    errors = exc.errors()
    cleaned_errors = [{k: v for k, v in error.items() if k != "input"} for error in errors]
    content = {
        "type": f"/errors/unprocessable_entity",
        "title": "Unprocessable Entity",
        "status": status_code,
        "detail": "The request is invalid.",
        "instance": request.url.path,
        "issues": jsonable_encoder(cleaned_errors),
    }
    return JSONResponse(content, status_code=status_code)

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    logger.error(f"HTTPException: {exc.detail}")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

@app.get("/model/service/health", tags=["Health"])
async def health_check():
    return {"status": "UP"}

@app.get("/model/service/meta", include_in_schema=False)
async def get_metadata():
    return app.openapi()

@app.get("/model/", include_in_schema=False)
async def root():
    return "Welcome to the Model Invocation Service!"

@app.get("/model/list_models", tags=["Model Invocation"])
async def list_models(app_id: str = Depends(get_app_id_from_token)):
    """ 
    ### Endpoint to List Supported Models and Their Model Names and Model IDs

    ***

    #### Returns
    - **List[Dict[str, str]]**: A list of supported models with their names and IDs.

    ***

    #### Response Body

    {
        "text_models": [
            {
                "model_name": "model_name",
                "model_id": "model_id"
                }
        ],
        "embed_models": [
            {
                "model_name": "model_name",
                "model_id": "model_id"
            }
        ]
    }

    ***

    #### Errors

    - **500 Internal Server Error**: If there is an unexpected error listing the models.

    ***

    #### Notes

    """
    try:
        text_models = [{"model_name": model_name, "model_id": model_id} for model_name, model_id in model_id_map.items() if "EMBED" not in model_name]
        embed_models = [{"model_name": model_name, "model_id": model_id} for model_name, model_id in model_id_map.items() if "EMBED" in model_name]
        # return [{"model_name": model_name, "model_id": model_id} for model_name, model_id in model_id_map.items()]
        return {"text_models": text_models, "embed_models": embed_models}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Unexpected error listing models")

@app.post("/model/invoke", tags=["Model Invocation"])
async def invoke_model(request: InvokeModelRequest, app_id: str = Depends(get_app_id_from_token)):
    """
    ## Endpoint to Invoke a Model on Bedrock with Standardized Input
    This endpoint allows users to invoke a model on Bedrock using either a simple text prompt or a series of messages. The request can include various optional parameters to control the model's behavior.

    ***

    ## Request Body

    | Parameter       | Type                                                      | Description                                                                                           |
    |-----------------|-----------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
    | model_name      | str                                                       | The name of the model to invoke. Must be one of the supported models.                                  |
    | prompt          | Union[str, List[Dict[str, Union[str, List[Dict[str, str]]]]]] | A simple text prompt (str) or a list of messages (see below for message format).                       |
    | max_tokens      | Optional[int]                                             | The maximum number of tokens to generate in the response.                                             |
    | temperature     | Optional[float]                                           | Sampling temperature to use. Higher values make the output more random.                                |
    | top_p           | Optional[float]                                           | Probability threshold for nucleus sampling.                                                           |
    | top_k           | Optional[int]                                             | The number of highest probability vocabulary tokens to keep for top-k filtering.                       |
    | stop_sequences  | Optional[List[str]]                                       | Sequences where the generation will stop.                                                             |
    | system_prompts  | Optional[List[Dict[str, str]]]                            | A list of dictionaries for system prompts, each with a single key "text".                              |

    ***
    
    #### Message Format for Prompt

    | Parameter | Type              | Description                                                        |
    |-----------|-------------------|--------------------------------------------------------------------|
    | role      | str               | The role of the message sender (e.g., "user", "assistant").        |
    | content   | List[Dict[str, str]] | A list of dictionaries, each containing a "text" key with the message content. |

    ***

    #### Example 1: Simple Text Prompt
    ```json
    { 
        "model_name": "example_model", 
        "prompt": "Translate the following text to French: 'Hello, how are you?'", 
        "max_tokens": 100, 
        "temperature": 0.7, 
        "top_p": 0.9, 
        "top_k": 50, 
        "stop_sequences": ["\\n"] 
    }
    ```

    #### Example 2: Messages

    ```json
    { 
        "model_name": "example_model", 
        "prompt": [ 
            { 
                "role": "user", 
                "content": [{"text": "What is the weather like today?"}] 
            }, 
            { 
                "role": "assistant", 
                "content": [{"text": "The weather is sunny with a high of 25°C."}] 
            } 
        ], 
        "max_tokens": 100, 
        "temperature": 0.7, 
        "top_p": 0.9, 
        "top_k": 50, 
        "stop_sequences": ["\\n"], 
        "system_prompts": [ 
            { 
                "text": "Your system prompt here" 
            } 
        ] 
    }
    ```

    ***

    ## Response Body

    | Field          | Type   | Description                          |
    |----------------|--------|--------------------------------------|
    | output_text    | str    | The generated text.                  |
    | input_tokens   | str    | The number of input tokens used.     |
    | output_tokens  | str    | The number of output tokens generated.|

    ***

    #### Errors

    - **400 Bad Request**: If the request parameters are invalid.
    - **401 Unauthorized**: If the authorization header is missing or invalid.
    - **500 Internal Server Error**: If there is an unexpected error during model invocation.

    ***

    #### Notes

    
    """
    
    logger.info(f"Received request: {request.dict()}")
    logger.info(f"App ID: {app_id}")

    if request.model_name not in input_adapters or request.model_name not in output_adapters:
        raise HTTPException(status_code=400, detail=f"Unsupported model: {request.model_name}")

    logger.info(f"Model ID Map: {model_id_map}")

    model_id = model_id_map.get(request.model_name)
    if not model_id:
        raise HTTPException(status_code=400, detail=f"Model ID not found for model: {request.model_name}")

    logger.info(f"Model ID: {model_id}")

    standard_input = StandardInput(
        model_name=request.model_name,
        prompt=request.prompt,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        top_p=request.top_p,
        top_k=request.top_k,
        stop_sequences=request.stop_sequences
    )

    logger.info(f"Standard Input: {standard_input.dict()}")

    adapted_input = input_adapters[request.model_name](standard_input)

    if isinstance(request.prompt, list):  # Handle messages input

        if request.model_name in ["AI21_JURASSIC_2_ULTRA", "AI21_JURASSIC_2_MID", "COHERE_COMMAND_LIGHT_TEXT_V14", "COHERE_COMMAND_TEXT_V14"]:
            if len(request.prompt) > 1:
                request.prompt = [request.prompt[-1]]

        inference_config = {}
        if request.max_tokens:
            inference_config["maxTokens"] = request.max_tokens
        if request.temperature:
            inference_config["temperature"] = request.temperature
        if request.top_p:
            inference_config["topP"] = request.top_p
        if request.stop_sequences:
            inference_config["stopSequences"] = request.stop_sequences

        additional_model_request_fields = {}
        if request.top_k and request.model_name != 'MISTRAL_LARGE_V1:0':
            if 'ANTHROPIC' in request.model_name or 'MISTRAL' in request.model_name:
                additional_model_request_fields["top_k"] = request.top_k
            elif 'COHERE' in request.model_name:
                additional_model_request_fields["k"] = request.top_k

        messages = request.prompt
        system_prompts = request.system_prompts if request.system_prompts else []

        try:
            response = bedrock_client.converse(
                modelId=model_id,
                messages=messages,
                system=system_prompts,
                inferenceConfig=inference_config if inference_config else {},
                additionalModelRequestFields=additional_model_request_fields if additional_model_request_fields else {}
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error invoking model: {str(e)}")

        logger.info(f"Response: {response}")

        # Check if the keys are present in the response
        if "output" not in response or "usage" not in response:
            raise HTTPException(status_code=500, detail="Unexpected response from model")
        
        output_text =""
        if "message" in response["output"] and "content" in response["output"]["message"] and len(response["output"]["message"]["content"]) > 0:
            output_text = response["output"]["message"]["content"][0]["text"]

        adapted_output = StandardOutput(
            output_text=output_text,
            input_tokens=response["usage"]["inputTokens"],
            output_tokens=response["usage"]["outputTokens"]
        )

        save_invocation_log(
            model_name=request.model_name,
            model_id=model_id,
            input_tokens=adapted_output.input_tokens,
            output_tokens=adapted_output.output_tokens,
            status="SUCCESS",
            error_message="NA",
            app_id=app_id
        )

    else:  # Handle text input
        adapted_output = invoke_model_and_log(request.model_name, model_id, adapted_input, app_id)

    logger.info(f"Adapted Output: {adapted_output.dict()}")
    return adapted_output.dict(exclude_none=True)

@app.post("/model/embed", tags=["Model Invocation"])
async def invoke_embed(request: InvokeEmbedModelRequest, app_id: str = Depends(get_app_id_from_token)):
    """
    ## Endpoint to Invoke Embed Models
    This endpoint allows users to invoke embed models.

    ***

    #### Request Body

    | Parameter    | Type       | Description                                                      |
    |--------------|------------|------------------------------------------------------------------|
    | model_name   | str        | The name of the model to invoke. Must be one of the supported models. |
    | input_text   | str        | The text to embed.                                               |

    ***

    #### Response Body

    | Field          | Type   | Description                          |
    |----------------|--------|--------------------------------------|
    | output_text    | str    | The generated text.                  |
    | input_tokens   | str    | The number of input tokens used.     |
    | output_tokens  | str    | The number of output tokens generated.|

    ***

    #### Errors

    - **400 Bad Request**: If the request parameters are invalid.
    - **401 Unauthorized**: If the authorization header is missing or invalid.
    - **500 Internal Server Error**: If there is an unexpected error during model invocation.

    ***

    #### Notes

    
    """
    
    if request.model_name not in input_adapters or request.model_name not in output_adapters:
        raise HTTPException(status_code=400, detail=f"Unsupported model: {request.model_name}")

    model_id = model_id_map.get(request.model_name)
    if not model_id:
        raise HTTPException(status_code=400, detail=f"Model ID not found for model: {request.model_name}")

    if 'EMBED' not in request.model_name:
        raise HTTPException(status_code=400, detail=f"Model is not an embed model: {request.model_name}")

    standard_input = StandardInput(
        model_name=request.model_name,
        text_to_embed=request.input_text,
        dimensions=0,
        normalize=False,
        texts=[],
        input_type='',
        truncate=''
    )
    

    adapted_input = input_adapters[request.model_name](standard_input)
    adapted_output = invoke_model_and_log(request.model_name, model_id, adapted_input, app_id)
    return adapted_output.dict(exclude_none=True)

@app.on_event("startup")
async def fetch_metadata():
    global session, bedrock_client, dynamodb, redis_client

    if not ECS_METADATA_URL:
        raise HTTPException(status_code=500, detail="ECS_CONTAINER_METADATA_URI_V4 environment variable not set.")

    try:
        response = requests.get(ECS_METADATA_URL, timeout=10)
        response.raise_for_status()
        metadata = response.json()
        region_name = metadata.get("Labels", {}).get("com.amazonaws.ecs.task-arn", "").split(":")[3]

        session = boto3.Session(region_name=region_name)
        bedrock_client = session.client(service_name='bedrock-runtime', config=retry_config)
        dynamodb = session.client('dynamodb', region_name=region_name)

        redis_client = redis.Redis(host=REDIS_URL, port=REDIS_PORT, decode_responses=True, ssl=True)

        # Not used currently, but can be used to validate the JWT token
        COGNITO_JWKS_URL = f'https://cognito-idp.{region_name}.amazonaws.com/{COGNITO_USER_POOL_ID}/.well-known/jwks.json'

        logger.info("Model Invocation Service started successfully.")
        logger.info(f"Region: {region_name}")
        logger.info(f"COGNITO_JWKS_URL: {COGNITO_JWKS_URL}")
        logger.info(f"CLIENTS_TABLE: {CLIENTS_TABLE}")
        logger.info(f"LOGGING_TABLE: {LOGGING_TABLE}")
        logger.info(f"COGNITO_USER_POOL_ID: {COGNITO_USER_POOL_ID}")

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving ECS metadata: {str(e)}")

