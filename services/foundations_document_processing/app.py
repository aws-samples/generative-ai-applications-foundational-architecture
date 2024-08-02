import json
import logging
import uuid
import os
from fastapi import FastAPI, HTTPException, Depends, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, List, Optional, Union
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
import jwt
import logging
import datetime
import requests
from enum import Enum
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
COGNITO_USER_POOL_ID = os.getenv('COGNITO_USER_POOL_ID')
CLIENTS_TABLE = os.getenv('CLIENTS_TABLE')
RESULTS_BUCKET_NAME = os.getenv('RESULTS_BUCKET_NAME')
SOURCE_BUCKET_NAME = os.getenv('SOURCE_BUCKET_NAME')
EXTRACTION_JOBS_TABLE = os.getenv('EXTRACTION_JOBS_TABLE')
EXTRACTION_JOB_FILES_TABLE = os.getenv('EXTRACTION_JOB_FILES_TABLE')
QUEUE_URL = os.getenv('QUEUE_URL')
CHUNKING_JOBS_TABLE = os.getenv('CHUNKING_JOBS_TABLE')
CHUNKING_JOBS_FILES_TABLE = os.getenv('CHUNKING_JOBS_FILES_TABLE')
CHUNKING_QUEUE_URL = os.getenv('CHUNKING_QUEUE_URL')


MAX_RETRIES = 10
COGNITO_JWKS_URL = ''

# Global variables
session = None
s3_client = None
dynamodb = None

app = FastAPI()

retry_config = Config(retries={"max_attempts": MAX_RETRIES, "mode": "standard"})


def check_s3_file_access(file_path: str) -> bool:
    try:
        s3_client.head_object(Bucket=SOURCE_BUCKET_NAME, Key=file_path)
        return True
    except Exception as e:
        return False

def generate_presigned_url(bucket: str, key: str, expiration: int = 3600) -> str:
    response = s3_client.generate_presigned_url(
        ClientMethod='put_object',
        Params={'Bucket': bucket, 'Key': key},
        ExpiresIn=expiration
    )
    return response

def generate_presigned_url_get(bucket: str, key: str, expiration: int = 3600) -> str:
    response = s3_client.generate_presigned_url(
        ClientMethod='get_object',
        Params={'Bucket': bucket, 'Key': key},
        ExpiresIn=expiration
    )
    return response

def add_file_to_queue(file_path: str, job_id: str, file_name: str, app_id: str):
    sqs = boto3.client('sqs')
    response = sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps({"file_path": file_path, "job_id": job_id, "app_id": app_id}),
        MessageGroupId=str(uuid.uuid4()),
        MessageDeduplicationId=str(uuid.uuid4())
    )

    extraction_job_file = ExtractionJobFiles.safe_get(job_id, file_name)
    if extraction_job_file:
        extraction_job_file.status = "QUEUED"
        extraction_job_file.save()
        logger.info(f"File {file_path} added to queue successfully.")
        return response
    else:
        raise HTTPException(status_code=404, detail="File not found")

def get_job_files(job_id: str):
    extraction_job_files = ExtractionJobFiles.query(A.job_id == job_id, index='job_id-index')
    return extraction_job_files


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
    
# Get the total file count and list of file names for the provided extraction job
def get_completed_files(job_id: str):
    try:

        logger.info(f"Getting completed files for job_id: {job_id}")

        job_files = ExtractionJobFiles.query(A.job_id == job_id, index='job_id-index')

        job_files = [file for file in job_files]
        if len(job_files) == 0:
            return 0, []

        completed_files = [item for item in job_files if item.status == 'COMPLETED']
        file_names = [item.file_name for item in completed_files]
        return len(file_names), file_names

    except ClientError as e:
            raise HTTPException(status_code=500, detail="Internal Server Error")

# Check if chunking job already exists
def check_chunking_job_exists(job_id: str) -> bool:
    try:

        chunking_job = ChunkingJobs.query(A.extraction_job_id == job_id, index='extraction_job_id-index')
        chunking_jobs = [job for job in chunking_job if job.status == 'WAITING_QUEUE_ALLOCATION']
        if len(chunking_jobs) > 0:
            return True
        return False
        
    except ClientError as e:
            logger.error(f"Unable to query item: {e.response['Error']['Message']}")
            return False

# add files to sqs for chunking
def add_files_to_sqs_for_chunking(chunk_job_id: str,extraction_job_id: str,chunking_strategy: str,chunking_params: Optional[ChunkingParams],app_id: str, file_names: List[str]):
    try:
        queue_url = CHUNKING_QUEUE_URL

        for file_name in file_names:
            chunk_job_file_id =  str(uuid.uuid4()).replace("-", "")
            message_body = {
                "chunking_job_id": chunk_job_id,
                "extraction_job_id": extraction_job_id,
                "chunking_strategy": chunking_strategy,
                "chunking_params": chunking_params.dict() if chunking_params else {},
                "app_id": app_id,
                "file_name": file_name,
                "file_path": f"{app_id}/{extraction_job_id}/{file_name}/{'extracted_text.json'}",
                "chunk_job_file_id": chunk_job_file_id
            }
            

            chunk_job_file = ChunkingJobFiles(
                chunk_job_file_id=chunk_job_file_id,
                chunking_job_id=chunk_job_id,
                app_id=app_id,
                file_name=file_name,
                file_path=f"{app_id}/{extraction_job_id}/{file_name}/{'chunk_'}{chunk_job_id}{'.json'}",
                file_id = str(uuid.uuid4()).replace("-", ""),
                status="QUEUED"
            )
            chunk_job_file.save()
            
            # Send message to SQS queue
            sqs = boto3.client('sqs')
            sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(message_body),
                MessageGroupId=chunk_job_id,
                MessageDeduplicationId=str(uuid.uuid4())
            )
        
        chunk_job = ChunkingJobs.safe_get(chunk_job_id)
        if not chunk_job:
            raise HTTPException(status_code=404, detail="Chunk job not found")
        chunk_job.status = "QUEUED"
        chunk_job.queued_files = len(file_names)
        chunk_job.save()


    except Exception as e:
            raise HTTPException(status_code=500, detail="Internal Server Error")


@app.get("/document/extraction/create_job", tags=["Extraction"], response_model=CreateExtractionResponse)
async def create_extraction_job(app_id: str = Depends(get_app_id_from_token)):
    """
    ## Endpoint to Create an Extraction Job
    This endpoint creates an extraction job and returns the job ID that can be used to get the status of the job.

    ***

    ## Response Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | extraction_job_id   | str    | The ID of the created job.       |
    | status              | str    | The status of the created job. Returns CREATED if the job is created successfully. |

    ***

    #### Errors

    - **500 Internal Server Error**: If there is an unexpected error during the creation of the extraction job.

    """
    try:
        extraction_job = ExtractionJobs(
            status="CREATED",
            app_id=app_id,
            total_file_count=0,
            queued_files=0,
            completed_file_count=0,
            failed_file_count=0
        )
        job_id = extraction_job.job_id
        extraction_job.save()
        logger.info(f"Extraction job with job ID: {job_id} created successfully.")
        return CreateExtractionResponse(extraction_job_id=job_id, status="CREATED")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error creating extraction job")



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

# API endpoint to create chunking job
@app.post("/document/chunking/create_job", tags=["Chunking"], response_model=CreateChunkingJobResponse)
async def create_chunking_job(request: CreateChunkingJobRequest, background_task: BackgroundTasks, app_id: str = Depends(get_app_id_from_token)):
    """
    ## Endpoint to Create a Chunking Job
    This endpoint creates a chunking job and returns the job ID that can be used to get the status of the job.

    ***

    ## Request Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | extraction_job_id   | str    | The ID of the extraction job.    |
    | chunking_strategy   | str    | The chunking strategy to use.    |
    | chunking_params     | Optional[ChunkingParams] | Optional parameters for the chunking strategy. |

    ***

    #### Chunking Strategies

    - **fixed_size**: Chunks the file into fixed-size segments.
    - **recursive**: Recursively splits the file into smaller segments based on a delimiter.

    ***

    #### Chunking Parameters

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | chunk_size          | int    | The size of each chunk in character. |
    | chunk_overlap       | int    | The number of overlapping characters between chunks. |

    ***

    ## Example Request Body

    ```json

    {
        "extraction_job_id": "123456",
        "chunking_strategy": "fixed_size",
        "chunking_params": {
            "chunk_size": 1000,
            "chunk_overlap": 100
        }
    }

    ```

    ***

    ## Response Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | chunking_job_id     | str    | The ID of the created job.       |
    | extraction_job_id   | str    | The ID of the extraction job.     |
    | status              | str    | The status of the created job. Returns WAITING_QUEUE_ALLOCATION if the job is created successfully. |
    | total_file_count    | int    | The total number of files to be chunked. |

    ***

    #### Errors

    - **400 Bad Request**: If a chunking job with status 'WAITING_QUEUE_ALLOCATION' already exists.
    - **400 Bad Request**: If the extraction job is not in COMPLETED or COMPLETED_WITH_ERRORS state.
    - **404 Not Found**: If the extraction job is not found.
    - **403 Forbidden**: If the extraction job does not belong to the app.
    - **500 Internal Server Error**: If there is an unexpected error during the creation of the chunking job.

    """

    try:
        # Get the extraction job
        extraction_job = ExtractionJobs.safe_get(request.extraction_job_id)
        if not extraction_job:
            raise HTTPException(status_code=404, detail="Extraction job not found")

        # Check if extraction_job is associated with the app_id
        if extraction_job.app_id != app_id:
            raise HTTPException(status_code=403, detail="Extraction job does not belong to the app")

        # check if chunking job already exists
        if check_chunking_job_exists(request.extraction_job_id):
            raise HTTPException(status_code=400, detail="A chunking job with status 'WAITING_QUEUE_ALLOCATION' already exists")

        if extraction_job.status not in ['COMPLETED', 'COMPLETED_WITH_ERRORS']:
            raise HTTPException(status_code=400, detail="Extraction job is not in COMPLETED or COMPLETED_WITH_ERRORS state")

        
        # get completed files
        file_count, file_names = get_completed_files(request.extraction_job_id)

        chunk_job = ChunkingJobs(
            extraction_job_id=request.extraction_job_id,
            app_id=app_id,
            status="WAITING_QUEUE_ALLOCATION",
            chunking_strategy=request.chunking_strategy.value,
            chunking_params=str(request.chunking_params.dict()) if request.chunking_params else '',
            total_file_count=file_count,
            queued_files=0,
            completed_files=0,
            failed_files=0
        )
        chunk_job_id = chunk_job.chunking_job_id

        chunk_job.save()

        background_task.add_task(add_files_to_sqs_for_chunking, chunk_job_id, request.extraction_job_id, request.chunking_strategy, request.chunking_params, app_id, file_names)

        return CreateChunkingJobResponse(chunking_job_id=chunk_job_id, extraction_job_id=request.extraction_job_id, status="WAITING_QUEUE_ALLOCATION", total_file_count=file_count)

    except HTTPException as e:
        logger.error(f"Error creating chunking job: {e}")
        raise e
    except Exception as e:
            raise HTTPException(status_code=500, detail="Error creating chunking job")

@app.post("/document/extraction/register_file", tags=["Extraction"], response_model=RegisterFileResponse)
async def register_file(
    req: RegisterFileRequest,
    app_id: str = Depends(get_app_id_from_token)
):
    """
    ## Endpoint to Register a File for Extraction
    This endpoint registers a file for extraction and returns a presigned URL for the file upload.

    ***

    ## Request Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | extraction_job_id   | str    | The ID of the extraction job.    |
    | file_name           | str    | The name of the file to register. |

    ***

    ## Response Body

     | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | extraction_job_id   | str    | The ID of the extraction job.    |
    | file_name           | str    | The name of the registered file. |
    | file_id             | str    | The ID of the registered file.   |
    | upload_url          | str    | The presigned URL for file upload. |

    ***

    #### Errors

    - **400 Bad Request**: If the file name is invalid or already registered for the job.
    - **403 Forbidden**: If the extraction job does not belong to the app.
    - **404 Not Found**: If the extraction job is not found.
    - **500 Internal Server Error**: If there is an unexpected error during the registration of the file.

    ***

    Note: The file name should not contain any of the following characters: <space> & $ @ = ; / : + , ? \ { } ^ ] " > [ ~ < # | %

    """
    try:

        # Retrieve 
        extraction_job = ExtractionJobs.safe_get(req.extraction_job_id)
        if not extraction_job:
            raise HTTPException(status_code=404, detail="Extraction job not found")

        # Check if extraction_job is associated with the app_id
        if extraction_job.app_id != app_id:
            raise HTTPException(status_code=403, detail="Extraction job does not belong to the app")

        # Check if the job is in a valid state to register files
        if extraction_job.status != "CREATED":
            raise HTTPException(status_code=400, detail="Job is already started or completed. Please create a new job.")

        # Check if valid file name
        file_name = req.file_name
        if not file_name:
            raise HTTPException(status_code=400, detail="Invalid file name")
        ## Check file type
        allowed_file_types = ['pdf', 'txt', 'md', 'html', 'json', 'jsonl', 'png', 'jpg', 'jpeg', 'tiff']
        file_type = file_name.split('.')[-1].lower()
        if file_type not in allowed_file_types:
            raise HTTPException(status_code=400, detail="Invalid file type. Supported file types are pdf, txt, md, html, json")
                   
        # Check if file_name has any characters from avoid_chars
        avoid_chars = ["&", "$", "@", "=", ";", "/", ":", "+", " ", ",", "?", "\\", "{", "}", "^", "]", "\"", ">", "[", "~", "<", "#", "|", "%"]
        if any(char in file_name for char in avoid_chars):
            raise HTTPException(status_code=400, detail="Invalid file name. Following characters are not allowed in the file name: <space> & $ @ = ; / : + , ? \\ { } ^ ] \" > [ ~ < # | %")
        # Check if the file is already registered for the job
        extraction_job_file = ExtractionJobFiles.safe_get(req.extraction_job_id, req.file_name)
        if extraction_job_file:
            raise HTTPException(status_code=400, detail="A file with the same name is already registered for this job")

        # Generate file ID and file key
        file_id = str(uuid.uuid4()).replace("-", "")
        extension = req.file_name.split(".")[-1]
        file_key = f"{app_id}/{req.extraction_job_id}/{file_name}"

        # Generate presigned URL for file upload
        presigned_url = generate_presigned_url(SOURCE_BUCKET_NAME, file_key)

        # Create and save the extraction job file record
        extraction_job_file = ExtractionJobFiles(
            job_id=req.extraction_job_id,
            file_name=req.file_name,
            file_path=file_key,
            file_id=file_id,
            status="PENDING"
        )
        extraction_job_file.save()

        
        # Update the extraction job record
        extraction_job.total_file_count += 1
        extraction_job.save()

        # Log success and return response
        logger.info(f"File {req.file_name} registered successfully for job {req.extraction_job_id}.")
        return RegisterFileResponse(
            extraction_job_id=req.extraction_job_id,
            file_name=req.file_name,
            file_id=file_id,
            upload_url=presigned_url
        )
    except HTTPException as http_err:
        raise http_err
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error registering file: {e}")


@app.post("/document/extraction/start_job", tags=["Extraction"], response_model=StartExtractionJobResponse)
async def start_extraction_job(req: StartExtractionJobRequest, app_id: str = Depends(get_app_id_from_token)):
    """
    ## Endpoint to Start an Extraction Job
    This endpoint starts an extraction job by adding all registered files to the SQS queue for processing.

    ***

    ## Request Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | extraction_job_id   | str    | The ID of the extraction job.    |

    ***

    ## Response Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | extraction_job_id   | str    | The ID of the extraction job.    |
    | total_files         | int    | The total number of files registered for the job. |
    | status              | str    | The status of the extraction job. Returns STARTED if the job is started successfully. |

    ***

    #### Errors

    - **400**: If the job is already started or completed.
    - **400**: If no files are registered for the job.
    - **400**: If any of the registered files are not uploaded to S3 using the presigned URL.
    - **403**: If the extraction job does not belong to the app.
    - **404**: If the job ID is not found.
    - **500**: If any other error occurs during the start process.


    """
    try:
        job_id = req.extraction_job_id

        # Retrieve the extraction job
        extraction_job = ExtractionJobs.safe_get(job_id)
        if not extraction_job:
            raise HTTPException(status_code=404, detail="Extraction job not found")

        # Check if extraction_job is associated with the app_id
        if extraction_job.app_id != app_id:
            raise HTTPException(status_code=403, detail="Extraction job does not belong to the app")

        # Check if the job is in a valid state to be started
        if extraction_job.status != "CREATED":
            raise HTTPException(status_code=400, detail="Job is either already started or completed. Please create a new job.")

        # Retrieve files associated with the job
        job_files = [file for file in get_job_files(job_id)]

        # Validate all files in S3
        invalid_files = [file.file_path for file in job_files if not check_s3_file_access(file.file_path)]
        if invalid_files:
            raise HTTPException(status_code=400, detail=f"Files not uploaded: {', '.join(invalid_files)}")
        
        
        # Add files to the SQS queue
        if len(job_files) == 0:
            raise HTTPException(status_code=400, detail="No files registered for the job. Please register and upload files before starting the job.")
        
        file_count = len(job_files)
        for file in job_files:
            add_file_to_queue(file.file_path, job_id, file.file_name, app_id)

        # Update and save the extraction job status
        extraction_job.status = "STARTED"
        extraction_job.total_file_count = file_count
        extraction_job.queued_files = file_count
        extraction_job.save()

        logger.info(f"Extraction job with job ID: {job_id} started successfully.")
        return StartExtractionJobResponse(extraction_job_id=job_id, total_files=file_count, status="STARTED")
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error starting extraction job")


@app.get("/document/extraction/job_files/{extraction_job_id}", tags=["Extraction"], response_model=List[GetExtractionJobFilesResponse])
async def get_files_for_job(extraction_job_id:str, app_id: str = Depends(get_app_id_from_token)):
    """ 
    ## Endpoint to Get Files for an Extraction Job
    This endpoint returns a list of files registered for an extraction job.

    ***

    ## Request Parameters

    | Parameter           | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | extraction_job_id   | str    | The ID of the extraction job.    |

    ***

    ## Response Body
    List of json objects, each containing the following fields:

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | job_id              | str    | The ID of the extraction job.    |
    | file_name           | str    | The name of the file.            |
    | status              | str    | The status of the file. Can be COMPLETED, QUEUED, or FAILED. |

    ***

    #### Errors

    - **403**: If the extraction job does not belong to the app.
    - **404**: If the job ID is not found or no files are found for the job.
    - **500**: If any other error occurs during the retrieval of files.

    """
    try:

        # get extraction job
        extraction_job = ExtractionJobs.safe_get(extraction_job_id)
        if not extraction_job:
            raise HTTPException(status_code=404, detail="Extraction job not found")

        # Check if extraction_job is associated with the app_id
        if extraction_job.app_id != app_id:
            raise HTTPException(status_code=403, detail="Extraction job does not belong to the app")

        files = get_job_files(extraction_job_id)
        if not files:
            raise HTTPException(status_code=404, detail="No files found for the job")
        response = []
        # return files
        for file in files:
            response.append(GetExtractionJobFilesResponse(
                job_id=file.job_id,
                file_name=file.file_name,
                status=file.status
            ))
        return response
    
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting files for job: {e}")

# Get the status of a extraction job
@app.get("/document/extraction/job_status/{extraction_job_id}", tags=["Extraction"], response_model=ExtractionJobStatusResponse)
async def get_job_status(extraction_job_id: str, app_id: str = Depends(get_app_id_from_token)):
    """ 
    ## Endpoint to Get the Status of an Extraction Job
    This endpoint returns the status of an extraction job.

    ***

    ## Request Parameters

    | Parameter           | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | extraction_job_id   | str    | The ID of the extraction job.    |

    ***

    ## Response Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | job_id              | str    | The ID of the extraction job.    |
    | completed_file_count| int    | The number of files completed.   |
    | total_file_count    | int    | The total number of files.       |
    | failed_file_count   | int    | The number of files failed.      |
    | status              | str    | The status of the extraction job. Can be CREATED, STARTED, IN_PROGRESS, COMPLETED, or COMPLETED_WITH_ERRORS.          |

    ***

    #### Errors

    - **403**: If the extraction job does not belong to the app.
    - **404**: If the job ID is not found.
    - **500**: If any other error occurs during the retrieval of the job status.


    """
    try:
        extraction_job = ExtractionJobs.safe_get(extraction_job_id)
        if not extraction_job:
            raise HTTPException(status_code=404, detail="Extraction job not found")

        # Check if extraction_job is associated with the app_id
        if extraction_job.app_id != app_id:
            raise HTTPException(status_code=403, detail="Extraction job does not belong to the app")
        
        return ExtractionJobStatusResponse(
            job_id=extraction_job.job_id,
            completed_file_count=extraction_job.completed_file_count,
            total_file_count=extraction_job.total_file_count,
            failed_file_count=extraction_job.failed_file_count,
            status=extraction_job.status
        )

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting job status")
    
# Get the status of a file from extraction job
@app.post("/document/extraction/file_status", tags=["Extraction"], response_model=ExtractionJobFileResponse)
async def get_file_status(req: ExtractionJobFileRequest, app_id: str = Depends(get_app_id_from_token)):
    """
    ## Endpoint to Get the Status of a File from an Extraction Job
    This endpoint returns the status of a file from an extraction job.

    ***

    ## Request Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | extraction_job_id   | str    | The ID of the extraction job.    |
    | file_name           | str    | The name of the file.            |

    ***

    ## Response Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | extraction_job_id   | str    | The ID of the extraction job.    |
    | status              | str    | The status of the file. Can be COMPLETED or QUEUED. |
    | result_url          | str    | The presigned URL for the extracted text file. |

    ***

    #### Errors

    - **404**: If the file is not found.
    - **500**: If any other error occurs during the retrieval of the file status.


    """
    try:
        extraction_job_id = req.extraction_job_id
        file_name = req.file_name

        # Get extraction job
        extraction_job = ExtractionJobs.safe_get(extraction_job_id)
        if not extraction_job:
            raise HTTPException(status_code=404, detail="Extraction job not found")

        # Check if extraction_job is associated with the app_id
        if extraction_job.app_id != app_id:
            raise HTTPException(status_code=401, detail="Extraction job does not belong to the app")


        response = ExtractionJobFiles.safe_get(extraction_job_id, file_name)
        if not response:
            raise HTTPException(status_code=404, detail="File not found")
        status = response.status
        if status == "COMPLETED":
            file_path = f"{app_id}/{extraction_job_id}/{file_name}/extracted_text.json"
            try:
                file_url = generate_presigned_url_get(RESULTS_BUCKET_NAME, file_path)
            except ClientError as e:
                raise HTTPException(status_code=500, detail="Error generating pre-signed URL")
        else:
            file_url = None
        return ExtractionJobFileResponse(status=status, result_url=file_url, extraction_job_id=extraction_job_id)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting file status")



# Get the status of a chunk job
@app.get("/document/chunking/job_status/{job_id}", tags=["Chunking"])
async def get_job_status(job_id: str, app_id: str = Depends(get_app_id_from_token)):
    """ 
    ## Endpoint to Get the Status of a Chunking Job
    This endpoint returns the status of a chunking job.

    ***

    ## Request Parameters

    | Parameter           | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | job_id              | str    | The ID of the chunking job.      |

    ***

    ## Response Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | chunking_job_id     | str    | The ID of the chunking job.      |
    | status              | str    | The status of the chunking job. Can be QUEUED, IN_PROGRESS, COMPLETED, or FAILED. |
    | total_file_count    | int    | The total number of files to be chunked. |
    | completed_files     | int    | The number of files completed.   |
    | failed_files        | int    | The number of files failed.      |

    ***

    #### Errors

    - **403**: If the chunking job does not belong to the app.
    - **404**: If the job ID is not found.
    - **500**: If any other error occurs during the retrieval of the job status.

    """
    try:
        job = ChunkingJobs.safe_get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Chunking job not found")

        # Check if chunking_job is associated with the app_id
        if job.app_id != app_id:
            raise HTTPException(status_code=403, detail="Chunking job does not belong to the app")

        return_obj = {
            "chunking_job_id": job.chunking_job_id,
            "status": job.status,
            "total_file_count": job.total_file_count,
            "completed_files": job.completed_files,
            "failed_files": job.failed_files,
        }
        return return_obj
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting job status")


# Get list of files for a chunk job
@app.get("/document/chunking/job_files/{job_id}", tags=["Chunking"])
async def get_files_for_chunk_job(job_id: str, app_id: str = Depends(get_app_id_from_token)):
    """ 
    ## Endpoint to Get Files for a Chunking Job
    This endpoint returns a list of files associated with a chunking job.

    ***

    ## Request Parameters

    | Parameter           | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | job_id              | str    | The ID of the chunking job.      |

    ***

    ## Response Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | chunking_job_id     | str    | The ID of the chunking job.      |
    | files               | List   | List of files associated with the job. Each file contains the following fields: file_name, status, timestamp. |

    ***

    #### Errors

    - **400**: If no files are found for the job.
    - **403**: If the chunking job does not belong to the app.
    - **404**: If the job ID is not found.
    - **500**: If any other error occurs during the retrieval of files.


    """
    try:

        # Get chunking job
        chunk_job = ChunkingJobs.safe_get(job_id)
        if not chunk_job:
            raise HTTPException(status_code=404, detail="Chunking job not found")

        # Check if chunking_job is associated with the app_id
        if chunk_job.app_id != app_id:
            raise HTTPException(status_code=403, detail="Chunking job does not belong to the app")

        job_files = ChunkingJobFiles.query(A.chunking_job_id == job_id, index='chunking_job_id-index')
        
        if not job_files:
            raise HTTPException(status_code=400, detail="No files found for job")

        return_obj = {}
        return_obj["chunking_job_id"] = job_id
        return_obj["files"] = []
        for file in job_files:
            file_obj = {
                "file_name": file.file_name,
                "status": file.status,
                "timestamp": file.timestamp
            }
            return_obj["files"].append(file_obj)
        return return_obj
    
    except HTTPException as e:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting files for job")


@app.post("/document/chunking/chunk_file_url", tags=["Chunking"])
async def get_chunk_job_results(req:GetFileChunksRequest, app_id: str = Depends(get_app_id_from_token)):
    """
    ## Endpoint to Get Chunk Job Results
    This endpoint returns the presigned URL for the chunked file associated with a chunking job.

    ***

    ## Request Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | chunking_job_id     | str    | The ID of the chunking job.      |
    | file_name           | str    | The name of the file.            |

    ***

    ## Response Body

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | file_name           | str    | The name of the file.            |
    | chunk_file_url      | str    | The presigned URL for the chunked file. |

    ***

    #### Errors

    - **404**: If the job ID or file name is not found.
    - **400**: If the job is not completed yet.
    - **403**: If the chunking job does not belong to the app.
    - **500**: If any other error occurs during the retrieval of the chunked file.


    """

    try:
        job_id = req.chunking_job_id

        # Get chunking job
        chunk_job = ChunkingJobs.safe_get(job_id)
        if not chunk_job:
            raise HTTPException(status_code=404, detail="Chunking job not found")

        # Check if chunking_job is associated with the app_id
        if chunk_job.app_id != app_id:
            raise HTTPException(status_code=403, detail="Chunking job does not belong to the app")

        file_name = req.file_name
        response = ChunkingJobFiles.query(A.chunking_job_id == job_id, index='chunking_job_id-index')


        if not response:
            raise HTTPException(status_code=404, detail="File not found for job")

        return_results = {}
        

        for item in response:
            if item.file_name == file_name:
                job_status = item.status
                if job_status != "COMPLETED":
                    raise HTTPException(status_code=400, detail="Job is not completed yet")
                chunk_file_key = item.file_path
                try:
                    chunk_file_url = generate_presigned_url_get(RESULTS_BUCKET_NAME, chunk_file_key)
                except ClientError as e:
                    raise HTTPException(status_code=500, detail="Error getting chunk file URL")
                
                return_results['file_name'] = file_name
                return_results['chunk_file_url'] = chunk_file_url
                return_results['chunking_job_id'] = job_id
                return return_results


        raise HTTPException(status_code=404, detail="Results not found")
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting chunk job results")

# Get job results
@app.get("/document/extraction/job_results/{extraction_job_id}", tags=["Extraction"])
async def get_job_results(extraction_job_id: str, app_id: str = Depends(get_app_id_from_token)):
    """ 
    ## Endpoint to Get Extraction Job Results
    This endpoint returns the results of an extraction job, including the extracted text and tables for each file.

    ***

    ## Request Parameters

    | Parameter           | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | extraction_job_id   | str    | The ID of the extraction job.    |

    ***

    ## Response Body

    A dictionary containing the file names as keys and the extracted text and tables URLs as values.

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | file_name           | str    | The name of the file.            |
    | extracted_text_url  | str    | The presigned URL for the extracted text. |
    | extracted_tables_url| str    | The presigned URL for the extracted tables. |

    ***

    #### Errors

    - **404**: If the job ID is not found.
    - **400**: If the job is not completed yet.
    - **403**: If the extraction job does not belong to the app.
    - **500**: If any other error occurs during the retrieval of the job results.

    """

    extraction_job = ExtractionJobs.safe_get(extraction_job_id)

    if not extraction_job:
        raise HTTPException(status_code=404, detail="Job ID not found")

    # Check if extraction_job is associated with the app_id
    if extraction_job.app_id != app_id:
        raise HTTPException(status_code=403, detail="Extraction job does not belong to the app")

    if extraction_job.status not in ["COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED"]:
        raise HTTPException(status_code=400, detail="Job is not completed yet")

    s3_results_meta_json = f"{app_id}/{extraction_job_id}/metadata.json"
    s3_key = f"{app_id}/{extraction_job_id}/"

    ## Read all folders in s3_key
    folders = []
    try:
        paginator = s3_client.get_paginator('list_objects_v2')
        for result in paginator.paginate(Bucket=RESULTS_BUCKET_NAME, Prefix=s3_key, Delimiter='/'):
            if 'CommonPrefixes' in result:
                for prefix in result.get('CommonPrefixes'):
                    folders.append(prefix.get('Prefix'))
    except s3_client.exceptions.NoSuchBucket:
        raise HTTPException(status_code=404, detail="Results not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting job results")

    ## Get the metadata.json file in folders
    metadata_conbined = {
        "files": []
    }
    for folder in folders:
        try:
            response = s3_client.get_object(
                Bucket=RESULTS_BUCKET_NAME,
                Key=f"{folder}metadata.json"
            )
            metadata = json.loads(response['Body'].read())
            file_key  = metadata['files'][0]['extracted_text_key']
            file_name = folder.split('/')[-2]
            presigned_url = generate_presigned_url_get(RESULTS_BUCKET_NAME, file_key)
            metadata_conbined['files'].append({
                "file_name": file_name,
                "extracted_text_url": presigned_url
            })
        except s3_client.exceptions.NoSuchKey:
            raise HTTPException(status_code=404, detail="Results not found")
        except Exception as e:
            raise HTTPException(status_code=500, detail="Error getting job results")
    
    return metadata_conbined

# List Extraction Jobs
@app.get("/document/extraction/list_jobs", tags=["Extraction"])
async def list_extraction_jobs(app_id: str = Depends(get_app_id_from_token)):
    """ 
    ## Endpoint to List Extraction Jobs
    This endpoint returns a list of extraction jobs associated with the app.

    ***

    ## Response Body

    List of json objects, each containing the following fields:

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | job_id              | str    | The ID of the extraction job.    |
    | status              | str    | The status of the extraction job. |
    | total_file_count    | int    | The total number of files to be extracted. |
    | completed_file_count| int    | The number of files completed.   |
    | failed_file_count   | int    | The number of files failed.      |
    | queued_files        | int    | The number of files queued.      |

    ***

    #### Errors

    - **500**: If any other error occurs during the retrieval of jobs.


    """
    try:
        jobs = ExtractionJobs.query(A.app_id == app_id, index='app_id_index')
        if not jobs:
            return []
        jobs_list = [job.dict(exclude={'timestamp','app_id'}) for job in jobs]
        return jobs_list
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting jobs")

# List Chunking Jobs
@app.get("/document/chunking/list_jobs", tags=["Chunking"])
async def list_chunking_jobs(app_id: str = Depends(get_app_id_from_token)):
    """ 
    ## Endpoint to List Chunking Jobs
    This endpoint returns a list of chunking jobs associated with the app.

    ***

    ## Response Body

    List of json objects, each containing the following fields:

    | Field               | Type   | Description                      |
    |---------------------|--------|----------------------------------|
    | chunking_job_id     | str    | The ID of the chunking job.      |
    | extraction_job_id   | str    | The ID of the extraction job.    |
    | status              | str    | The status of the chunking job. Can be QUEUED, IN_PROGRESS, COMPLETED, or FAILED. |
    | total_file_count    | int    | The total number of files to be chunked. |
    | completed_files     | int    | The number of files completed.   |
    | failed_files        | int    | The number of files failed.      |
    | chunking_strategy   | str    | The chunking strategy used.      |
    | chunking_params     | str    | The parameters used for the chunking strategy. |


    ***

    #### Errors

    - **500**: If any other error occurs during the retrieval of jobs.


    """
    try:
        jobs = ChunkingJobs.query(A.app_id == app_id, index='app_id_index')
        if not jobs:
            return []
        jobs_list = [job.dict(exclude={'timestamp', 'app_id'}) for job in jobs]
        return jobs_list
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error getting jobs")

@app.get("/document/service/meta", include_in_schema=False)
async def get_metadata():
    return app.openapi()

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    logger.error(f"HTTPException: {exc.detail}")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

@app.get("/document/service/health", tags=["Health"])
async def health_check():
    return {"status": "UP"}

@app.on_event("startup")
async def startup_event():
    global session, s3_client, dynamodb, COGNITO_JWKS_URL
    
    if not ECS_METADATA_URL:
        raise HTTPException(status_code=500, detail="ECS_CONTAINER_METADATA_URI_V4 environment variable not set.")

    try:
        response = requests.get(ECS_METADATA_URL, timeout=10)
        response.raise_for_status()
        metadata = response.json()
        region_name = metadata.get("Labels", {}).get("com.amazonaws.ecs.task-arn", "").split(":")[3]

        session = boto3.Session(region_name=region_name)
        s3_client = session.client('s3', config=retry_config)
        dynamodb = session.client('dynamodb', config=retry_config)

        COGNITO_JWKS_URL = f'https://cognito-idp.{region_name}.amazonaws.com/{COGNITO_USER_POOL_ID}/.well-known/jwks.json'

        logger.info("Document Processing Service started successfully.")
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving ECS metadata: {str(e)}")
