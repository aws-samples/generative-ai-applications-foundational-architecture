import streamlit as st
from sdk.accelerator import GenerativeAIAccelerator
import requests
import time

accelerator = GenerativeAIAccelerator()
_document = accelerator.document_service
_model = accelerator.model_service

prompt_template = """
Give two pieces of text, compare them and list out the differences. 

Text 1:
{text1}

Text 2:
{text2}
"""

def upload_file(file, extraction_job):
    upload_url = _document.register_file_for_extraction(extraction_job, file.name)['upload_url']
    requests.put(upload_url, data=file)

def check_extraction_status(extraction_job):
    while True:
        response = _document.get_extraction_job_status(extraction_job)
        job_status = response['status']
        if job_status in ['COMPLETED', 'FAILED', 'COMPLETED_WITH_ERRORS']:
            return job_status
        time.sleep(5)

def extract_text(extraction_job, file_name):
    response = _document.get_file_status(extraction_job, file_name)
    text_response = requests.get(response['result_url']).json()
    return "".join(page['page_text'] for page in text_response['pages'])

def compare_documents(text1, text2):
    compare_prompt = prompt_template.format(text1=text1, text2=text2)
    response = _model.invoke_model(
        model_name="ANTHROPIC_CLAUDE_3_SONNET_V1",
        prompt=compare_prompt,
        max_tokens=5000,
        temperature=0.7,
        top_p=0.9,
        top_k=50,
        stop_sequences=["\\n"]
    )
    return response['output_text']

def process_files(file1, file2):
    extraction_job = _document.create_extraction_job()['extraction_job_id']
    st.write(f"Extracting text from files ..")

    upload_file(file1, extraction_job)
    upload_file(file2, extraction_job)

    _document.start_extraction_job(extraction_job)
    job_status = check_extraction_status(extraction_job)

    if job_status == 'COMPLETED':
        st.write("Extraction completed successfully")
        text1 = extract_text(extraction_job, file1.name)
        text2 = extract_text(extraction_job, file2.name)
        comparison_result = compare_documents(text1, text2)
        st.write(comparison_result)
    else:
        st.write(f"Extraction failed with status: {job_status}")

# Sidebar for file uploads
with st.sidebar:
    st.title("Document Comparison (PDF)")
    st.markdown("#### Upload Documents")
    file1 = st.sidebar.file_uploader("Choose the first PDF file", type=["pdf"], key="file1")
    file2 = st.sidebar.file_uploader("Choose the second PDF file", type=["pdf"], key="file2")


if file1 and file2:
    with st.spinner("Processing..."):
        process_files(file1, file2)
