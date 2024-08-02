import boto3
import json
import uuid
from langchain_community.vectorstores import OpenSearchVectorSearch
from langchain_community.embeddings.bedrock import BedrockEmbeddings
from langchain_community.docstore.document import Document
from requests_aws4auth import AWS4Auth
from opensearchpy import RequestsHttpConnection, AWSV4SignerAuth
from opensearchpy import OpenSearch, helpers
from urllib.parse import urlparse
import re
import uuid
import concurrent.futures

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("document_processor")
logger.setLevel(logging.INFO)


def embed_document(embeddings, doc, index):
    return index, embeddings.embed_documents([doc.page_content])[0]

class OpenSearchVectorDB:
    """A class to represent and interface with an OpenSearch Vector database."""

    AOSS_SVC_NAME = "aoss"
    DEFAULT_TIMEOUT = 100

    def __init__(self, host=None, index_name=None, use_ssl=True, verify_certs=True, timeout=DEFAULT_TIMEOUT, region_name=None):
        """Initializes the OpenSearch Vector DB."""
        self.host = host
        self.index_name = index_name
        self.use_ssl = use_ssl
        self.verify_certs = verify_certs
        self.timeout = timeout
        self.embeddings = BedrockEmbeddings()
        self.region_name = region_name
        self.opensearch_auth = AWSV4SignerAuth(
            boto3.Session().get_credentials(), self.region_name, self.AOSS_SVC_NAME)

        # Initialize vector search object
        self.docsearch = OpenSearchVectorSearch(
            opensearch_url=self.host,
            index_name=self.index_name,
            embedding_function=self.embeddings,
            http_auth=self.opensearch_auth,
            timeout=self.timeout,
            use_ssl=self.use_ssl,
            verify_certs=self.verify_certs,
            connection_class=RequestsHttpConnection,
        )

    def read_s3_txt(self, s3_txt_path, bucket_name, s3_client):
        """Reads the text from an S3 file."""
        response = s3_client.get_object(Bucket=bucket_name, Key=s3_txt_path)
        txt = response['Body'].read().decode('utf-8')
        # print(txt)
        return txt

    def vectorize_and_store(self, data=None):
        """Converts JSON data into chunks and vectors and stores them in OpenSearch."""

        try:
            if data is not None:
                chunks = json.loads(data)

            # Create langchain documents
            docs = [Document(page_content=chunk['chunk']) for chunk in chunks]

            # Use ThreadPoolExecutor to parallelize the embedding process
            with concurrent.futures.ThreadPoolExecutor() as executor:
                futures = [executor.submit(embed_document, self.embeddings, doc, i) for i, doc in enumerate(docs)]
                results = [future.result() for future in concurrent.futures.as_completed(futures)]

            # Sort results by the original order
            results.sort(key=lambda x: x[0])
            vectors = [result[1] for result in results]

            mapping_tuples = [(doc.page_content, vectors[i])
                              for i, doc in enumerate(docs)]

            # Add embeddings to OpenSearch
            self.docsearch.add_embeddings(
                text_embeddings=mapping_tuples, text_field="text", vector_field="vector_field")

            return ""

        except Exception as e:
            raise Exception(f"Error occurred during vectorization: {e}")
            

    def similarity_search(self, query, text_field="text", vector_field="vector_field"):
        """Searches the OpenSearch index for documents similar to the provided query."""
        sim_docs = self.docsearch.similarity_search(
            query, text_field=text_field, vector_field=vector_field)
        
        sim_docs = [{"text": doc.page_content} for doc in sim_docs]

        return sim_docs