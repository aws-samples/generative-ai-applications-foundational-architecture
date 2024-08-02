import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from dyntastic import Dyntastic
from pydantic import Field, model_validator
import os
from pydantic import BaseModel
from enum import Enum


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