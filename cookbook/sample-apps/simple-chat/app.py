import streamlit as st
from sdk.accelerator import GenerativeAIAccelerator
import requests

accelerator = GenerativeAIAccelerator()
_model = accelerator.model_service

def get_model_list():
    response = _model.list_models()
    return response['text_models']

with st.sidebar:
    st.title("Simple Chat App")
    st.divider()
    model_selected = st.selectbox("Select Model", [model["model_name"] for model in get_model_list() if 'EMBED' not in model["model_name"]])
    max_tokens = st.slider("Max Tokens", min_value=100, max_value=2000, value=200)
    temperature = st.slider("Temperature", min_value=0.1, max_value=1.0, value=0.7)
    

model_prompt = """
Role: You are a helpful chatbot assistant. Respond appropriately to user's message/question.
User:{text}
"""

def get_response(message, model):
    if 'TITAN' in model:
        stop_sequences = ["User:"]
    else:
        stop_sequences = ["\\n"]
    response = _model.invoke_model(model_name=model_selected,
                            prompt= model_prompt.format(text=message),
                            max_tokens=max_tokens,
                            temperature=temperature,
                            top_p=0.9,
                            top_k=50,
                            stop_sequences=stop_sequences)
    return response['output_text']


if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "Hello! I am chatbot built on GenAI Foundational Platform. I can help you with your queries. Ask me anything."}]

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("What is up?"):
    st.chat_message("user").markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})
    response = get_response(prompt , model_selected)
    with st.chat_message("assistant"):
        st.markdown(response)
    st.session_state.messages.append({"role": "assistant", "content": response})