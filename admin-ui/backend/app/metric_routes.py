from fastapi import APIRouter, Request, Depends, HTTPException
import httpx
from dependencies import verify_token, get_cognito_token
from utils import cognito_token_manager
import requests
from typing import Dict, Any, Type
from pydantic import BaseModel, Field, create_model, validator
from typing import Optional
import json
import boto3
from boto3.dynamodb.conditions import Key
from datetime import datetime
from config import conf
from models import *
from dyntastic import A


router = APIRouter()
# Remove trailing slash from the base URL
EXTERNAL_API_URL = conf.PLATFORM_BASE_URL.rstrip("/")
region = conf.AWS_REGION
dynamodb = boto3.resource('dynamodb', region_name=region)

def convert_to_iso8601(date_str: str) -> str:
    try:
        print(date_str)
        # Convert from yyyy-dd-mm to yyyy-mm-dd
        date_obj = date_str.split('-')
        date_obj = datetime(int(date_obj[0]), int(date_obj[1]), int(date_obj[2]))
        print(date_obj)
        # Convert to ISO 8601 format with time
        iso_date_str = date_obj.isoformat() + 'Z'
        print(iso_date_str)
        return iso_date_str
    except Exception as e:
        print(f"Failed to convert date: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid date format: {date_str}. Expected format is yyyy-dd-mm.")

def convert_to_dynamodb_timestamp(date_str):
    # Parse the input date string in yyyy-mm-dd format
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    # Convert to the desired timestamp format
    dynamodb_timestamp = date_obj.strftime('%Y-%m-%dT%H:%M:%S.%f')
    return dynamodb_timestamp

class MetricsRequest(BaseModel):
    model_id: Optional[str] = None
    app_id: str
    start_date: str = None  # in yyyy-dd-mm format
    end_date: str = None  # in yyyy-dd-mm format
    limit: int = 1000
    last_evaluated_key: dict = None

class VectorStoreIndexesRequest(BaseModel):
    vector_store_id: str

@router.post("/admin/metrics/invocations")
async def get_invocations(request: MetricsRequest):
    try:
        start_timestamp = None
        end_timestamp = None

        if request.start_date:
            start_timestamp = convert_to_dynamodb_timestamp(request.start_date)
        if request.end_date:
            end_timestamp = convert_to_dynamodb_timestamp(request.end_date)

        fe = None
        if request.start_date and request.end_date:
            fe = A('timestamp').between(start_timestamp, end_timestamp)
        elif request.start_date:
            fe = A('timestamp').gte(start_timestamp)
        elif request.end_date:
            fe = A('timestamp').lte(end_timestamp)

        invocations = ModelInvocationLogs.query(A.app_id == request.app_id, index = 'app_id_index', filter_condition=fe)
        print(f"Invocations: {invocations}")
        # for i in invocations:
        #     print(i.model_dump())

        # Group by model_id, status and get count, sum of input_tokens, sum of output_tokens
        grouped_items = {}
        for invocation in invocations:
            model_id = invocation.model_id
            status = invocation.status
            # input_tokens and output_tokens are stored as strings in DynamoDB, can be None
            if invocation.input_tokens:
                input_tokens = int(invocation.input_tokens)
            else:
                input_tokens = 0
            if invocation.output_tokens:
                output_tokens = int(invocation.output_tokens)
            else:
                output_tokens = 0

            if model_id not in grouped_items:
                grouped_items[model_id] = {
                    'total_count': 0,
                    'total_input_tokens': 0,
                    'total_output_tokens': 0,
                    'status_counts': {}
                }

            grouped_items[model_id]['total_count'] += 1
            grouped_items[model_id]['total_input_tokens'] += input_tokens
            grouped_items[model_id]['total_output_tokens'] += output_tokens
            grouped_items[model_id]['model_name'] = invocation.model_name

            if status not in grouped_items[model_id]['status_counts']:
                grouped_items[model_id]['status_counts'][status] = 0

            grouped_items[model_id]['status_counts'][status] += 1

        return {
            'items': grouped_items,
            'last_evaluated_key': None
        }
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
    

@router.post("/admin/metrics/extraction-jobs")
async def get_extraction_jobs(request: MetricsRequest):

    try:
        start_timestamp = None
        end_timestamp = None

        if request.start_date:
            start_timestamp = convert_to_dynamodb_timestamp(request.start_date)
        if request.end_date:
            end_timestamp = convert_to_dynamodb_timestamp(request.end_date)

        fe = None
        if request.start_date and request.end_date:
            fe = A('timestamp').between(start_timestamp, end_timestamp)
        elif request.start_date:
            fe = A('timestamp').gte(start_timestamp)
        elif request.end_date:
            fe = A('timestamp').lte(end_timestamp)

        extraction_jobs = ExtractionJobs.query(A.app_id == request.app_id, index = 'app_id_index', filter_condition=fe)

        # Group by status and get count, sum of completed_file_count, sum of total_file_count, sum of failed_file_count
        grouped_items = {}
        for job in extraction_jobs:
            status = job.status
            completed_file_count = job.completed_file_count
            total_file_count = job.total_file_count
            failed_file_count = job.failed_file_count

            if status not in grouped_items:
                grouped_items[status] = {
                    'total_count': 0,
                    'total_completed_file_count': 0,
                    'total_total_file_count': 0,
                    'total_failed_file_count': 0
                }

            grouped_items[status]['total_count'] += 1
            grouped_items[status]['total_completed_file_count'] += completed_file_count
            grouped_items[status]['total_total_file_count'] += total_file_count
            grouped_items[status]['total_failed_file_count'] += failed_file_count

        return {
            'items': grouped_items,
            'last_evaluated_key': None
        }
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@router.post("/admin/metrics/chunking-jobs")
async def get_chunking_jobs(request: MetricsRequest):
    try:
        start_timestamp = None
        end_timestamp = None
    
        if request.start_date:
            start_timestamp = convert_to_dynamodb_timestamp(request.start_date)
        if request.end_date:
            end_timestamp = convert_to_dynamodb_timestamp(request.end_date)
    
        fe = None
        if request.start_date and request.end_date:
            fe = A('timestamp').between(start_timestamp, end_timestamp)
        elif request.start_date:
            fe = A('timestamp').gte(start_timestamp)
        elif request.end_date:
            fe = A('timestamp').lte(end_timestamp)
    
        chunking_jobs = ChunkingJobs.query(A.app_id == request.app_id, index = 'app_id_index', filter_condition=fe)
        
        # Group by status and get count, sum of completed_files, sum of total_files, sum of failed_files
        grouped_items = {}
        for job in chunking_jobs:
            status = job.status
            completed_files = job.completed_files
            total_files = job.total_file_count
            failed_files = job.failed_files
    
            if status not in grouped_items:
                grouped_items[status] = {
                    'total_count': 0,
                    'total_completed_files': 0,
                    'total_total_files': 0,
                    'total_failed_files': 0
                }
    
            grouped_items[status]['total_count'] += 1
            grouped_items[status]['total_completed_files'] += completed_files
            grouped_items[status]['total_total_files'] += total_files
            grouped_items[status]['total_failed_files'] += failed_files
    
        return {
            'items': grouped_items,
            'last_evaluated_key': None
        }
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@router.post("/admin/metrics/vector-stores")
async def get_vector_stores(request: MetricsRequest):

    try:
        start_timestamp = None
        end_timestamp = None

        if request.start_date:
            start_timestamp = convert_to_dynamodb_timestamp(request.start_date)
        if request.end_date:
            end_timestamp = convert_to_dynamodb_timestamp(request.end_date)

        fe = None
        if request.start_date and request.end_date:
            fe = A('created_at').between(start_timestamp, end_timestamp)
        elif request.start_date:
            fe = A('created_at').gte(start_timestamp)
        elif request.end_date:
            fe = A('created_at').lte(end_timestamp)

        vector_stores = VectorStore.query(A.app_id == request.app_id, index = 'app_id_index', filter_condition=fe)

        stores = []
        for v in vector_stores:
            stores.append(v.model_dump())

        return {
            'items': stores,
            'last_evaluated_key': None
        }
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@router.post("/admin/metrics/vector-indexes")
def get_vector_indexes(request: VectorStoreIndexesRequest):
    try:  
        vector_indexes = VectorIndex.query(A.vector_store_id == request.vector_store_id, index = 'vector_store_id-index')
        indexes = []
        for i in vector_indexes:
            indexes.append(i.model_dump())

        return {
            'items': indexes,
            'last_evaluated_key': None
        }
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@router.post("/admin/metrics/vectorization-jobs")
def get_vectorization_jobs(request: MetricsRequest):
    try:
        start_timestamp = None
        end_timestamp = None
    
        if request.start_date:
            start_timestamp = convert_to_dynamodb_timestamp(request.start_date)
        if request.end_date:
            end_timestamp = convert_to_dynamodb_timestamp(request.end_date)
    
        fe = None
        if request.start_date and request.end_date:
            fe = A('created_at').between(start_timestamp, end_timestamp)
        elif request.start_date:
            fe = A('created_at').gte(start_timestamp)
        elif request.end_date:
            fe = A('created_at').lte(end_timestamp)
    
        vectorization_jobs = VectorizationJobs.query(A.app_id == request.app_id, index = 'app_id-index', filter_condition=fe)
        # for v in vectorization_jobs:
        #     print(v.model_dump())
    
        # Group by status and get count, sum of completed_files, sum of total_files, sum of failed_files
        grouped_items = {}
        for job in vectorization_jobs:
            status = job.status
            completed_files = job.completed_file_count
            total_files = job.total_file_count
            failed_files = job.failed_file_count
    
            if status not in grouped_items:
                grouped_items[status] = {
                    'total_count': 0,
                    'total_completed_files': 0,
                    'total_total_files': 0,
                    'total_failed_files': 0
                }
    
            grouped_items[status]['total_count'] += 1
            grouped_items[status]['total_completed_files'] += completed_files
            grouped_items[status]['total_total_files'] += total_files
            grouped_items[status]['total_failed_files'] += failed_files
    
        return {
            'items': grouped_items,
            'last_evaluated_key': None
        }
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")