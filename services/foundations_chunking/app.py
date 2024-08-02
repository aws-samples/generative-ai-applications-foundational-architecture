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
from utils.fixed_size_chunking import FixedSizeChunker
from utils.recursive_chunking import RecursiveChunker
from utils.page_wise_chunking import PagewiseChunker
from utils.json_chunking import JSONChunker
from typing import List
from models import ChunkingJobs, ChunkingJobFiles

# Configure structured logging
logging.basicConfig(level=logging.INFO)
logger =  logging.getLogger("chunking_processor")
logger.setLevel(logging.INFO)

# Environment variables for local testing and ECS task
QUEUE_URL = os.getenv('QUEUE_URL')
RESULTS_S3_BUCKET = os.getenv('RESULTS_S3_BUCKET')
MAX_RETRIES = int(os.getenv('MAX_RETRIES', '10'))
REGION_NAME = ''
MAX_CONCURRENT_TASKS = int(os.getenv('MAX_CONCURRENT_TASKS', '10'))
VISIBILITY_TIMEOUT = int(os.getenv('VISIBILITY_TIMEOUT', '600'))  # in seconds (10 minutes)
ECS_METADATA_URL = os.getenv("ECS_CONTAINER_METADATA_URI_V4", "")
CHUNKING_JOBS_TABLE = os.getenv('CHUNKING_JOBS_TABLE')
CHUNKING_JOBS_FILES_TABLE = os.getenv('CHUNKING_JOBS_FILES_TABLE')



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


def get_boto3_clients(region_name):
    session = boto3.Session(region_name=region_name)
    s3_client = session.client('s3', config=retry_config)
    sqs_client = session.client('sqs', config=retry_config)
    dynamodb_client = session.client('dynamodb', config=retry_config)
    return s3_client, sqs_client, dynamodb_client

def save_chunks_to_s3(bucket: str, file_path: str, chunks: List[dict]):
    try:
        s3 = boto3.client('s3')
        s3.put_object(Bucket=bucket, Key=file_path, Body=json.dumps(chunks))
        logger.info(f"Chunks saved to S3: {file_path}")
    except Exception as e:
        raise e

def read_file_from_s3(file_path: str) -> str:
    try:
        s3 = boto3.client('s3')
        response = s3.get_object(Bucket=RESULTS_S3_BUCKET, Key=file_path)
        data = json.loads(response['Body'].read())
        return data
    except Exception as e:
        raise e

async def poll_sqs( sqs_client, dynamodb, s3_client, semaphore):
    logger.info("Polling SQS queue")
    
    while True:
        print("Polling SQS queue")
        try:
            response = sqs_client.receive_message(
                QueueUrl=QUEUE_URL,
                MaxNumberOfMessages=3,
                WaitTimeSeconds=5,
                VisibilityTimeout=VISIBILITY_TIMEOUT  # initial visibility timeout
            )
            messages = response.get('Messages', [])
            logger.info(f"Received {len(messages)} messages")
            for message in messages:
                await semaphore.acquire()
                asyncio.create_task(
                    handle_chunking(
                        semaphore,
                        message,
                        dynamodb,
                        s3_client,
                        sqs_client
                    )
                )
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error occurred: {e}")
            await asyncio.sleep(5)

async def handle_chunking(semaphore, message, dynamodb, s3_client, sqs_client):
    try:
        
        message_body = json.loads(message['Body'])
        file_path = message_body.get('file_path')
        file_name = message_body.get('file_name')
        extraction_job_id = message_body.get('extraction_job_id')
        chunk_job_id = message_body.get('chunking_job_id')
        chunk_job_file_id = message_body.get('chunk_job_file_id')
        chunking_strategy = message_body.get('chunking_strategy')
        chunking_params = message_body.get('chunking_params')
        app_id = message_body.get('app_id')
        receipt_handle = message['ReceiptHandle']

        # Infer File Type
        file_extension = file_name.split(".")[-1]

        await extend_visibility_timeout(sqs_client, receipt_handle)
        # Perform Chunking
        chunk_size = chunking_params.get('chunk_size', 1000)
        chunk_overlap = chunking_params.get('chunk_overlap', 0)
        content = read_file_from_s3(file_path)
        if file_extension == "json":
            json_chunker = JSONChunker()
            chunks = json_chunker.chunk_json(content)
            logger.info(f"Processed file: {file_name}, chunks: {json.dumps(chunks, indent=2)}")
        elif file_extension == "jsonl":
            json_chunker = JSONChunker()
            chunks = json_chunker.chunk_jsonl(content)
            logger.info(f"Processed file: {file_name}, chunks: {json.dumps(chunks, indent=2)}")
        else:
            if chunking_strategy == "fixed_size":
                fixed_size_chunker = FixedSizeChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
                chunks = fixed_size_chunker.chunk(content)
                logger.info(f"Processed file: {file_name}, chunks: {json.dumps(chunks, indent=2)}")
            elif chunking_strategy == "recursive":
                recursive_chunker = RecursiveChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
                chunks = recursive_chunker.chunk(content)
                logger.info(f"Processed file: {file_name}, chunks: {json.dumps(chunks, indent=2)}")
            elif chunking_strategy == "page":
                pagewise_chunker = PagewiseChunker()
                chunks = pagewise_chunker.chunk(content)
                logger.info(f"Processed file: {file_name}, chunks: {json.dumps(chunks, indent=2)}")
            else:
                raise ValueError(f"Invalid chunking strategy: {chunking_strategy}")
        
        # Save chunks to S3
        
        created_chunk_key = f"{app_id}/{extraction_job_id}/{file_name}/chunk_{chunk_job_id}.json"
        save_chunks_to_s3(RESULTS_S3_BUCKET, created_chunk_key, chunks)

        #  delete the message from the queue
        sqs_client.delete_message(
            QueueUrl=QUEUE_URL,
            ReceiptHandle=message['ReceiptHandle']
        )
        logger.info(f"Deleted message from SQS: {message}")

        chunking_job_file = ChunkingJobFiles.safe_get(chunk_job_file_id)
        if chunking_job_file:
            chunking_job_file.status = "COMPLETED"
            chunking_job_file.save()
            logger.info(f"Updated chunking job file record: {chunk_job_file_id}")
            chunking_job = ChunkingJobs.safe_get(chunk_job_id)
            if chunking_job:
                chunking_job.status = "COMPLETED"
                chunking_job.queued_files -= 1
                chunking_job.completed_files += 1
                chunking_job.save()
            else:
                logger.error(f"Chunking job record not found: {chunk_job_id}")

        else:
            logger.error(f"Chunking job file record not found: {chunk_job_file_id}")

        logger.info(f"Updated chunking job record: {chunk_job_id}")
    except Exception as e:
        logger.error(f"Error processing message: {e}")
    finally:
        semaphore.release()

async def extend_visibility_timeout(sqs_client, receipt_handle):
    try:
        sqs_client.change_message_visibility(
            QueueUrl=QUEUE_URL,
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

@app.get("/chunking/service/health")
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
        # extraction = Extraction(region_name=REGION_NAME)

        logger.info("Chunking Processing Service started successfully.")
        logger.info(f"Region: {REGION_NAME}")
        logger.info(f"Results S3 Bucket: {RESULTS_S3_BUCKET}")
        logger.info(f"Chunking Job Results Table: {CHUNKING_JOBS_TABLE}")
        logger.info(f"Chunking Job Files Results Table: {CHUNKING_JOBS_FILES_TABLE}")
        logger.info(f"Chunking Queue URL: {QUEUE_URL}")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving ECS metadata: {str(e)}")


    asyncio.create_task(ensure_task_running(background_tasks, sqs_client, dynamodb_client, s3_client))
