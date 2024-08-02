from fastapi import FastAPI, HTTPException, Depends, Request
import jwt
from typing import List, Optional, Dict, Any
import json
import boto3
from botocore.config import Config
import logging
import uuid
from datetime import datetime
from utils.opensearchutil import OpenSearchServerlessManager, OpenSearchVectorDB
import os
import requests
from models import *
from dyntastic import A
import base64
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi import status
from pydantic import error_wrappers


# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Configuration for AWS SDK
REGION = ''
MAX_RETRIES = 10
ACCESS_ROLE_ARN = os.getenv('ACCESS_ROLE_ARN')
VECTOR_STORES_TABLE = os.getenv('VECTOR_STORES_TABLE')
VECTOR_STORES_INDEX_TABLE = os.getenv('VECTOR_STORES_INDEX_TABLE')
VECTORIZE_JOBS_TABLE = os.getenv('VECTORIZE_JOBS_TABLE')
VECTORIZE_JOB_FILES_TABLE = os.getenv('VECTORIZE_JOB_FILES_TABLE')
JOBS_QUEUE_URL = os.getenv('JOBS_QUEUE_URL')
ECS_METADATA_URL = os.getenv("ECS_CONTAINER_METADATA_URI_V4", "")
CHUNK_JOBS_TABLE = os.getenv('CHUNK_JOBS_TABLE')
CHUNK_JOB_FILES_TABLE = os.getenv('CHUNK_JOB_FILES_TABLE')
CLIENTS_TABLE = os.getenv('CLIENTS_TABLE')
AOSS_VPCE_ID = os.getenv('AOSS_VPCE_ID')


session = None
dynamodb = None
retry_config = Config(retries={"max_attempts": MAX_RETRIES, "mode": "standard"})
sqs_client = None
open_search_client = None

manager = None

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


def generate_short_uuid():
    uuid4 = uuid.uuid4()
    uuid_bytes = uuid4.bytes
    base64_uuid = base64.b32encode(uuid_bytes).rstrip(b'=')
    return base64_uuid.decode('utf-8').lower()


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

# Helper functions
def create_vector_store_entry(collection_name: str, host: str, store_type: str, app_id: str) -> str:
    vector_store = VectorStore(store_name=collection_name, app_id=app_id, host=host, store_type=store_type)
    vector_store.save()
    return vector_store.vector_store_id

def create_vector_store_index_entry(vector_store_id: str, index_name: str) -> str:
    vector_index = VectorIndex(vector_store_id=vector_store_id, index_name=index_name)
    vector_index.save()
    return vector_index.index_id


def create_vectorize_job_entry(vector_store_id: str, index_id: str, chunking_job_id: str, app_id: str) -> str:
    vectorize_job = VectorizationJobs(vector_store_id=vector_store_id, index_id=index_id, chunking_job_id=chunking_job_id, status="STARTED", total_file_count=0, queued_files=0, completed_file_count=0, failed_file_count=0, app_id=app_id)
    vectorize_job.save()
    return vectorize_job.vectorize_job_id


def create_vectorize_job_file_entry(vectorize_job_id: str, file_path: str) -> str:
    vectorize_job_file = VectorizationJobFiles(vectorize_job_id=vectorize_job_id, file_path=file_path, status="QUEUED")
    vectorize_job_file.save()
    return vectorize_job_file.vectorize_job_file_id

def get_vector_db(host: str, index_name: str, region: str) -> OpenSearchVectorDB:
    return OpenSearchVectorDB(host=host, index_name=index_name, region=region)


# API endpoints
@app.post("/vector/store/create", tags=["Vectorization"], response_model=CreateVectorStoreResponse)
async def create_opensearch_collection(request: CreateVectorStoreRequest, app_id: str = Depends(get_app_id_from_token)) -> Dict[str, Any]:

    """
    ## Endpoint to Create a Vector Store
    This endpoint creates a vector store and returns the store ID that can be used to create an index.

    ***
    ## Request Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | store_type          | str    | The type of the vector store.    |
    | description         | str    | The description of the vector store. |
    | tags                | Optional[Dict[str, str]] | Tags to associate with the vector store. |

    ***

    ## Example Request Body
    
        ```json
    
        {
            "store_type": "opensearchserverless",
            "description": "A vector store for semantic search.",
            "tags": {
                "environment": "production",
                "team": "data"
            }
        }
    
        ```

    ***
    ## Response Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | store_name          | str    | The name of the created store.   |
    | store_type          | str    | The type of the created store.   |
    | store_id            | str    | The ID of the created store.     |
    | message             | str    | A message indicating the status of the operation. |

    ***
    #### Errors

    - **400 Bad Request**: If the store type is not supported.
    - **500 Internal Server Error**: If there is an unexpected error during the creation of the vector store.


    """

    try:
        store_uuid = 'lp'+generate_short_uuid()

        if request.store_type == "opensearchserverless":
            encryption_policy_detail = manager.create_encryption_policy(
                name=store_uuid + "-ep",
                description="An encryption policy for logs collection",
                collection_pattern=store_uuid + "*"
            )
            

            network_policy_detail = manager.create_network_policy(
                name=store_uuid + "-np",
                description="Public access for logs collection",
                collection_pattern=store_uuid + "*",
                allow_public=False,
                vpce_id=AOSS_VPCE_ID
            )
            

            data_access_policy_detail = manager.create_data_access_policy(
                name=store_uuid + "-dp",
                description="Data access policy for logs collection",
                collection_pattern=store_uuid,
                index_name="",
                role_arn=ACCESS_ROLE_ARN
            )
            

            collection_detail = manager.create_collection(
                collection_name=store_uuid,
                description=request.description,
                standby_replicas="DISABLED",
                tags=request.tags
            )
            

            domain_part = collection_detail['arn'].split(':')[-1].split('/')[1]
            host = f"https://{domain_part}.{REGION}.aoss.amazonaws.com"

            vector_store_id = create_vector_store_entry(store_uuid, host, 'opensearchserverless', app_id)

            return CreateVectorStoreResponse(store_name=store_uuid, store_type=request.store_type, store_id=vector_store_id, message="Vector store created successfully")
        else:
            raise HTTPException(status_code=400, detail="Invalid store type")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating vector store: {str(e)}")

# POST /vector/store/status
@app.post("/vector/store/status", tags=["Vectorization"], response_model=VectorStoreStatusResponse)
async def get_opensearch_collection_status(request: VectorStoreStatusRequest, app_id: str = Depends(get_app_id_from_token)) -> Dict[str, str]:
    
        """
        ## Endpoint to Get Vector Store Status
        This endpoint returns the status of the specified vector store.
    
        ***
        ## Request Body
    
        | Field               | Type   | Description                      |
        |---------------------|--------|----------------------------------|
        | store_id            | str    | The ID of the vector store.      |
    
        ***
    
        ## Example Request Body
    
            ```json
        
            {
                "store_id": "b1c2b4c5-6d7e-8f9g-0h1i-2j3k4l5m6n7"
            }
        
            ```
    
        ***
        ## Response Body
    
        | Field               | Type   | Description                      |
        |---------------------|--------|----------------------------------|
        | store_id            | str    | The ID of the vector store.      |
        | status              | str    | The status of the vector store. Returns "ACTIVE", "CREATING", "DELETING", "FAILED" or "NOT_FOUND". |
    
        ***
        #### Errors
    
        - **404 Bad Request**: If the store is not found.
        - **403 Bad Request**: If the store does not belong to the app.
        - **500 Internal Server Error**: If there is an unexpected error during the retrieval of the vector store status.
    
        """
        try:
            logger.info(f"Store ID: {request.store_id}")
            vector_store = VectorStore.safe_get(request.store_id, app_id)
        
            if not vector_store:
                raise HTTPException(status_code=404, detail="Store not found")

            if vector_store.app_id != app_id:
                raise HTTPException(status_code=403, detail="Vector Store does not belong to the app")
        
            store_id = vector_store.vector_store_id
            collection_filter = {
                'name': vector_store.store_name
            }
            collections = open_search_client.list_collections(collectionFilters=collection_filter)

            

            if not collections['collectionSummaries']:
                return {"store_id": store_id, "status": "NOT_FOUND"}

            for collection in collections['collectionSummaries']:
                logger.info(f"Collection: {collection}")
                if collection['name'] == vector_store.store_name:
                    return {"store_id": store_id, "status": collection['status']}
            
            return {"store_id": store_id, "status": "NOT_FOUND"}
        
        except HTTPException as e:
            raise e
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error getting vector store status: {str(e)}")

@app.post("/vector/store/index/create", tags=["Vectorization"], response_model=CreateIndexResponse)
async def create_opensearch_index(request: CreateIndexRequest, app_id: str = Depends(get_app_id_from_token)):

    """
    ## Endpoint to Create an Index
    This endpoint creates an index in the specified vector store.

    ***
    ## Request Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | store_id            | str    | The ID of the vector store.      |
    | index_name          | str    | The name of the index to create. |

    ***
    ## Example Request Body
    
        ```json
    
        {
            "store_id": "b1c2b4c5-6d7e-8f9g-0h1i-2j3k4l5m6n7",
            "index_name": "my_index"
        }
    
        ```

    ***
    ## Response Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | index_name          | str    | The name of the created index.   |
    | index_id            | str    | The ID of the created index.     |
    | store_id            | str    | The ID of the vector store.      |
    | store_type          | str    | The type of the vector store.    |
    | message             | str    | A message indicating the status of the operation. |

    ***
    #### Errors

    - **404**: If the vector store is not found.
    - **500 Internal Server Error**: If there is an unexpected error during the creation of the vector store.
    
    """

    try:
        store_id = request.store_id
        vector_store = VectorStore.safe_get(store_id, app_id)

        if not vector_store:
            raise HTTPException(status_code=404, detail="Store not found")

        store_name = vector_store.store_name
        store_type = vector_store.store_type

        if store_type == "opensearchserverless":
            collections = open_search_client.list_collections()
            collection_id = next(
                (collection['id'] for collection in collections['collectionSummaries'] if collection['name'] == store_name),
                None
            )

            if collection_id is None:
                return {"message": "Collection not found"}

            host = f"https://{collection_id}.{REGION}.aoss.amazonaws.com"
            vector_db = get_vector_db(host, store_name, REGION)
            vector_db.create_index(request.index_name)

            index_id = create_vector_store_index_entry(store_id, request.index_name)

            return CreateIndexResponse(index_name=request.index_name, index_id=index_id, store_id=store_id, store_type=store_type, message="Index created successfully")
        else:
            raise HTTPException(status_code=400, detail="Invalid store type")
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating index: {str(e)}. Store may not be ready. Please try again.")

# POST /vector/store/index/status 
@app.post("/vector/store/index/status", tags=["Vectorization"])
async def get_opensearch_index_status(request: VectorIndexStatusRequest, app_id: str = Depends(get_app_id_from_token)) -> Dict[str, str]:

    """
    ## Endpoint to Get Index Status
    This endpoint returns the status of the specified index.

    ***
    ## Request Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | index_id            | str    | The ID of the index.             |

    ***
    ## Example Request Body

        ```json
    
        {
            "index_id": "b1c2b4c5-6d7e-8f9g-0h1i-2j3k4l5m6n7"
        }
    
        ```
    ***
    ## Response Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | index_id            | str    | The ID of the index.             |
    | status              | str    | The status of the index. Returns "ACTIVE" or "NOT_FOUND_OR_READY". |

    ***
    #### Errors

    - **404**: If the vector index or vector store is not found.
    - **500 Internal Server Error**: If there is an unexpected error during the retrieval of the index status.

    """


    try:
        index_id = request.index_id
        vector_index = VectorIndex.safe_get(index_id)

        if not vector_index:
            raise HTTPException(status_code=404, detail="Index not found")

        vector_store = VectorStore.safe_get(vector_index.vector_store_id, app_id)

        if not vector_store:
            raise HTTPException(status_code=404, detail="Store not found")

        index_name = vector_index.index_name

        vector_db = get_vector_db(vector_store.host, index_name, REGION)
        index_status = vector_db.get_index_status(index_name)

        logger.info(f"Index Status: {index_status}")

        return {"index_id": index_id, "status": 'ACTIVE'}
    
    except HTTPException as e:
        raise e
    except Exception as e:
        return {"index_id": index_id, "status": 'NOT_FOUND_OR_READY'}

# POST /vector/stores/list
@app.post("/vector/stores/list", tags=["Vectorization"])
async def list_vector_stores(app_id: str = Depends(get_app_id_from_token)) -> List[Dict[str, str]]:
    """
    ## Endpoint to List Vector Stores
    This endpoint returns a list of vector stores.

    ***
    ## Response Body

    [
        {
            "store_id": "<store_id>",
            "store_type": "<store_type>"
        }
    ]

    ***
    #### Errors

    - **500 Internal Server Error**: If there is an unexpected error during the retrieval of the vector stores.
    """
    
    try:
        vector_stores = VectorStore.query(A.app_id == app_id, index='app_id_index')
        return [{
            "store_id": vector_store.vector_store_id,
            "store_type": vector_store.store_type
        } for vector_store in vector_stores]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing vector stores: {str(e)}")

# GET /vector/store/{store_id}/indexes
@app.get("/vector/store/{store_id}/indexes", tags=["Vectorization"])
async def list_vector_store_indexes(store_id: str, app_id: str = Depends(get_app_id_from_token)) -> List[Dict[str, str]]:
    """
    ## Endpoint to List Vector Store Indexes
    This endpoint returns a list of indexes in the specified vector store.

    ***
    ## Request Parameters

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | store_id            | str    | The ID of the vector store.      |

    ***
    ## Response Body

    [
        {
            "index_id": "<index_id>",
            "index_name": "<index_name>"
        }
    ]

    ***
    #### Errors

    - **404**: If the vector store is not found.
    - **403**: If the vector store does not belong to the app.
    - **500 Internal Server Error**: If there is an unexpected error during the retrieval of the vector store indexes.
    
    """
    try:
        # get vector store
        vector_store = VectorStore.safe_get(store_id, app_id)
        if not vector_store:
            raise HTTPException(status_code=404, detail="Store not found")

        if vector_store.app_id != app_id:
            raise HTTPException(status_code=403, detail="Vector Store does not belong to the app")
        
        vector_indexes = VectorIndex.query(A.vector_store_id == store_id, index='vector_store_id-index')
        return [{
            "index_id": vector_index.index_id,
            "index_name": vector_index.index_name
        } for vector_index in vector_indexes]
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing vector store indexes: {str(e)}")


@app.post("/vector/store/vectorize", tags=["Vectorization"], response_model=VectorizationJobStatusResponse)
async def vectorize_and_store_chunk(request: VectorizeRequestChunkJobInput, app_id: str = Depends(get_app_id_from_token)) -> Dict[str, str]:
    """
    ## Endpoint to Vectorize and Store Chunks. 
    This endpoint triggers the vectorization and storage of chunks. It takes a reference to the chunking job that was completed and triggers the vectorization of the chunks.

    ***
    ## Request Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | chunking_job_id     | str    | The ID of the chunking job.      |
    | index_id            | str    | The ID of the index to store the vectors. |

    ***

    ## Example Request Body
        
            ```json
        
            {
                "chunking_job_id": "b1c2b4c5-6d7e-8f9g-0h1i-2j3k4l5m6n7",
                "index_id": "b1c2b4c5-6d7e-8f9g-0h1i-2j3k4l5m6n7"
            }
        
            ```
    ***
    ## Response Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | vectorize_job_id    | str    | The ID of the vectorization job. |
    | vector_store_id     | str    | The ID of the vector store.      |
    | index_id            | str    | The ID of the index.             |
    | chunking_job_id     | str    | The ID of the chunking job.      |
    | total_file_count    | int    | The total number of files to be vectorized. |
    | completed_file_count| int    | The number of files that have been vectorized. |
    | failed_file_count   | int    | The number of files that failed to be vectorized. |
    | status              | str    | The status of the vectorization job. |

    ***
    #### Errors

    - **400**: If the chunking job is not completed.
    - **403**: If the chunking job does not belong to the app.
    - **403**: If the vector index does not belong to the app.
    - **404**: Chunk job, index or store not found.
    - **500 Internal Server Error**: If there is an unexpected error during the vectorization process.

    """
    try:

        # get chunking job
        chunk_job = ChunkingJobs.safe_get(request.chunking_job_id)

        if not chunk_job:
            raise HTTPException(status_code=404, detail="Chunk job not found")

        # Check if chunk job is associated with the app
        if chunk_job.app_id != app_id:
            raise HTTPException(status_code=403, detail="Chunk job does not belong to the app")

        vector_index = VectorIndex.safe_get(request.index_id)

        if not vector_index:
            raise HTTPException(status_code=404, detail="Index not found")

        index_name = vector_index.index_name
        vector_store = VectorStore.safe_get(vector_index.vector_store_id, app_id)

        if not vector_store:
            raise HTTPException(status_code=404, detail="Store not found")

        if vector_store.app_id != app_id:
            raise HTTPException(status_code=403, detail="Vector Index does not belong to the app")

        store_id = vector_store.vector_store_id
        host = vector_store.host

        chunk_job = ChunkingJobs.safe_get(request.chunking_job_id)
        
        if not chunk_job:
            raise HTTPException(status_code=404, detail="Chunk job not found")

        if chunk_job.status != "COMPLETED":
            raise HTTPException(status_code=400, detail="Chunk job is not completed")

        chunk_files = ChunkingJobFiles.query(A.chunking_job_id == request.chunking_job_id, index = 'chunking_job_id-index')

        if not chunk_files:
            raise HTTPException(status_code=404, detail="Chunk files not found")
        
        chunk_files =[chunk_file for chunk_file in chunk_files]

        
        if len(chunk_files) != 0:
            vectorize_job_id = create_vectorize_job_entry(store_id, request.index_id, request.chunking_job_id, app_id)
            vectorize_job = VectorizationJobs.safe_get(vectorize_job_id)
            vectorize_job.total_file_count = len(chunk_files)
            vectorize_job.save()
        else:
            raise HTTPException(status_code=400, detail="No chunk files found")
        
        for item in chunk_files:
            if item.status == "COMPLETED":
                vectorize_file_id = create_vectorize_job_file_entry(store_id, item.file_path)
                message = {
                        "chunking_job_id": request.chunking_job_id,
                        "index_id": request.index_id,
                        "vector_store_id": store_id,
                        "host": host,
                        "file_path": item.file_path,
                        "app_id": app_id,
                        "file_id": vectorize_file_id,
                        "vectorize_job_id": vectorize_job_id,
                        "index_name": index_name
                    }
                sqs_client.send_message(
                    QueueUrl=JOBS_QUEUE_URL,
                    MessageBody=json.dumps(message),
                    MessageGroupId=str(uuid.uuid4()).replace("-", ""),
                    MessageDeduplicationId=str(uuid.uuid4()).replace("-", "")
                )
        
        return VectorizationJobStatusResponse(vectorize_job_id=vectorize_job_id, vector_store_id=store_id, index_id=request.index_id, chunking_job_id=request.chunking_job_id, total_file_count=len(chunk_files), completed_file_count=0, failed_file_count=0, status="STARTED")
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail="Error processing request")

## List vectorization jobs
@app.get("/vector/jobs/list", tags=["Vectorization"])
async def list_vectorization_jobs(app_id: str = Depends(get_app_id_from_token)):
    """
    ## Endpoint to List Vectorization Jobs
    This endpoint returns a list of vectorization jobs.

    ***
    ## Response Body

    List of json objects, each containing the following fields:

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | vectorize_job_id    | str    | The ID of the vectorization job. |
    | vector_store_id     | str    | The ID of the vector store.      |
    | index_id            | str    | The ID of the index.             |
    | chunking_job_id     | str    | The ID of the chunking job.      |
    | created_at          | str    | The timestamp when the job was created. |
    | status              | str    | The status of the vectorization job. |
    | total_file_count    | int    | The total number of files to be vectorized. |
    | queued_files        | int    | The number of files that are queued for vectorization. |
    | completed_file_count| int    | The number of files that have been vectorized. |
    | failed_file_count   | int    | The number of files that failed to be vectorized. |


    ***
    #### Errors

    - **500 Internal Server Error**: If there is an unexpected error during the retrieval of the vectorization jobs.

    """
    try:
        vectorize_jobs = VectorizationJobs.query(A.app_id == app_id, index='app_id-index')
        return [job.dict(
            exclude={'app_id'}
        ) for job in vectorize_jobs]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing vectorization jobs: {str(e)}")

## Vectorization job status check
@app.get("/vector/job/status/{vectorize_job_id}", tags=["Vectorization"], response_model=VectorizationJobStatusResponse)
async def get_vectorize_job_status(vectorize_job_id: str, app_id: str = Depends(get_app_id_from_token)) -> Dict[str, str]:

    """
    ## Endpoint to Get Vectorization Job Status
    This endpoint returns the status of a vectorization job.

    ***
    ## Request Parameters

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | vectorize_job_id    | str    | The ID of the vectorization job. |

    ***
    ## Response Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | vectorize_job_id    | str    | The ID of the vectorization job. |
    | vector_store_id     | str    | The ID of the vector store.      |
    | index_id            | str    | The ID of the index.             |
    | chunking_job_id     | str    | The ID of the chunking job.      |
    | total_file_count    | int    | The total number of files to be vectorized. |
    | completed_file_count| int    | The number of files that have been vectorized. |
    | failed_file_count   | int    | The number of files that failed to be vectorized. |
    | status              | str    | The status of the vectorization job. |

    ***
    #### Errors

    - **403**: If the vectorization job does not belong to the app.
    - **404**: If the vectorization job is not found.
    - **500 Internal Server Error**: If there is an unexpected error during the vectorization process.

    """
    vectorize_job = VectorizationJobs.safe_get(vectorize_job_id)
    if not vectorize_job:
        raise HTTPException(status_code=404, detail="Vectorize job not found")

    if vectorize_job.app_id != app_id:
        raise HTTPException(status_code=403, detail="Vectorize job does not belong to the app")
    
    vectorize_job_id = vectorize_job.vectorize_job_id
    vector_store_id = vectorize_job.vector_store_id
    index_id = vectorize_job.index_id
    chunking_job_id = vectorize_job.chunking_job_id
    total_file_count = vectorize_job.total_file_count
    completed_file_count = vectorize_job.completed_file_count
    failed_file_count = vectorize_job.failed_file_count

    return VectorizationJobStatusResponse(vectorize_job_id=vectorize_job_id, vector_store_id=vector_store_id, index_id=index_id, chunking_job_id=chunking_job_id, total_file_count=total_file_count, completed_file_count=completed_file_count, failed_file_count=failed_file_count, status=vectorize_job.status)


@app.post("/vector/search", tags=["Vectorization"])
async def semantic_search(request: SemanticSearchRequest, app_id: str = Depends(get_app_id_from_token)) -> List[Dict[str, Any]]:

    """
    ## Endpoint to Perform Semantic Search
    This endpoint performs a semantic search using the specified query.

    ***
    ## Request Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | query               | str    | The semantic search query.       |
    | index_id            | str    | The ID of the index to search.   |

    ***

    ## Example Request Body

        ```json
            
            {
                "query": "what is AWS?",
                "index_id": "b1c2b4c5-6d7e-8f9g-0h1i-2j3k4l5m6n7"
            }
    
            ```
    ***
    ## Response Body

    [
        {
            "text": "<text>",
        }
    ]

    ***

    Errors

    - **404**: If the vector index or vector store is not found.
    - **403**: If the vector index does not belong to the app.
    - **500 Internal Server Error**: If there is an unexpected error during the vectorization process.

    """
    vector_index = VectorIndex.safe_get(request.index_id)

    if not vector_index:
        raise HTTPException(status_code=404, detail="Index not found")

    index_name = vector_index.index_name
    vector_store = VectorStore.safe_get(vector_index.vector_store_id, app_id)

    if not vector_store:
        raise HTTPException(status_code=404, detail="Store not found")
    
    if vector_store.app_id != app_id:
        raise HTTPException(status_code=403, detail="Vector Index does not belong to the app")
    
    store_id = vector_store.vector_store_id
    host = vector_store.host
    store_name = vector_store.store_name

    vector_db = get_vector_db(host, index_name, REGION)
    results = vector_db.similarity_search(request.query, text_field="text", vector_field="vector_field")

    return results

@app.on_event("startup")
async def startup_event():
    global session, dynamodb, manager, sqs_client, REGION, open_search_client
    
    if not ECS_METADATA_URL:
        raise HTTPException(status_code=500, detail="ECS_CONTAINER_METADATA_URI_V4 environment variable not set.")

    try:
        response = requests.get(ECS_METADATA_URL, timeout=10)
        response.raise_for_status()
        metadata = response.json()
        REGION = metadata.get("Labels", {}).get("com.amazonaws.ecs.task-arn", "").split(":")[3]

        session = boto3.Session(region_name=REGION)
        dynamodb = session.client('dynamodb', config=retry_config)
        manager = OpenSearchServerlessManager(region_name=REGION)
        sqs_client = session.client('sqs')
        open_search_client = session.client('opensearchserverless')

        logger.info("Vector Processing Service started successfully.")
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving ECS metadata: {str(e)}")

@app.get("/vector/service/meta", include_in_schema=False)
async def get_metadata():
    return app.openapi()

@app.get("/vector/service/health", tags=["Health"])
async def health_check():
    return {"status": "UP"}
