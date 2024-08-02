import streamlit as st
from sdk.accelerator import GenerativeAIAccelerator
import requests
import time

accelerator = GenerativeAIAccelerator()
_document = accelerator.document_service
_model = accelerator.model_service

page_summary_prompt_template = """
Summarize the following text:

{text}
"""

summary_of_summaries_prompt_template = """
Summarize the following summaries:

{summaries}
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
    return [page['page_text'] for page in text_response['pages']]

def summarize_text(text):
    summary_prompt = page_summary_prompt_template.format(text=text)
    response = _model.invoke_model(
        model_name="ANTHROPIC_CLAUDE_3_SONNET_V1",
        prompt=summary_prompt,
        max_tokens=5000,
        temperature=0.7,
        top_p=0.9,
        top_k=50,
        stop_sequences=["\\n"]
    )
    return response['output_text']

def summarize_summaries(summaries):
    summaries_text = "\n\n".join(summaries)
    summary_of_summaries_prompt = summary_of_summaries_prompt_template.format(summaries=summaries_text)
    response = _model.invoke_model(
        model_name="ANTHROPIC_CLAUDE_3_SONNET_V1",
        prompt=summary_of_summaries_prompt,
        max_tokens=5000,
        temperature=0.7,
        top_p=0.9,
        top_k=50,
        stop_sequences=["\\n"]
    )
    return response['output_text']

def process_file(file):
    with st.spinner("Summarizing .."):
        extraction_job = _document.create_extraction_job()['extraction_job_id']
        st.write(f"Extraction job ID: {extraction_job}")

        upload_file(file, extraction_job)

        _document.start_extraction_job(extraction_job)
        job_status = check_extraction_status(extraction_job)

        if job_status == 'COMPLETED':
            st.write("Extraction completed successfully")
            pages_text = extract_text(extraction_job, file.name)

            page_summaries = []
            for i, page_text in enumerate(pages_text):
                summary = summarize_text(page_text)
                page_summaries.append(summary)
                with st.expander(f"Page {i+1} Summary"):
                    st.write(summary)

            summary_of_summaries = summarize_summaries(page_summaries)
            with st.expander("Summary of Summaries"):
                st.write(summary_of_summaries)
        else:
            st.write(f"Extraction failed with status: {job_status}")

# Sidebar for file upload
with st.sidebar:
    st.title("Document Summarizer")
    st.write("Summarize a PDF document using AI")
    file = st.sidebar.file_uploader("Choose a PDF file", type=["pdf"], key="file")

if file:
    process_file(file)
