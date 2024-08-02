import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from dyntastic import Dyntastic
from pydantic import Field, model_validator
import os
from pydantic import BaseModel
from enum import Enum


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