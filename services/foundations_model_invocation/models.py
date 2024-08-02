import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Union, Tuple

from dyntastic import Dyntastic
from pydantic import Field, validator
import os
from pydantic import BaseModel
from enum import Enum



class ModelInvocationLogs(Dyntastic):
    __table_name__ = lambda: os.environ.get("LOGGING_TABLE")
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


class InvokeModelRequest(BaseModel):
    model_name: str
    prompt: Union[str, List[Dict[str, Union[str, List[Dict[str, str]]]]]]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    stop_sequences: Optional[List[str]] = None
    system_prompts: Optional[List[Dict[str, Union[str, List[Dict[str, str]]]]]] = Field(None,
    example=[{"text":"You are a helpful assistant."}])

    @validator('prompt', pre=True, always=True)
    def check_prompt(cls, v):
        if isinstance(v, str):
            return v
        elif isinstance(v, list):
            for message in v:
                if not isinstance(message, dict) or 'role' not in message or 'content' not in message:
                    raise ValueError("Each message must be a dict with 'role' and 'content'")
            return v
        else:
            raise ValueError("prompt must be either a string or a list of messages")

class InvokeModelWithRawInputRequest(BaseModel):
    model_id: str
    raw_input: Dict

class InvokeEmbedModelRequest(BaseModel):
    model_name: str
    input_text: Optional[str] = None