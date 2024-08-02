import json
from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse
from datetime import datetime
import boto3
import requests
from config import conf
from dependencies import verify_token, get_cognito_token
# from models import Apps
from relay_routes import router as relay_router
from relay_routes import init_relay_router
from metric_routes import router as metrics_router
from utils import cognito_token_manager
import logging
import uuid

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Generative AI Foundations API",
    version="0.1",
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

@app.middleware("http")
async def add_cors_header(request: Request, call_next):
    response = await call_next(request)
    response.headers['Access-Control-Allow-Origin'] = conf.CORS_ORIGIN
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Content-Security-Policy'] = (
        f"default-src 'self'; "
        f"script-src 'self'; "
        f"style-src 'self'; "
        f"connect-src 'self' {conf.CORS_ORIGIN};"
    )
    return response


# If you want to test locally, uncomment the below code
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://localhost:3001"], 
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

def add_app_client_to_dynamodb(client_id, app_name, secret_arn, description):
    session = boto3.Session(region_name=conf.AWS_REGION)
    dynamodb = session.client('dynamodb')

    logger.info(f"Adding app client to dynamodb: {conf.DYNAMODB_TABLE_NAME}")

    dynamodb.put_item(
        TableName=conf.DYNAMODB_TABLE_NAME,
        Item={
            "app_id": {"S": str(uuid.uuid4())},
            "client_id": {"S": client_id},
            "status": {"S": "active"},
            "app_name": {"S": app_name},
            "secret_arn": {"S": secret_arn},
            "description": {"S": description},
            "date_created": {"S": str(datetime.now())}
        }
    )

    return {"client_id": client_id, "client_secret_arn": secret_arn}

def add_default_app_client_if_not_exists(platform_app_client):
    session = boto3.Session(region_name=conf.AWS_REGION)
    dynamodb = session.client('dynamodb')
    response = dynamodb.scan(TableName=conf.DYNAMODB_TABLE_NAME)
    items = response.get("Items", [])
    
    ## Check if the default app client exists
    for item in items:
        if item.get("client_id", {}).get("S") == platform_app_client:
            return

    logger.info(f"Adding default app client to dynamodb: {conf.DYNAMODB_TABLE_NAME}")

    add_app_client_to_dynamodb(platform_app_client, "AdminUIBackend", "", "Backend for Admin UI")

    return




def fetch_openapi_spec():
    logger.info("Fetching OpenAPI spec")
    try:
        token = cognito_token_manager.get_token()
        headers = {"Authorization": f"Bearer {token}"}
        spec_links = ['model/service/meta', 'document/service/meta', 'vector/service/meta', 'prompt/service/meta']
        spec_jsons = []

        for link in spec_links:
            logger.info(f"Fetching OpenAPI spec from: {link}")
            response = requests.get(f'{conf.PLATFORM_BASE_URL}{link}', headers=headers, timeout=60)
            response.raise_for_status()
            if response.status_code == 200:
                logger.info(f"OpenAPI spec fetched successfully from: {link}")
                spec_jsons.append(response.json())

        main_spec = {
            "openapi": "3.0.2",
            "info": {
                "title": "Generative AI Foundations API",
                "version": "0.1"
            },
            "paths": {},
            "components": {
                "schemas": {}
            }
        }

        for spec in spec_jsons:
            for path, path_item in spec.get("paths", {}).items():
                new_path = f"{path}"
                main_spec["paths"][new_path] = path_item
            main_spec["components"]["schemas"].update(spec.get("components", {}).get("schemas", {}))

        # print(main_spec)
        import pprint
        conf.OPENAPI_SPEC= main_spec
        # pprint.pprint(conf.OPENAPI_SPEC)
        return main_spec
    except Exception as e:
        logger.error(f"Failed to fetch OpenAPI spec: {e}")
        logger.info(f"Falling back to default OpenAPI spec: {e}")
    



@app.get("/admin/docs")
async def get_docs(payload: dict = Depends(verify_token)):
    return get_swagger_ui_html(openapi_url="/openapi.json", title="Swagger UI")

@app.get("/admin/platform/openapi.json")
async def get_openapi(payload: dict = Depends(verify_token), token: str = Depends(get_cognito_token)):
    return fetch_openapi_spec()


@app.post("/admin/set_cookie", include_in_schema=False)
async def set_cookie(request: Request, response: Response):
    try:
        logger.info("Setting cookie")

        # Fetch id_token from Authorization header
        id_token = request.headers.get("Authorization")

        # Remove Bearer from id_token
        if id_token:
            id_token = id_token.replace("Bearer ", "")

        logger.info(f"ID Token: {id_token}")
        
        if not id_token:
            raise HTTPException(status_code=400, detail="No id_token provided")

        # Validate id_token
        is_valid_token = await cognito_token_manager.validate_token_signature(id_token)
        if not is_valid_token:
            logger.error("Invalid id_token")
            raise HTTPException(status_code=401, detail="Invalid id_token")

        logger.info("ID Token is valid")
        response = JSONResponse(content={"message": "Cookie set successfully"}, status_code=200)
        response.set_cookie("access_token", id_token, httponly=True, max_age=3600, samesite="None", secure=True)
        response.delete_cookie("id_token")
        logger.info(response.headers)
        return response
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@app.get("/admin/unset_cookie", include_in_schema=False)
async def unset_cookie(response: Response):
    response = JSONResponse(content={"message": "Cookie unset successfully"}, status_code=200)
    response.set_cookie("access_token", "", httponly=True, max_age=0, samesite="None", secure=True)
    return response

@app.get("/admin/auth/status")
async def auth_status(payload: dict = Depends(verify_token)):
    return {"message": "You are authenticated"}


@app.get("/admin/platform/services/health")
async def services_health(payload: dict = Depends(verify_token), token: str = Depends(get_cognito_token)):
    services = conf.PLARFORM_SERVICES
    statuses = []
    headers = {"Authorization": f"Bearer {token}"}

    for service, details in services.items():
        service_url = details.get("service_url")
        try:
            response = requests.get(f'{conf.PLATFORM_BASE_URL}{service_url}', headers=headers, timeout=60)
            response.raise_for_status()
        except Exception as e:
            statuses.append({"service_name": details['service_name'], "status": "unhealthy"})
            continue
        status = "healthy" if response.status_code == 200 else "unhealthy"
        statuses.append({"service_name": details['service_name'], "status": status})
    
    return statuses


@app.post("/admin/platform/create_app_client")
async def create_app_client(request: Request, payload: dict = Depends(verify_token)):
    client = boto3.client("cognito-idp", region_name=conf.AWS_REGION)
    data = await request.json()

    # Validate data
    if not data.get("app_name") or data.get("app_name").strip() == "":
        raise HTTPException(status_code=400, detail="app_name is required")
    if not data.get("description") or data.get("description").strip() == "":
        raise HTTPException(status_code=400, detail="description is required")

    app_name = data.get("app_name")
    description = data.get("description")
    secrets_manager_client = boto3.client("secretsmanager", region_name=conf.AWS_REGION)

    try:
        response = client.create_user_pool_client(
            UserPoolId=conf.APP_USER_POOL_ID,
            ClientName=app_name,
            GenerateSecret=True,
            SupportedIdentityProviders=['COGNITO'],
            AllowedOAuthFlows=['client_credentials'],
            AllowedOAuthScopes=['genaifoundations/read'],
            AllowedOAuthFlowsUserPoolClient=True,
            ExplicitAuthFlows=['ALLOW_USER_SRP_AUTH', 'ALLOW_REFRESH_TOKEN_AUTH']
        )

        client_id = response["UserPoolClient"]["ClientId"]
        client_secret = response["UserPoolClient"]["ClientSecret"]

        try:
            secret_name = f"{client_id}_client_secret"
            secret_response = secrets_manager_client.create_secret(
                Name=secret_name,
                SecretString=client_secret
            )
            secret_arn = secret_response["ARN"]
        except KeyError:
            secret_arn = "failed"
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

    logger.info(f"Adding app client to dynamodb: {conf.DYNAMODB_TABLE_NAME}")
    add_app_client_to_dynamodb(client_id, app_name, secret_arn, description)

    return {"client_id": client_id, "client_secret_arn": secret_arn, "status": "active"}


@app.post("/admin/platform/deactivate_app_client")
async def deactivate_app_client(request: Request, payload: dict = Depends(verify_token)):
    data = await request.json()
    app_id = data.get("app_id")
    session = boto3.Session(region_name=conf.AWS_REGION)
    dynamodb = session.client('dynamodb')

    try:

        dynamodb.update_item(
            TableName=conf.DYNAMODB_TABLE_NAME,
            Key={
                "app_id": {"S": app_id}
            },
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": {"S": "inactive"}},
            ConditionExpression="attribute_exists(app_id)"
        )

        return {"message": "Client deactivated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@app.post("/admin/platform/activate_app_client")
async def activate_app_client(request: Request, payload: dict = Depends(verify_token)):
    data = await request.json()
    app_id = data.get("app_id")
    session = boto3.Session(region_name=conf.AWS_REGION)
    dynamodb = session.client('dynamodb')

    try:

        dynamodb.update_item(
            TableName=conf.DYNAMODB_TABLE_NAME,
            Key={
                "app_id": {"S": app_id}
            },
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": {"S": "active"}},
            ConditionExpression="attribute_exists(app_id)"
        )

        return {"message": "Client activated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")

@app.get("/admin/platform/get_all_app_clients")
async def get_all_app_clients(payload: dict = Depends(verify_token)):
    try:
        logger.info(f"Fetching app clients {conf.DYNAMODB_TABLE_NAME}, {conf.AWS_REGION}")
        session = boto3.Session(region_name=conf.AWS_REGION)
        dynamodb = session.client('dynamodb')
        response = dynamodb.scan(TableName=conf.DYNAMODB_TABLE_NAME)
        items = response.get("Items", [])
        clients = []

        logger.info(f"Items: {items}")

        for item in items:
            try:
                client_id = item.get("client_id", {}).get("S")
                app_name = item.get("app_name", {}).get("S")
                secret_arn = item.get("secret_arn", {}).get("S")
                description = item.get("description", {}).get("S")
                date_created = item.get("date_created", {}).get("S")
                # format date_created
                date_created = datetime.strptime(date_created, "%Y-%m-%d %H:%M:%S.%f").strftime("%Y-%m-%d %H:%M:%S")
                app_id = item.get("app_id", {}).get("S")
                status = item.get("status", {}).get("S")
                clients.append({
                    "app_id": app_id,
                    "client_id": client_id,
                    "app_name": app_name,
                    "secret_arn": secret_arn,
                    "description": description,
                    "date_created": date_created,
                    "status": status,
                    "app_user_pool_id": conf.APP_USER_POOL_ID,
                    "platform_app_client_id": conf.PLATFORM_APP_CLIENT_ID,
                    "platform_domain": conf.PLATFORM_DOMAIN
                })
            except Exception as e:
                logger.error(f"Error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")
    
    return clients

@app.get("/admin/service/health")
async def health():
    return {"status": "Up"}, 200


@app.on_event("startup")
async def startup_event():
    logger.info("Fetching OpenAPI spec")
    logger.info(conf.get_conf())
    spec = fetch_openapi_spec()
    conf.OPENAPI_SPEC = spec
    init_relay_router()
    app.include_router(relay_router)
    app.include_router(metrics_router)
    add_default_app_client_if_not_exists(conf.PLATFORM_APP_CLIENT_ID)
