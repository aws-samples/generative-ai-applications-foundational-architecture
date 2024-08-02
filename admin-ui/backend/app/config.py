import os

# # For UI authentication
# COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID")
# COGNITO_JWK_URL = os.getenv("COGNITO_JWK_URL", "")
# AWS_REGION = os.getenv("AWS_REGION","")
# USER_POOL_ID = os.getenv("USER_POOL_ID")

# # For UI Backend authentication
# APP_USER_POOL_ID = os.getenv("APP_USER_POOL_ID")
# PLATFORM_APP_CLIENT_ID = os.getenv("PLATFORM_APP_CLIENT_ID")
# PLATFORM_APP_CLIENT_SECRET = os.getenv("PLATFORM_APP_CLIENT_SECRET")
# PLATFORM_DOMAIN = os.getenv("PLATFORM_DOMAIN")
# DYNAMODB_TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME")
# PLATFORM_BASE_URL = os.getenv("PLATFORM_BASE_URL")
# PLARFORM_SERVICES = os.getenv("PLARFORM_SERVICES")
# OPENAPI_SPEC = os.getenv("OPENAPI_SPEC")
# CORS_ORIGIN = os.getenv("CORS_ORIGIN")

# # Model Service
# INVOCATION_LOG_TABLE = os.getenv("INVOCATION_LOG_TABLE")

# PLARFORM_SERVICES = {
#     "document_processing": {
#         "service_name": "Extraction Service",
#         "service_url": "document/service/health",
#         "base_path": "/admin/document/"
#     },
#     "model_invocation": {
#         "service_name": "Model Invocation Service",
#         "service_url": "model/service/health",
#         "base_path": "/admin/model/"
#     }
# }

class ConfManager:
    def __init__(self):
        self.COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID")
        self.COGNITO_JWK_URL = os.getenv("COGNITO_JWK_URL", "")
        self.AWS_REGION = os.getenv("AWS_REGION","")
        self.USER_POOL_ID = os.getenv("USER_POOL_ID")
        self.APP_USER_POOL_ID = os.getenv("APP_USER_POOL_ID")
        self.PLATFORM_APP_CLIENT_ID = os.getenv("PLATFORM_APP_CLIENT_ID")
        self.PLATFORM_DOMAIN = os.getenv("PLATFORM_DOMAIN")
        self.DYNAMODB_TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME")
        self.PLATFORM_BASE_URL = os.getenv("PLATFORM_BASE_URL")
        self.PLARFORM_SERVICES = os.getenv("PLARFORM_SERVICES")
        self.OPENAPI_SPEC = os.getenv("OPENAPI_SPEC")
        self.CORS_ORIGIN = os.getenv("CORS_ORIGIN")
        self.INVOCATION_LOG_TABLE = os.getenv("INVOCATION_LOG_TABLE")
        self.PLARFORM_SERVICES = {
            "document_processing": {
                "service_name": "Extraction Service",
                "service_url": "document/service/health",
                "base_path": "/admin/document/"
            },
            "model_invocation": {
                "service_name": "Model Invocation Service",
                "service_url": "model/service/health",
                "base_path": "/admin/model/"
            },
            "vectorization": {
                "service_name": "Vectorization Service",
                "service_url": "vector/service/health",
                "base_path": "/admin/vector/"
            },
            "prompt_management": {
                "service_name": "Prompt Management Service",
                "service_url": "prompt/service/health",
                "base_path": "/admin/prompt/"
            }
        }

    def get_conf(self):
        return {
            "COGNITO_CLIENT_ID": self.COGNITO_CLIENT_ID,
            "COGNITO_JWK_URL": self.COGNITO_JWK_URL,
            "AWS_REGION": self.AWS_REGION,
            "USER_POOL_ID": self.USER_POOL_ID,
            "APP_USER_POOL_ID": self.APP_USER_POOL_ID,
            "PLATFORM_APP_CLIENT_ID": self.PLATFORM_APP_CLIENT_ID,
            "PLATFORM_DOMAIN": self.PLATFORM_DOMAIN,
            "DYNAMODB_TABLE_NAME": self.DYNAMODB_TABLE_NAME,
            "PLATFORM_BASE_URL": self.PLATFORM_BASE_URL,
            "PLARFORM_SERVICES": self.PLARFORM_SERVICES,
            "OPENAPI_SPEC": self.OPENAPI_SPEC,
            "CORS_ORIGIN": self.CORS_ORIGIN,
            "INVOCATION_LOG_TABLE": self.INVOCATION_LOG_TABLE
        }

conf = ConfManager()





