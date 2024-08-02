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


class OpenSearchServerlessManager:
    """Manages OpenSearch Serverless resources such as security policies and collections."""

    def __init__(self, region_name):
        """Initialize the OpenSearch Serverless client."""
        self.client = boto3.client(
            "opensearchserverless", region_name=region_name)

    def create_security_policy(self, name, policy_type, description, policy_json):
        """Creates a security policy in OpenSearch Serverless."""
        client_token = str(uuid.uuid4())  # Generate a unique client token

        response = self.client.create_security_policy(
            clientToken=client_token,
            description=description,
            name=name,
            policy=json.dumps(policy_json),  # Convert dict to JSON string
            type=policy_type
        )

        return response['securityPolicyDetail']

    def create_encryption_policy(self, name, description, collection_pattern):
        """Creates an encryption policy with a resource pattern that matches the collection name pattern."""
        policy_json = {
            "Rules": [
                {
                    "ResourceType": "collection",
                    "Resource": [f"collection/{collection_pattern}"]
                }
            ],
            "AWSOwnedKey": True  # Use AWS-managed encryption key
        }

        return self.create_security_policy(
            name=name,
            policy_type="encryption",
            description=description,
            policy_json=policy_json
        )

    def create_network_policy(self, name, description, collection_pattern, allow_public=False, vpce_id=None):
        """Creates a network policy with access rules for a specific collection pattern."""
        policy_json = [
            {
                "Description": description,
                "SourceVPCEs":[
                    vpce_id
                ],
                "Rules": [
                    {
                        "ResourceType": "dashboard",
                        "Resource": [f"collection/{collection_pattern}"]
                    },
                    {
                        "ResourceType": "collection",
                        "Resource": [f"collection/{collection_pattern}"]
                    }
                ],
                "AllowFromPublic": allow_public
            }
        ]

        return self.create_security_policy(
            name=name,
            policy_type="network",
            description=description,
            policy_json=policy_json
        )

    def create_data_access_policy(self, name, description, collection_pattern, index_name, role_arn, allow_public=True):
        """Creates a data access policy with access rules for a specific collection pattern."""
        policy_json = """[
            {
                "Rules": [
                    {
                        "ResourceType": "collection",
                        "Resource": ["collection/{collection_pattern}"],
                        "Permission": ["aoss:UpdateCollectionItems"]
                    },
                    {
                        "ResourceType": "index",
                        "Resource": ["index/{collection_pattern}/*"],
                        "Permission": ["aoss:CreateIndex","aoss:DeleteIndex","aoss:UpdateIndex","aoss:DescribeIndex","aoss:ReadDocument","aoss:WriteDocument"]
                    }
                ],
                "Principal": ["{role_arn}"]
            }
        ]"""
        policy_json = policy_json.replace("{collection_pattern}", collection_pattern).replace("{role_arn}", role_arn)
        print(policy_json)

        return self.client.create_access_policy(
            name=name,
            type="data",
            clientToken=str(uuid.uuid4()),
            description=description,
            policy=policy_json
        )

    def create_collection(self, collection_name, description="", standby_replicas="DISABLED", tags=None):
        """Creates an OpenSearch Serverless collection."""
        client_token = str(uuid.uuid4())  # Generate a unique client token
        tags = tags or []

        response = self.client.create_collection(
            clientToken=client_token,
            description=description,
            name=collection_name,
            standbyReplicas=standby_replicas,
            tags=tags,
            type='VECTORSEARCH'
        )

        return response['createCollectionDetail']



class OpenSearchVectorDB:
    """A class to represent and interface with an OpenSearch Vector database."""

    AOSS_SVC_NAME = "aoss"
    DEFAULT_TIMEOUT = 100

    

    def get_auth(self):
        credentials = self.session.get_credentials()

        access_key = credentials.access_key
        secret_key = credentials.secret_key
        token = credentials.token

        auth = AWS4Auth(access_key, secret_key,
                 self.region , 'aoss', session_token=token)

        return auth
        
        

    def __init__(self, host=None, index_name=None, region=None, use_ssl=True, verify_certs=True, timeout=DEFAULT_TIMEOUT):
        """Initializes the OpenSearch Vector DB."""
        self.host = host
        self.index_name = index_name
        self.use_ssl = use_ssl
        self.verify_certs = verify_certs
        self.timeout = timeout
        self.embeddings = BedrockEmbeddings()
        self.region = region
        self.session = boto3.Session(region_name=region)
        self.credentials = self.session.get_credentials()
        self.opensearch_auth = self.get_auth()
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

    def create_index(self, index_name=None):
        """Creates the OpenSearch index if it doesn't exist."""
        index_body = {
            "settings": {
                "index.knn": True
            },
            "mappings": {
                "properties": {
                    "vector_field": {
                        "type": "knn_vector",
                        "dimension": 1536
                    },
                    "text": {
                        "type": "text"
                    }
                }
            }
        }

        client = OpenSearch(
            hosts=[self.host],
            http_auth=self.opensearch_auth,
            use_ssl=self.use_ssl,
            verify_certs=self.verify_certs,
            connection_class=RequestsHttpConnection,
        )

        if not client.indices.exists(index_name):
            client.indices.create(index=index_name, body=index_body)

    def get_index_status(self, index_name=None):
        """Returns the status of the OpenSearch index."""
        client = OpenSearch(
            hosts=[self.host],
            http_auth=self.opensearch_auth,
            use_ssl=self.use_ssl,
            verify_certs=self.verify_certs,
            connection_class=RequestsHttpConnection,
        )

        return client.indices.get(index=index_name)

    def similarity_search(self, query, text_field="text", vector_field="vector_field"):
        """Searches the OpenSearch index for documents similar to the provided query."""
        sim_docs = self.docsearch.similarity_search(
            query, text_field=text_field, vector_field=vector_field)
        print(sim_docs)

        sim_docs = [{"text": doc.page_content} for doc in sim_docs]

        return sim_docs