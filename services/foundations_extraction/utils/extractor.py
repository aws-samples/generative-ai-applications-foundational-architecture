import boto3
import re
import uuid
import json
from textractor import Textractor
from textractor.data.constants import TextractFeatures, TextractAPI
from textractor.entities.lazy_document import LazyDocument
from textractor.data.text_linearization_config import TextLinearizationConfig

class ExtractedDocument:
    def __init__(self, pages=None, tables=None, all_text=None, input_path=None):
        self.pages = pages or []
        self.tables = tables or {}
        self.all_text = all_text
        self.input_path = input_path

    def s3_save(self, app_id, job_id, file_name, bucket, s3_client):
        file_name = file_name.split('/')[-1]

        extracted_text_content = {
            "job_id": job_id,
            "file_name": file_name,
            "pages": [{"page_number": i + 1, "page_text": page} for i, page in enumerate(self.pages)]
        }

        extracted_tables_content = {
            "job_id": job_id,
            "file_name": file_name,
            "pages": [{"page_number": i + 1, "tables": self.tables.get(i + 1, [])} for i in range(len(self.pages))]
        }

        extracted_text_key = f"{app_id}/{job_id}/{file_name}/extracted_text.json"
        s3_client.put_object(
            Bucket=bucket,
            Key=extracted_text_key,
            Body=json.dumps(extracted_text_content),
            ContentType="application/json",
        )

        extracted_tables_key = f"{app_id}/{job_id}/{file_name}/extracted_tables.json"
        s3_client.put_object(
            Bucket=bucket,
            Key=extracted_tables_key,
            Body=json.dumps(extracted_tables_content),
            ContentType="application/json",
        )

        metadata_key = f"{app_id}/{job_id}/{file_name}/metadata.json"
        try:
            metadata_obj = s3_client.get_object(Bucket=bucket, Key=metadata_key)
            metadata = json.loads(metadata_obj['Body'].read().decode('utf-8'))
        except s3_client.exceptions.NoSuchKey:
            metadata = {"job_id": job_id, "files": []}

        metadata["files"].append({
            "file_name": file_name,
            "extracted_text_key": extracted_text_key,
            "extracted_tables_key": extracted_tables_key
        })

        s3_client.put_object(
            Bucket=bucket,
            Key=metadata_key,
            Body=json.dumps(metadata),
            ContentType="application/json",
        )

class Extraction:
    def __init__(self, region_name):
        self.region_name = region_name

    def extract(self, document_path):
        extractor = Textractor(region_name=self.region_name)
        client_request_token = str(uuid.uuid4())
        document = extractor.start_document_analysis(
            file_source=document_path,
            features=[TextractFeatures.LAYOUT, TextractFeatures.TABLES],
            client_request_token=client_request_token,
            save_image=False,
        )
        return document.job_id

    def extract_nonpdf(self, s3_bucket, s3_key):
        # read s3 object
        s3_client = boto3.client("s3", region_name=self.region_name)
        s3_obj = s3_client.get_object(Bucket=s3_bucket, Key=s3_key)
        file_content = s3_obj["Body"].read()
        file_name = s3_key.split("/")[-1]
        if isinstance(file_content, bytes):
            file_content = file_content.decode("utf-8")
        pages = [file_content]
        return ExtractedDocument(pages=pages, tables={}, all_text=file_content, input_path=file_name)

    def extract_tables_from_page(self, page_text):
        tables = re.findall(r"<table>.*?</table>", page_text, re.DOTALL)
        page_no_tables_text = re.sub(r"<table>.*?</table>", "", page_text, flags=re.DOTALL)
        tables_text = [table.strip() for table in tables]
        return page_no_tables_text, tables_text

    def get_document(self, job_id, file_name):
        textract_client = boto3.client("textract", region_name=self.region_name)
        lazy_doc = LazyDocument(
            job_id=job_id, textract_client=textract_client, api=TextractAPI.ANALYZE
        )

        config = TextLinearizationConfig(
            hide_figure_layout=True,
            title_prefix="<title>",
            title_suffix="</title>",
            text_prefix="<text>",
            text_suffix="</text>",
            section_header_prefix="<header>",
            section_header_suffix="</header>",
            table_prefix="<table>",
            table_suffix="</table>",
            # table_linearization_format="HTML",
            list_element_prefix="<list_element>",
            list_element_suffix="</list_element>",
            key_value_layout_prefix="<key_value>",
            key_value_layout_suffix="</key_value>",
            key_prefix="<key>",
            key_suffix="</key>",
            value_prefix="<value>",
            value_suffix="</value>",
            hide_footer_layout=True,
            hide_page_num_layout=True
            # table_row_prefix = "<tr>",
            # table_row_suffix = "</tr>",
            # table_cell_prefix = "<td>",
            # table_cell_suffix = "</td>"
        )

        e_pages = []
        all_text = ""
        all_tables = {}
        for page_number, page in enumerate(lazy_doc.pages, start=1):
            page_text = page.get_text(config=config)
            page_no_tables_text, tables = self.extract_tables_from_page(page_text)
            all_text += "<page>" + page_text + "</page>"
            all_tables[page_number] = tables
            e_pages.append(page_text)

        return ExtractedDocument(pages=e_pages, tables=all_tables, all_text=all_text, input_path=file_name)
