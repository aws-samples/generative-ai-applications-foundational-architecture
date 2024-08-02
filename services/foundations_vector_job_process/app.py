import json
import logging
import os
import asyncio
from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends
from pydantic import BaseModel
import boto3
from botocore.config import Config
from typing import Dict, Any
import requests
from models import VectorizationJobs, VectorizationJobFiles

from utils.vectorize import OpenSearchVectorDB


# Configure structured logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("document_processor")
logger.setLevel(logging.INFO)

# Environment variables for local testing and ECS task
VECTORIZATION_QUEUE_URL = os.getenv('VECTORIZATION_QUEUE_URL')
VECTORIZE_JOBS_TABLE = os.getenv('VECTORIZE_JOBS_TABLE')
VECTORIZE_JOB_FILES_TABLE = os.getenv('VECTORIZE_JOB_FILES_TABLE')
RESULTS_S3_BUCKET = os.getenv('RESULTS_S3_BUCKET')
MAX_RETRIES = int(os.getenv('MAX_RETRIES', '10'))
REGION_NAME = ''
MAX_CONCURRENT_TASKS = int(os.getenv('MAX_CONCURRENT_TASKS', '10'))
VISIBILITY_TIMEOUT = int(os.getenv('VISIBILITY_TIMEOUT', '600'))  # in seconds (10 minutes)
ECS_METADATA_URL = os.getenv("ECS_CONTAINER_METADATA_URI_V4", "")


# Global variables
session = None
s3_client = None
sqs_client = None
dynamodb = None

retry_config = Config(retries={"max_attempts": MAX_RETRIES, "mode": "standard"})

# Background task checking interval (in seconds)
CHECK_INTERVAL = 60
poll_task = None

app = FastAPI()

class Doc(BaseModel):
    file_path: str

# Dependency injection for AWS clients
def get_boto3_clients(region_name):
    session = boto3.Session(region_name=region_name)
    s3_client = session.client('s3', config=retry_config)
    sqs_client = session.client('sqs', config=retry_config)
    dynamodb_client = session.client('dynamodb', config=retry_config)
    return s3_client, sqs_client, dynamodb_client

def get_vector_db(host: str, index_name: str) -> OpenSearchVectorDB:
    return OpenSearchVectorDB(host=host, index_name=index_name, region_name=REGION_NAME)

def update_job_entry(job_id: str, status:str, dynamodb):
    try:
        
        vectorize_job = VectorizationJobs.get(job_id)

        if vectorize_job:
            if status == "FAILED":
                vectorize_job.failed_file_count += 1
            if status == "COMPLETED":
                vectorize_job.completed_file_count += 1
            
            if vectorize_job.failed_file_count + vectorize_job.completed_file_count == vectorize_job.total_file_count:
                # Update job status to 'Completed'
                if vectorize_job.failed_file_count > 0 and vectorize_job.completed_file_count > 0:
                    vectorize_job.status = "COMPLETED_WITH_ERRORS"
                elif vectorize_job.failed_file_count > 0:
                    vectorize_job.status = "FAILED"
                else:
                    vectorize_job.status = "COMPLETED"
            else:
                vectorize_job.status = "IN_PROGRESS"
            
            vectorize_job.save()
        
        else:
            logger.error(f"Job {job_id} not found in the database")

        logger.info(f"Results saved for job {job_id}")
    except Exception as e:
        logger.error(f"Error occurred while saving results: {e}")
    

def update_job_file_entry(file_id:str, status:str, dynamodb):
    try:
        vectorize_job_file = VectorizationJobFiles.get(file_id)
        if vectorize_job_file:
            vectorize_job_file.status = status
            vectorize_job_file.save()
        logger.info(f"Results saved for job file {file_id}")
    except Exception as e:
        logger.error(f"Error occurred while saving results: {e}")
    

async def perform_vectorization(file_path: str, file_id: str, app_id: str, vectorize_job_id: str, index_id: str, host:str, dynamodb, s3_client, sqs_client, receipt_handle: str):
    try:
        
        await extend_visibility_timeout(sqs_client, receipt_handle)

        # Read the text from the S3 file
        vector_db = get_vector_db(host, index_id)
        txt = vector_db.read_s3_txt(file_path, RESULTS_S3_BUCKET, s3_client)

        # Vectorize the text and store in OpenSearch
        vector_db.vectorize_and_store(txt)

        # Sample similiarity search
        # sim_docs = vector_db.docsearch.similarity_search("intrafusal fibers")
        
        sqs_client.delete_message(
            QueueUrl=VECTORIZATION_QUEUE_URL,
            ReceiptHandle=receipt_handle
        )

        print(f"Deleted message from queue: {receipt_handle}")

        # Update the job status in the database
        update_job_file_entry(file_id, 'COMPLETED', dynamodb)
        update_job_entry(vectorize_job_id, 'COMPLETED', dynamodb)


    except Exception as e:
        job_results = {
            'status': "Failed",
            'error': str(e)
        }
        update_job_file_entry(file_id, 'FAILED', dynamodb)
        update_job_entry(app_id, 'FAILED', dynamodb)
        logger.error(f"Error occurred during extraction for job {job_id}: {e}")

async def poll_sqs(sqs_client, dynamodb, s3_client, semaphore):
    logger.info("Polling SQS queue")
    
    while True:
        print("Polling SQS queue")
        try:
            response = sqs_client.receive_message(
                QueueUrl=VECTORIZATION_QUEUE_URL,
                MaxNumberOfMessages=3,
                WaitTimeSeconds=5,
                VisibilityTimeout=VISIBILITY_TIMEOUT  # initial visibility timeout
            )
            messages = response.get('Messages', [])
            logger.info(f"Received {len(messages)} messages")
            for message in messages:
                await semaphore.acquire()
                loop = asyncio.get_event_loop()
                loop.run_in_executor(None, handle_vectorization, semaphore, message, dynamodb, s3_client, sqs_client, message['ReceiptHandle'])
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error occurred: {e}")
            await asyncio.sleep(5)

def handle_vectorization(semaphore, message, dynamodb, s3_client, sqs_client, receipt_handle):
    try:
        message_body = json.loads(message['Body'])
        file_path = message_body['file_path']
        app_id = message_body['app_id']
        index_id = message_body['index_id']
        index_name = message_body['index_name']
        host = message_body['host']
        file_id = message_body['file_id']
        vectorize_job_id = message_body['vectorize_job_id']

        # await perform_vectorization(file_path, file_id, app_id, vectorize_job_id, index_name, host, dynamodb, s3_client, sqs_client, receipt_handle)
        try:
        
            extend_visibility_timeout(sqs_client, receipt_handle)

            # Read the text from the S3 file
            # vector_db = get_vector_db(host, index_id)
            vector_db = get_vector_db(host, index_name)
            txt = vector_db.read_s3_txt(file_path, RESULTS_S3_BUCKET, s3_client)

            # Vectorize the text and store in OpenSearch
            vector_db.vectorize_and_store(txt)

            # Sample similiarity search
            # sim_docs = vector_db.docsearch.similarity_search("intrafusal fibers")
            
            sqs_client.delete_message(
                QueueUrl=VECTORIZATION_QUEUE_URL,
                ReceiptHandle=receipt_handle
            )

            print(f"Deleted message from queue: {receipt_handle}")

            # Update the job status in the database
            update_job_file_entry(file_id, 'COMPLETED', dynamodb)
            update_job_entry(vectorize_job_id, 'COMPLETED', dynamodb)


        except Exception as e:
            job_results = {
                'status': "Failed",
                'error': str(e)
            }
            update_job_file_entry(file_id, 'FAILED', dynamodb)
            update_job_entry(app_id, 'FAILED', dynamodb)
            logger.error(f"Error occurred during vectorization: {e}")
    finally:
        semaphore.release()

def extend_visibility_timeout(sqs_client, receipt_handle):
    try:
        sqs_client.change_message_visibility(
            QueueUrl=VECTORIZATION_QUEUE_URL,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=VISIBILITY_TIMEOUT  # extend the visibility timeout
        )
    except Exception as e:
        logger.error(f"Failed to extend visibility timeout: {e}")

async def ensure_task_running(background_tasks: BackgroundTasks, sqs_client, dynamodb, s3_client):
    global poll_task
    logger.info("Starting background task")
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    while True:
        if poll_task is None or poll_task.done():
            logger.info("Polling task not running or done, starting new task")
            poll_task = asyncio.create_task(poll_sqs(sqs_client, dynamodb, s3_client, semaphore))
            background_tasks.add_task(lambda: poll_task)
            logger.info("Started new polling task")
        await asyncio.sleep(CHECK_INTERVAL)


@app.get("/vectorization/service/health")
async def health_check():
    return {"status": "UP"}

@app.on_event("startup")
async def startup_event(background_tasks: BackgroundTasks = BackgroundTasks()):

    global REGION_NAME

    if not ECS_METADATA_URL:
        raise HTTPException(status_code=500, detail="ECS_CONTAINER_METADATA_URI_V4 environment variable not set.")

    try:
        response = requests.get(ECS_METADATA_URL, timeout=10)
        response.raise_for_status()
        metadata = response.json()
        REGION_NAME = metadata.get("Labels", {}).get("com.amazonaws.ecs.task-arn", "").split(":")[3]

        s3_client, sqs_client, dynamodb_client = get_boto3_clients(REGION_NAME)

        
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving ECS metadata: {str(e)}")


    asyncio.create_task(ensure_task_running(background_tasks, sqs_client, dynamodb_client, s3_client))
