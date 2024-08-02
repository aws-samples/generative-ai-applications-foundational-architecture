import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any

from dyntastic import Dyntastic
from pydantic import Field
import os
from pydantic import BaseModel
from enum import Enum


class PromptTemplate(Dyntastic):
    __table_name__ = lambda: os.environ.get("PROMPT_TEMPLATE_TABLE")
    __hash_key__ = "name"

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    app_id: str
    name: str
    prompt_template: str
    version: int
    timestamp: datetime = Field(default_factory=datetime.now)

## Input / Output Models

class CreatePromptTemplateRequest(BaseModel):
    name: str
    prompt_template: str

class GetPromptTemplateRequest(BaseModel):
    name: str

class GetPromptTemplateRequestByVersion(BaseModel):
    name: str
    vnum: int

class TemplateResponse(BaseModel):
    id: str
    name: str
    prompt_template: str
    version: int













