import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from dyntastic import Dyntastic
from pydantic import Field, model_validator
import os
from pydantic import BaseModel
from enum import Enum



class ChunkingJobs(Dyntastic):
    __table_name__ = lambda: os.environ.get("CHUNK_JOBS_TABLE")
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
    updated_at: datetime = Field(default_factory=datetime.now)

    @model_validator(mode="before")
    def set_updated_at(cls, values):
        values["updated_at"] = datetime.now()
        return values

class ChunkingJobFiles(Dyntastic):
    __table_name__ = lambda: os.environ.get("CHUNK_JOB_FILES_TABLE")
    __hash_key__ = "chunk_job_file_id"

    chunk_job_file_id: str
    chunking_job_id: str
    app_id: str
    file_name: str
    file_path: str
    file_id: str
    status: str
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
    app_id: str
    updated_at: datetime = Field(default_factory=datetime.now)

    @model_validator(mode="before")
    def set_updated_at(cls, values):
        values["updated_at"] = datetime.now()
        return values

class VectorizationJobFiles(Dyntastic):

    __table_name__ = lambda: os.environ.get("VECTORIZE_JOB_FILES_TABLE")
    __hash_key__ = "vectorize_job_file_id"

    vectorize_job_file_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    vectorize_job_id: str
    file_path: str
    status: str
    created_at: datetime = Field(default_factory=datetime.now)


## Input / Output Models

# Pydantic models
class CreateVectorStoreRequest(BaseModel):
    store_name: str
    store_type: str
    description: Optional[str] = "Collection for storing vectorized documents"
    tags: List[Dict[str, str]] = [{"key": "project", "value": "GenerativeAI"}]

class CreateVectorStoreResponse(BaseModel):
    store_name: str
    store_type: str
    store_id: str
    message: str

class VectorStoreStatusRequest(BaseModel):
    store_id: str

class VectorStoreStatusResponse(BaseModel):
    store_id: str
    status: str

class VectorIndexStatusRequest(BaseModel):
    index_id: str

class CreateIndexRequest(BaseModel):
    store_id: str
    index_name: str

class CreateIndexResponse(BaseModel):
    index_name: str
    index_id: str
    store_id: str
    store_type: str
    message: str

class VectorizeRequest(BaseModel):
    data: Optional[List[Dict[str, str]]] = None
    s3_txt_path: Optional[str] = None
    host: Optional[str] = None
    collection_name: Optional[str] = None

class VectorizationJobStatusResponse(BaseModel):
    vectorize_job_id: str
    vector_store_id: str
    index_id: str
    chunking_job_id: str
    total_file_count: int
    completed_file_count: int
    failed_file_count: int
    status: str

class SemanticSearchRequest(BaseModel):
    query: str
    index_id: str

class VectorizeRequestChunkJobInput(BaseModel):
    chunking_job_id: str
    index_id: str

class VectorizeResponse(BaseModel):
    vectorize_job_id: str
    status: str