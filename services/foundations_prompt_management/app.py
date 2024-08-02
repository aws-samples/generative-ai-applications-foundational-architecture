import boto3
import boto3.dynamodb
import boto3.dynamodb.conditions
import boto3.dynamodb.table
from botocore.exceptions import ClientError
import uuid
import requests
import logging
import jwt
import os
from fastapi import FastAPI, HTTPException, Depends, Request
from pydantic import BaseModel
from collections import defaultdict
from models import *
from dyntastic import A
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi import status
from pydantic import error_wrappers

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


ECS_METADATA_URL = os.getenv("ECS_CONTAINER_METADATA_URI_V4", "")
PROMPT_TEMPLATE_TABLE = os.getenv('PROMPT_TEMPLATE_TABLE') 
CLIENTS_TABLE = os.getenv('CLIENTS_TABLE')
COGNITO_JWKS_URL = ''

# Global variables. 
# clients_table = None
metadata = {}
dynamodb = None

app = FastAPI()


#################### COGNITO AUTHENTICATION ####################

def decode_token_without_verification(token: str):
    try:
        decoded_token = jwt.decode(token, options={"verify_signature": False})
        return decoded_token
    except jwt.DecodeError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_app_id_from_dynamodb(client_id: str):
    table = dynamodb.Table(CLIENTS_TABLE)
    response = table.scan()
    print(f"Response: {response}")
    items = response['Items']
    if not items:
        raise HTTPException(status_code=401, detail="No items found in DynamoDB")
    for item in items:
        if 'client_id' in item and client_id == item['client_id']:
            return item['app_id']

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

#################### END COGNITO AUTHENTICATION ####################



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

# Generate new version of prompt template
def get_new_version(template_name: str,app_id):
    try:
        response = PromptTemplate.query(
            hash_key=template_name,
            filter_condition=(A.app_id == app_id),
            scan_index_forward=False,
            )
        items = [item.model_dump() for item in response]
        if len(items) > 0:
            latest_version = items[0]['version']
            return latest_version + 1
        else:
            return 1
    except ClientError as e:
        logger.info(f"Error getting new version: {e.response['Error']['Message']}")
        raise HTTPException(status_code=500, detail=f"Client error: {e.response['Error']['Message']}")
    except Exception as e:
        logger.info(f"Error getting new version: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

# Health check endpoint
@app.get("/prompt/service/health", tags=["Health"])
async def health_check():
    return {"status": "UP"}

@app.get("/prompt/service/meta", include_in_schema=False)
async def get_metadata():
    return app.openapi()

@app.get("/prompt/",include_in_schema=False)
async def root():
    return "Welcome to the Prompt Management Service!"
  
# Create new prompt template
@app.post("/prompt/template/save",response_model=TemplateResponse, tags=["Prompt Management"])
async def create_prompt_template(request: CreatePromptTemplateRequest, app_id: str = Depends(get_app_id_from_token)):
    """
    ## Endpoint to Create a Prompt Template
    This endpoint creates a prompt template and returns the template ID.

    ***

    ## Request Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | name                | str    | The name of the prompt template. |
    | prompt_template     | str    | The prompt template.             |

    ***
    ## Example Request Body
    
        ```json
    
        {
            "name": "CHATBOT_PROMPT",
            "prompt_template": "Given the following information, answer the question. Context {context}. Question {question}"
        }
    
        ```
    ***
    ## Response Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | id                  | str    | The ID of the created prompt template. |
    | name                | str    | The name of the created prompt template. |
    | prompt_template     | str    | The prompt template.             |
    | version             | int    | The version of the created prompt template. |

    ***
    #### Errors

    - **500 Internal Server Error**: If there is an unexpected error during the creation of the prompt template.

    """
    try: 
        new_version = get_new_version(request.name,app_id)
        prompt_template = PromptTemplate(
            app_id = app_id,
            name = request.name,
            prompt_template = request.prompt_template,
            version = new_version
        )
        id = prompt_template.id
        prompt_template.save()
        return TemplateResponse(id = id,name = prompt_template.name, prompt_template = prompt_template.prompt_template,version = prompt_template.version)
    except Exception as e:
        error_message = f"Error creating prompt template: {str(e)}"
        logger.info(error_message)
        raise HTTPException(status_code=500, detail=error_message)
        

# get latest version of template for a given app_id
@app.post("/prompt/template/get", response_model=TemplateResponse, tags=["Prompt Management"])
async def get_prompt_template(request: GetPromptTemplateRequest, app_id: str = Depends(get_app_id_from_token)):
    """
    ## Endpoint to Get a Prompt Template
    This endpoint gets the latest version of a prompt template by name.

    ***
    ## Request Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | name                | str    | The name of the prompt template. |

    ***
    ## Example Request Body
    
        ```json
    
        {
            "name": "CHATBOT_PROMPT"
        }
    
        ```
    ***
    ## Response Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | id                  | str    | The ID of the prompt template. |
    | name                | str    | The name of the prompt template. |
    | prompt_template     | str    | The prompt template.             |
    | version             | int    | The version of the prompt template. |

    ***
    #### Errors

    - **404 Not Found**: If the prompt template is not found.
    - **500 Internal Server Error**: If there is an unexpected error during the retrieval of the prompt template.

    """
    try:
        response = PromptTemplate.query(
            hash_key=request.name,
            filter_condition= A.app_id == app_id,
            scan_index_forward = False
        )
        
        sorted_output = sorted(response, key=lambda x: x.version, reverse=True)
        if len(sorted_output) == 0:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        response = sorted_output[0]
        return  TemplateResponse(id = response.id, name = response.name, prompt_template = response.prompt_template, version = response.version)

    except HTTPException as e:
        raise e    
    except Exception as e:
        print(e.response['Error']['Message'])
        raise HTTPException(status_code=500, detail="Error retrieving prompt template")
    
# get all versions of template for a given app_id
@app.post("/prompt/template/versions", response_model=list[TemplateResponse], tags=["Prompt Management"])
async def get_all_prompt_template(request: GetPromptTemplateRequest, app_id: str = Depends(get_app_id_from_token)):
    """
    ## Endpoint to Get All Versions of a Prompt Template
    This endpoint gets all versions of a prompt template by name.

    ***
    ## Request Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | name                | str    | The name of the prompt template. |

    ***
    ## Example Request Body
    
        ```json
    
        {
            "name": "CHATBOT_PROMPT"
        }
    
        ```
    ***

    ## Response Body

    [
        {
            "id": <str>,
            "name": <str>,
            "prompt_template": <str>,
            "version": <int>
        }
    ]
    """
    try:
        response = PromptTemplate.query(
            hash_key=request.name,
            filter_condition= A.app_id == app_id,
            scan_index_forward = False
        )

        prompts=[prompt.model_dump() for prompt in response]
        if len(prompts) == 0:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        return [TemplateResponse(id = item['id'], name = item['name'], prompt_template = item['prompt_template'], version = item['version']) for item in prompts]
    except HTTPException as e:
        raise e  
    except Exception as e:
        print(e.response['Error']['Message'])
        raise HTTPException(status_code=500, detail="Error retrieving prompt template")

# get specific version of template for a given app_id 
@app.post("/prompt/template/version" , response_model=TemplateResponse, tags=["Prompt Management"])
async def get_prompt_template_version(request: GetPromptTemplateRequestByVersion, app_id: str = Depends(get_app_id_from_token)):
    """ 
    ## Endpoint to Get a Specific Version of a Prompt Template
    This endpoint gets a specific version of a prompt template by name and version.

    ***
    ## Request Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | name                | str    | The name of the prompt template. |
    | vnum                | int    | The version of the prompt template. |

    ***

    ## Example Request Body
        
            ```json
        
            {
                "name": "CHATBOT_PROMPT",
                "vnum": 1
            }

            ```
    ***
    ## Response Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | id                  | str    | The ID of the prompt template. |
    | name                | str    | The name of the prompt template. |
    | prompt_template     | str    | The prompt template.             |
    | version             | int    | The version of the prompt template. |

    ***
    #### Errors

    - **404 Not Found**: If the prompt template version is not found.
    - **500 Internal Server Error**: If there is an unexpected error during the retrieval of the prompt template version.

    """
    try:
        vnum = request.vnum
        response = PromptTemplate.query(
            hash_key=request.name,
            range_key_condition=A.version == vnum,
            filter_condition= A.app_id == app_id
        )
        
        template = next(response, None)
        if template is None:
            raise HTTPException(status_code=404, detail="Prompt template version not found")
        return TemplateResponse(id = template.id, name = template.name, prompt_template = template.prompt_template, version = template.version)
    except HTTPException as e:
        raise e 
    except Exception as e:
        print(e.response['Error']['Message'])
        raise HTTPException(status_code=500, detail="Error retrieving prompt template")
# handle excetption for non-existing version

# List all templates
@app.get("/prompt/template/list", tags=["Prompt Management"])
async def list_prompt_template(app_id: str = Depends(get_app_id_from_token)):
    """
    ## Endpoint to List All Prompt Templates
    This endpoint lists all prompt templates.

    ***
    ## Response Body
    ```json
    {
        "<template_name>": [
            {
                "version": <int>,
                "prompt_template": <str>
            }
        ]
    }
    ```

    ***
    #### Errors

    - **500 Internal Server Error**: If there is an unexpected error during the listing of prompt templates.

    """
    try:
        response = PromptTemplate.query(
            A.app_id == app_id,
            index='app_id-name-index',
            scan_index_forward = False
        )
        grouped_items = defaultdict(list)
        for item in response:
            grouped_items[item.name].append({
                'version': item.version,
                'prompt_template': item.prompt_template
            })

        structured_response = {
            name: versions
            for name, versions in grouped_items.items()
        }

        return structured_response
        
    except ClientError as e:
        print(e.response['Error']['Message'])
        raise HTTPException(status_code=500, detail="Error listing prompt template")
    
@app.on_event("startup")
async def startup_event():
    global metadata,dynamodb, COGNITO_JWKS_URL, clients_table

    if not ECS_METADATA_URL:
        raise HTTPException(status_code=500, detail="ECS_CONTAINER_METADATA_URI_V4 environment variable not set.")

    try:
        response = requests.get(ECS_METADATA_URL, timeout=10)
        response.raise_for_status()
        metadata = response.json()
        region_name = metadata.get("Labels", {}).get("com.amazonaws.ecs.task-arn", "").split(":")[3]
        dynamodb = boto3.resource('dynamodb',region_name=region_name)
        table = dynamodb.Table(PROMPT_TEMPLATE_TABLE)

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving ECS metadata: {str(e)}")