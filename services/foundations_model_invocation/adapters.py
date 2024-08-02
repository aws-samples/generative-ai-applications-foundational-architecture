# adapters.py

from typing import Dict, List, Optional, Union
from pydantic import BaseModel

class StandardInput(BaseModel):
    model_name: str
    prompt: Optional[Union[str, List[Dict[str, Union[str, List[Dict[str, str]]]]]]] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    stop_sequences: Optional[List[str]] = None
    text_to_embed: Optional[str] = None
    input_type: Optional[str] = None

class StandardOutput(BaseModel):
    output_text: Optional[str] = None
    embedding: Optional[List[float]] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None

    @classmethod
    def from_response(cls, response: dict, output_mapping: dict):
        return cls(
            output_text=response.get(output_mapping.get("output_text", "")),
            embedding=response.get(output_mapping.get("embedding", "")),
            input_tokens=response.get(output_mapping.get("input_tokens", "")),
            output_tokens=response.get(output_mapping.get("output_tokens", ""))
        )

# Input Adapters
def titan_text_adapter(request: StandardInput) -> dict:
    print(request)
    return {
        "inputText": request.prompt,
        "textGenerationConfig": {
            "temperature": request.temperature or 0.7,
            "topP": request.top_p or 0.9,
            "maxTokenCount": request.max_tokens or 100,
            "stopSequences": request.stop_sequences or []
        }
    }

def anthropic_adapter(request: StandardInput) -> dict:
    messages = [{"role": "user", "content": [{"type": "text", "text": request.prompt}]}]
    return {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": request.max_tokens or 1000,
        "system": "",
        "messages": messages if isinstance(request.prompt, str) else request.prompt,
        "temperature": request.temperature or 0.7,
        "top_p": request.top_p or 0.9,
        "top_k": request.top_k or 40,
        "stop_sequences": request.stop_sequences or []
    }

def ai21_adapter(request: StandardInput) -> dict:
    return {
        "prompt": request.prompt,
        "temperature": request.temperature or 0.7,
        "topP": request.top_p or 0.9,
        "maxTokens": request.max_tokens or 1000,
        "stopSequences": request.stop_sequences or [],
        "countPenalty": {"scale": 0.0},
        "presencePenalty": {"scale": 0.0},
        "frequencyPenalty": {"scale": 0.0}
    }

def cohere_command_adapter(request: StandardInput) -> dict:
    return {
        "prompt": request.prompt,
        "temperature": request.temperature or 0.7,
        "p": request.top_p or 0.9,
        "k": request.top_k or 40,
        "max_tokens": request.max_tokens or 1000,
        "stop_sequences": request.stop_sequences or [],
        "return_likelihoods": "NONE",
        "stream": False,
        "num_generations": 1,
        "logit_bias": {},
        "truncate": "NONE"
    }

def cohere_command_r_adapter(request: StandardInput) -> dict:
    return {
        "message": request.prompt,
        "chat_history": [],
        "documents": [],
        "search_queries_only": False,
        "preamble": "",
        "max_tokens": request.max_tokens or 1000,
        "temperature": request.temperature or 0.7,
        "p": request.top_p or 0.9,
        "k": request.top_k or 40,
        "prompt_truncation": 'OFF',
        "frequency_penalty": 0.0,
        "presence_penalty": 0.0,
        "seed": 0,
        "return_prompt": False,
        "stop_sequences": request.stop_sequences or [],
        "raw_prompting": False
    }

def meta_adapter(request: StandardInput) -> dict:
    return {
        "prompt": request.prompt,
        "temperature": request.temperature or 0.7,
        "top_p": request.top_p or 0.9,
        "max_gen_len": request.max_tokens or 1000
    }

def mistral_adapter(request: StandardInput) -> dict:
    return {
        "prompt": request.prompt,
        "max_tokens": request.max_tokens or 1000,
        "stop": request.stop_sequences or [],
        "temperature": request.temperature or 0.7,
        "top_p": request.top_p or 0.9,
        "top_k": request.top_k or 40
    }

def titan_embed_adapter(request: StandardInput) -> dict:
    return {"inputText": request.text_to_embed}

def cohere_embed_adapter(request: StandardInput) -> dict:
    return {
        "texts": [request.text_to_embed],
        "input_type": request.input_type or 'search_document',  
        # "truncate": request.stop_sequences  # assuming stop_sequences can serve as truncate in this case
    }

# Output Adapters
def titan_text_output_adapter(response: dict) -> StandardOutput:
    return StandardOutput(
        output_text=response.get("results", [{}])[0].get("outputText"),
        input_tokens=response.get("inputTextTokenCount"),
        output_tokens=response.get("results", [{}])[0].get("tokenCount")
    )

def anthropic_output_adapter(response: dict) -> StandardOutput:
    return StandardOutput(
        output_text=response.get("content", [{}])[0].get("text"),
        input_tokens=response.get("usage", {}).get("input_tokens"),
        output_tokens=response.get("usage", {}).get("output_tokens")
    )

def ai21_output_adapter(response: dict) -> StandardOutput:
    return StandardOutput(
        output_text=response.get("completions", [{}])[0]['data'].get("text")
    )

def cohere_command_output_adapter(response: dict) -> StandardOutput:
    return StandardOutput(
        output_text=response.get("generations", [{}])[0].get("text")
    )

def cohere_command_r_output_adapter(response: dict) -> StandardOutput:
    return StandardOutput(
        output_text=response.get("text"),
        input_tokens=response.get("token_count", {}).get("prompt_tokens"),
        output_tokens=response.get("token_count", {}).get("response_tokens")
    )

def meta_output_adapter(response: dict) -> StandardOutput:
    return StandardOutput(
        output_text=response.get("generation"),
        input_tokens=response.get("prompt_token_count"),
        output_tokens=response.get("generation_token_count")
    )

def mistral_output_adapter(response: dict) -> StandardOutput:
    return StandardOutput(
        output_text=response.get("outputs", [{}])[0].get("text")
    )

def titan_embed_output_adapter(response: dict) -> StandardOutput:
    return StandardOutput(
        embedding=response.get("embedding"),
        input_tokens=response.get("inputTextTokenCount")
    )

def cohere_embed_output_adapter(response: dict) -> StandardOutput:
    return StandardOutput(
        embedding=response.get("embeddings", [[]])[0]
    )

# Register adapters
input_adapters = {
    "TITAN_TEXT_PREMIER_V1": titan_text_adapter,
    "TITAN_TEXT_LITE_V1": titan_text_adapter,
    "TITAN_TEXT_EXPRESS_V1": titan_text_adapter,
    "ANTHROPIC_CLAUDE_INSTANT_V1": anthropic_adapter,
    "ANTHROPIC_CLAUDE_V2:1": anthropic_adapter,
    "ANTHROPIC_CLAUDE_V2": anthropic_adapter,
    "ANTHROPIC_CLAUDE_3_SONNET_V1": anthropic_adapter,
    "ANTHROPIC_CLAUDE_3_HAIKU_V1": anthropic_adapter,
    "AI21_JURASSIC_2_ULTRA": ai21_adapter,
    "AI21_JURASSIC_2_MID": ai21_adapter,
    "COHERE_COMMAND_LIGHT_TEXT_V14": cohere_command_adapter,
    "COHERE_COMMAND_TEXT_V14": cohere_command_adapter,
    "COHERE_COMMAND_R_V1": cohere_command_r_adapter,
    "COHERE_COMMAND_R_PLUS_V1": cohere_command_r_adapter,
    "META_LLAMA2_CHAT_13B_V1": meta_adapter,
    "META_LLAMA2_CHAT_70B_V1": meta_adapter,
    "META_LLAMA3_8B_INSTRUCT_V1": meta_adapter,
    "META_LLAMA3_70B_INSTRUCT_V1": meta_adapter,
    "MISTRAL_7B_INSTRUCT_V0:2": mistral_adapter,
    "MIXTRAL_8X7B_INSTRUCT_V0:1": mistral_adapter,
    "MISTRAL_LARGE_V1:0": mistral_adapter,
    "TITAN_EMBED_TEXT_V1": titan_embed_adapter,
    "TITAN_TEXT_EMBED_V2": titan_embed_adapter,
    "COHERE_EMBED_ENGLISH_V3": cohere_embed_adapter,
    "COHERE_EMBED_MULTILINGUAL_V3": cohere_embed_adapter,
}

output_adapters = {
    "TITAN_TEXT_PREMIER_V1": titan_text_output_adapter,
    "TITAN_TEXT_LITE_V1": titan_text_output_adapter,
    "TITAN_TEXT_EXPRESS_V1": titan_text_output_adapter,
    "ANTHROPIC_CLAUDE_INSTANT_V1": anthropic_output_adapter,
    "ANTHROPIC_CLAUDE_V2:1": anthropic_output_adapter,
    "ANTHROPIC_CLAUDE_V2": anthropic_output_adapter,
    "ANTHROPIC_CLAUDE_3_SONNET_V1": anthropic_output_adapter,
    "ANTHROPIC_CLAUDE_3_HAIKU_V1": anthropic_output_adapter,
    "AI21_JURASSIC_2_ULTRA": ai21_output_adapter,
    "AI21_JURASSIC_2_MID": ai21_output_adapter,
    "COHERE_COMMAND_LIGHT_TEXT_V14": cohere_command_output_adapter,
    "COHERE_COMMAND_TEXT_V14": cohere_command_output_adapter,
    "COHERE_COMMAND_R_V1": cohere_command_r_output_adapter,
    "COHERE_COMMAND_R_PLUS_V1": cohere_command_r_output_adapter,
    "META_LLAMA2_CHAT_13B_V1": meta_output_adapter,
    "META_LLAMA2_CHAT_70B_V1": meta_output_adapter,
    "META_LLAMA3_8B_INSTRUCT_V1": meta_output_adapter,
    "META_LLAMA3_70B_INSTRUCT_V1": meta_output_adapter,
    "MISTRAL_7B_INSTRUCT_V0:2": mistral_output_adapter,
    "MIXTRAL_8X7B_INSTRUCT_V0:1": mistral_output_adapter,
    "MISTRAL_LARGE_V1:0": mistral_output_adapter,
    "TITAN_EMBED_TEXT_V1": titan_embed_output_adapter,
    "TITAN_TEXT_EMBED_V2": titan_embed_output_adapter,
    "COHERE_EMBED_ENGLISH_V3": cohere_embed_output_adapter,
    "COHERE_EMBED_MULTILINGUAL_V3": cohere_embed_output_adapter,
}

model_id_map = {
    "TITAN_TEXT_PREMIER_V1": "amazon.titan-text-premier-v1:0",
    "TITAN_TEXT_LITE_V1": "amazon.titan-text-lite-v1",
    "TITAN_TEXT_EXPRESS_V1": "amazon.titan-text-express-v1",
    "ANTHROPIC_CLAUDE_INSTANT_V1": "anthropic.claude-instant-v1",
    "ANTHROPIC_CLAUDE_V2:1": "anthropic.claude-v2:1",
    "ANTHROPIC_CLAUDE_V2": "anthropic.claude-v2",
    "ANTHROPIC_CLAUDE_3_SONNET_V1": "anthropic.claude-3-sonnet-20240229-v1:0",
    "ANTHROPIC_CLAUDE_3_HAIKU_V1": "anthropic.claude-3-haiku-20240307-v1:0",
    "AI21_JURASSIC_2_ULTRA": "ai21.j2-ultra-v1",
    "AI21_JURASSIC_2_MID": "ai21.j2-mid-v1",
    "COHERE_COMMAND_LIGHT_TEXT_V14": "cohere.command-light-text-v14",
    "COHERE_COMMAND_TEXT_V14": "cohere.command-text-v14",
    "COHERE_COMMAND_R_V1": "cohere.command-r-v1:0",
    "COHERE_COMMAND_R_PLUS_V1": "cohere.command-r-plus-v1:0",
    "META_LLAMA2_CHAT_13B_V1": "meta.llama2-13b-chat-v1",
    "META_LLAMA2_CHAT_70B_V1": "meta.llama2-70b-chat-v1",
    "META_LLAMA3_8B_INSTRUCT_V1": "meta.llama3-8b-instruct-v1:0",
    "META_LLAMA3_70B_INSTRUCT_V1": "meta.llama3-70b-instruct-v1:0",
    "MISTRAL_7B_INSTRUCT_V0:2": "mistral.mistral-7b-instruct-v0:2",
    "MIXTRAL_8X7B_INSTRUCT_V0:1": "mistral.mixtral-8x7b-instruct-v0:1",
    "MISTRAL_LARGE_V1:0": "mistral.mistral-large-2402-v1:0",
    "TITAN_EMBED_TEXT_V1": "amazon.titan-embed-text-v1",
    "TITAN_TEXT_EMBED_V2": "amazon.titan-embed-text-v2:0",
    "COHERE_EMBED_ENGLISH_V3": "cohere.embed-english-v3",
    "COHERE_EMBED_MULTILINGUAL_V3": "cohere.embed-multilingual-v3"
}
