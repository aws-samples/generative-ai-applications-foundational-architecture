import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from dyntastic import Dyntastic
from pydantic import Field, model_validator
import os
from pydantic import BaseModel
from enum import Enum

# Extraction job status enum
class ExtractionJobStatus(str, Enum):
    CREATED = "CREATED"
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"



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
    updated_at: datetime = Field(default_factory=datetime.now)

    @model_validator(mode="before")
    def set_updated_at(cls, values):
        values["updated_at"] = datetime.now()
        return values

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
    updated_at: datetime = Field(default_factory=datetime.now)

    @model_validator(mode="before")
    def set_updated_at(cls, values):
        values["updated_at"] = datetime.now()
        return values

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


## Input / Output Models

class Doc(BaseModel):
    file_name: str

class CreateExtractionResponse(BaseModel):
    extraction_job_id: str
    status: ExtractionJobStatus

class RegisterFileRequest(BaseModel):
    extraction_job_id: str
    file_name: str

class RegisterFileResponse(BaseModel):
    extraction_job_id: str
    file_name: str
    file_id: str
    upload_url: str

class StartExtractionJobRequest(BaseModel):
    extraction_job_id: str

class GetExtractionJobFilesRequest(BaseModel):
    extraction_job_id: str

class ExtractionJobFileResponse(BaseModel):
    status: str
    result_url: Optional[str] = None
    extraction_job_id: str

class ExtractionJobFileRequest(BaseModel):
    extraction_job_id: str
    file_name: str

# {"job_id": job_id, "total_files": file_count, "status": "STARTED"}
class StartExtractionJobResponse(BaseModel):
    extraction_job_id: str
    total_files: int
    status: ExtractionJobStatus = Field(default=ExtractionJobStatus.STARTED)

class ChunkingParams(BaseModel):
    chunk_size: Optional[int] = None
    chunk_overlap: Optional[int]  = None 

class ChunkingStrategy(str,Enum):
     FIXED_SIZE = "fixed_size"
     RECURSIVE = "recursive"
     PAGE = "page"
     
class CreateChunkingJobRequest(BaseModel):
    extraction_job_id: str
    chunking_strategy: ChunkingStrategy
    chunking_params: Optional[ChunkingParams] = None

class CreateChunkingJobResponse(BaseModel):
    chunking_job_id: str
    extraction_job_id: str
    status: str
    total_file_count: int

class GetFileChunksRequest(BaseModel):
    chunking_job_id: str
    file_name: str

class GetExtractionJobFilesResponse(BaseModel):
    job_id: str
    file_name: str
    status: str

class ExtractionJobStatusResponse(BaseModel):
    job_id: str
    completed_file_count: int
    total_file_count: int
    failed_file_count: int
    status: str


avoid_chars = ["&", "$", "@", "=", ";", "/", ":", "+", " ", ",", "?", "\\", "{", "}", "^", "]", "\"", ">", "[", "~", "<", "#", "|", "%"]