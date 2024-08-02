import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from dyntastic import Dyntastic
from pydantic import Field
import os
from pydantic import BaseModel
from enum import Enum

class ModelInvocationLogs(Dyntastic):
    __table_name__ = lambda: os.environ.get("INVOCATION_LOG_TABLE")
    __hash_key__ = "invocation_id"

    invocation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.now)
    model_name: str
    model_id: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    app_id: str
    status: str
    error_message: Optional[str] = None

class ExtractionJobs(Dyntastic):
    __table_name__ = lambda: os.environ.get("EXTRACTION_JOBS_TABLE")
    __hash_key__ = "job_id"

    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    app_id: str
    completed_file_count: int = 0
    total_file_count: int
    failed_file_count: int = 0
    status: str = "CREATED"
    queued_files: int = 0
    timestamp: datetime = Field(default_factory=datetime.now)

class ExtractionJobFiles(Dyntastic):

    __table_name__ = lambda: os.environ.get("EXTRACTION_JOB_FILES_TABLE")
    __hash_key__ = "job_id"
    __range_key__ = "file_name"

    job_id: str
    file_name: str
    file_path: str
    file_id: str
    status: str = "PENDING"
    timestamp: datetime = Field(default_factory=datetime.now)


class ChunkingJobs(Dyntastic):
    __table_name__ = lambda: os.environ.get("CHUNKING_JOBS_TABLE")
    __hash_key__ = "chunking_job_id"

    chunking_job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    extraction_job_id: str
    app_id: str
    status: str
    chunking_strategy: str
    chunking_params: str
    total_file_count: int
    queued_files: int
    completed_files: int
    failed_files: int
    timestamp: datetime = Field(default_factory=datetime.now)

class ChunkingJobFiles(Dyntastic):
    __table_name__ = lambda: os.environ.get("CHUNKING_JOBS_FILES_TABLE")
    __hash_key__ = "chunk_job_file_id"

    chunk_job_file_id: str
    chunking_job_id: str
    app_id: str
    file_name: str
    file_path: str
    file_id: str
    status: str
    timestamp: datetime = Field(default_factory=datetime.now)

class PromptTemplate(Dyntastic):
    __table_name__ = lambda: os.environ.get("PROMPT_TEMPLATE_TABLE")
    __hash_key__ = "name"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    app_id: str
    name: str
    prompt_template: str
    version: int
    timestamp: datetime = Field(default_factory=datetime.now)

class VectorStore(Dyntastic):
    __table_name__ = lambda: os.environ.get("VECTOR_STORES_TABLE")
    __hash_key__ = "vector_store_id"
    __range_key__ = "app_id"

    vector_store_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    store_name: str
    app_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    host: str
    store_type: str

class VectorIndex(Dyntastic):
    __table_name__ = lambda: os.environ.get("VECTOR_STORES_INDEX_TABLE")
    __hash_key__ = "index_id"

    index_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    vector_store_id: str
    index_name: str
    created_at: datetime = Field(default_factory=datetime.now)

class VectorizationJobs(Dyntastic):

    __table_name__ = lambda: os.environ.get("VECTORIZE_JOBS_TABLE")
    __hash_key__ = "vectorize_job_id"

    vectorize_job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    vector_store_id: str
    index_id: str
    chunking_job_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    status: str
    total_file_count: int
    queued_files: int
    completed_file_count: int
    failed_file_count: int

class VectorizationJobFiles(Dyntastic):

    __table_name__ = lambda: os.environ.get("VECTORIZE_JOB_FILES_TABLE")
    __hash_key__ = "vectorize_job_file_id"

    vectorize_job_file_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    vectorize_job_id: str
    file_path: str
    status: str
    created_at: datetime = Field(default_factory=datetime.now)