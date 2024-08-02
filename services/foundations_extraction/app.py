import json
import logging
import os
import asyncio
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import boto3
from botocore.config import Config
from utils.extractor import Extraction, ExtractedDocument
import requests
from models import *
from dyntastic import A, transaction
from concurrent.futures import ThreadPoolExecutor
import threading


# Configure structured logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("document_processor")
logger.setLevel(logging.INFO)

QUEUE_URL = os.getenv('QUEUE_URL')
JOB_RESULTS_TABLE = os.getenv('JOB_RESULTS_TABLE')
JOB_FILES_TABLE = os.getenv('JOB_FILES_TABLE')
RESULTS_S3_BUCKET = os.getenv('RESULTS_S3_BUCKET')
SOURCE_S3_BUCKET = os.getenv('SOURCE_S3_BUCKET')
MAX_RETRIES = int(os.getenv('MAX_RETRIES', '10'))
REGION_NAME = ''
MAX_CONCURRENT_TASKS = int(os.getenv('MAX_CONCURRENT_TASKS', '10'))
VISIBILITY_TIMEOUT = int(os.getenv('VISIBILITY_TIMEOUT', '600'))  # in seconds (10 minutes)
ECS_METADATA_URL = os.getenv("ECS_CONTAINER_METADATA_URI_V4", "")

# Global variables
retry_config = Config(retries={"max_attempts": MAX_RETRIES, "mode": "standard"})
CHECK_INTERVAL = 60
poll_task = None

app = FastAPI()

def get_boto3_clients(region_name):
    session = boto3.Session(region_name=region_name)
    s3_client = session.client('s3', config=retry_config)
    sqs_client = session.client('sqs', config=retry_config)
    dynamodb_client = session.client('dynamodb', config=retry_config)
    return s3_client, sqs_client, dynamodb_client



def update_job_entry(job_id: str, textract_job_id: str, status: str, dynamodb, app_id=None, extraction_obj=None):
    try:
        # Get job files with job_id-index
        job_files = ExtractionJobFiles.query(A.job_id == job_id, index='job_id-index')

        job_files_list = [file for file in job_files]

        total_file_count = len(job_files_list)

        # Get COMPLETED and FAILED job files
        completed_files = [file.file_name for file in job_files_list if file.status == 'COMPLETED']
        failed_files = [file.file_name for file in job_files_list if file.status == 'FAILED']
        extraction_job = ExtractionJobs.get(job_id)

        # Update job status based on COMPLETED and FAILED files
        if len(completed_files) + len(failed_files) == total_file_count:

            if len(failed_files) > 0 and len(completed_files) > 0:
                status = 'COMPLETED_WITH_ERRORS'
            elif len(failed_files) > 0:
                status = 'FAILED'
            else:
                status = 'COMPLETED'

            if extraction_job:
                extraction_job.status = status
               
        # Update job status
        
        if extraction_job:
            extraction_job.completed_file_count = len(completed_files)
            extraction_job.failed_file_count = len(failed_files)
            extraction_job.save()


        
        logger.info(f"Results saved for job {job_id}")
    except Exception as e:
        logger.error(f"Error occurred while saving job entry: {e}")

def update_job_file_entry(job_id: str, file_name: str, status: str, dynamodb):
    try:
        extraction_job_file = ExtractionJobFiles.get(job_id, file_name)
        if extraction_job_file:
            extraction_job_file.status = status
            extraction_job_file.save()
        else:
            raise Exception(f"Job file {file_name} not found in the database")
        logger.info(f"Results saved for job file {file_name}")
    except Exception as e:
        logger.error(f"Error occurred while saving file entry: {e}")

async def poll_sqs(extraction: Extraction, sqs_client, dynamodb, s3_client, semaphore):
    logger.info("Polling SQS queue")
    while True:
        executor = ThreadPoolExecutor(max_workers=5)
        try:
            response = sqs_client.receive_message(
                QueueUrl=QUEUE_URL,
                MaxNumberOfMessages=5,
                WaitTimeSeconds=0,
                VisibilityTimeout=VISIBILITY_TIMEOUT
            )
            messages = response.get('Messages', [])
            logger.info(f"Received {len(messages)} messages")
            tasks = []
            for message in messages:
                await semaphore.acquire()
                message_body = json.loads(message['Body'])
                logger.info(f"Acquired semaphore for message {message_body}")
                loop = asyncio.get_event_loop()
                task = loop.run_in_executor(executor, handle_extraction, semaphore, message, extraction, dynamodb, s3_client, sqs_client)
                logger.info(f"Task created for message {message_body}")
                tasks.append(task)
            
            await asyncio.gather(*tasks)
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Error occurred: {e}")
            await asyncio.sleep(5)

def handle_extraction(semaphore, message, extraction, dynamodb, s3_client, sqs_client):
    try:
        message_body = json.loads(message['Body'])
        file_path = message_body.get('file_path')
        job_id = message_body.get('job_id')
        app_id = message_body.get('app_id')
        s3_path = f's3://{SOURCE_S3_BUCKET}/{file_path}'
        file_name = file_path.split('/')[-1]
        receipt_handle = message['ReceiptHandle']
        logger.info(f"Handle extraction for file {file_path}")

        ## Get file type
        file_type = file_path.split('.')[-1].lower()
        textract_file_types = ['pdf', 'png', 'jpg', 'jpeg', 'tiff']
        other_file_types = ['txt', 'md', 'html', 'json', 'jsonl']
        if file_type in textract_file_types:
            textract_job_id = extraction.extract(s3_path)
            try:
                logger.info(f"Performing extraction for job {textract_job_id}")
                extend_visibility_timeout(sqs_client, receipt_handle)
                logger.info(f"Extended visibility timeout for message {message_body}")
                extracted_document = extraction.get_document(textract_job_id, file_name)
                logger.info(f"Extracted document for job {textract_job_id}")
                extracted_document.s3_save(app_id, job_id, file_path, RESULTS_S3_BUCKET, s3_client)
                logger.info(f"Saved results for job {job_id}")
                file_name = file_path.split('/')[-1]

                update_job_file_entry(job_id, file_name, 'COMPLETED', dynamodb)
                update_job_entry(job_id, textract_job_id, 'COMPLETED', dynamodb, app_id, extraction)

                # update_job_entry(job_id, textract_job_id, 'COMPLETED', dynamodb)
                
                logger.info(f"Extraction completed for job {job_id}")
                sqs_client.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt_handle)
            except Exception as e:
                file_name = file_path.split('/')[-1]
                
                update_job_file_entry(job_id, file_name, 'FAILED', dynamodb)
                update_job_entry(job_id, textract_job_id, 'FAILED', dynamodb, app_id, extraction)
                # update_jobs_map(job_id, app_id, 'FAILED', dynamodb, file_name, None, extraction)
                logger.error(f"Error occurred during extraction for job {job_id}: {e}")
        elif file_type in other_file_types:
            logger.info(f"Performing extraction")
            extend_visibility_timeout(sqs_client, receipt_handle)
            extracted_document = extraction.extract_nonpdf(SOURCE_S3_BUCKET, file_path)
            extracted_document.s3_save(app_id, job_id, file_path, RESULTS_S3_BUCKET, s3_client)
            file_name = file_path.split('/')[-1]

            update_job_file_entry(job_id, file_name, 'COMPLETED', dynamodb)
            # update_jobs_map(job_id,app_id, 'COMPLETED', dynamodb, file_name, extracted_document, extraction)
            update_job_entry(job_id, file_name, 'COMPLETED', dynamodb, app_id, extraction)
            
            sqs_client.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt_handle)
        else:
            logger.error(f"Unsupported file type: {file_type}")
            sqs_client.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=receipt_handle)
            update_job_file_entry(job_id, file_name, 'FAILED', dynamodb)
            update_job_entry(job_id, file_name, 'FAILED', dynamodb, app_id, extraction)
            
            # update_jobs_map(job_id, app_id, 'FAILED', dynamodb, file_name, None, extraction)           
    finally:
        semaphore.release()

def extend_visibility_timeout(sqs_client, receipt_handle):
    try:
        sqs_client.change_message_visibility(
            QueueUrl=QUEUE_URL,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=VISIBILITY_TIMEOUT
        )
    except Exception as e:
        logger.error(f"FAILED to extend visibility timeout: {e}")

async def ensure_task_running(extraction: Extraction, sqs_client, dynamodb, s3_client):
    global poll_task
    logger.info("Starting background task")
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    while True:
        if poll_task is None or poll_task.done():
            logger.info("Polling task not running or done, starting new task")
            poll_task = asyncio.create_task(poll_sqs(extraction, sqs_client, dynamodb, s3_client, semaphore))
        await asyncio.sleep(CHECK_INTERVAL)

@app.on_event("startup")
async def startup_event():
    global REGION_NAME

    if not ECS_METADATA_URL:
        raise HTTPException(status_code=500, detail="ECS_CONTAINER_METADATA_URI_V4 environment variable not set.")

    try:
        response = requests.get(ECS_METADATA_URL, timeout=10)
        response.raise_for_status()
        metadata = response.json()
        REGION_NAME = metadata.get("Labels", {}).get("com.amazonaws.ecs.task-arn", "").split(":")[3]

        s3_client, sqs_client, dynamodb_client = get_boto3_clients(REGION_NAME)
        extraction = Extraction(region_name=REGION_NAME)

        logger.info("Document Processing Service started successfully.")
        logger.info(f"Region: {REGION_NAME}")
        logger.info(f"Results S3 Bucket: {RESULTS_S3_BUCKET}")
        logger.info(f"Job Results Table: {JOB_RESULTS_TABLE}")
        logger.info(f"Queue URL: {QUEUE_URL}")

        asyncio.create_task(ensure_task_running(extraction, sqs_client, dynamodb_client, s3_client))

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving ECS metadata: {str(e)}")
