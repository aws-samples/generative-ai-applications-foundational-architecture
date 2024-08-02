import requests
import time
import base64
import httpx
import requests
from config import conf
import boto3
import jwt
# from jwt.contrib.algorithms.pycrypto import RSAAlgorithm
# jwt.register_algorithm('RS256', RSAAlgorithm(RSAAlgorithm.SHA256))
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import base64
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def jwk_to_pem(jwk):
    exponent = base64.urlsafe_b64decode(jwk['e'] + '==')
    modulus = base64.urlsafe_b64decode(jwk['n'] + '==')
    
    public_numbers = rsa.RSAPublicNumbers(
        int.from_bytes(exponent, byteorder='big'),
        int.from_bytes(modulus, byteorder='big')
    )
    public_key = public_numbers.public_key(default_backend())
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return pem


class CognitoTokenManager:
    def __init__(self, client_id, client_secret, user_pool_id, region, domain):
        self.client_id = client_id
        self.client_secret = ""
        self.user_pool_id = user_pool_id
        self.region = region
        self.token = None
        self.expiry = 0
        self.domain = domain
    
    # return true if the token is valid
    async def validate_token_signature(self, token):
        try:
            keys = await get_cognito_public_keys()
            unverified_header = jwt.get_unverified_header(token)
            rsa_key_pem = None
            for key in keys["keys"]:
                if key["kid"] == unverified_header["kid"]:
                    rsa_key_pem = jwk_to_pem(key)
                    break
            if rsa_key_pem:
                payload = jwt.decode(
                    token,
                    rsa_key_pem,
                    algorithms=["RS256"],
                    options={"verify_signature": True, "verify_aud":False}
                )
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return False


    def get_token(self):
        current_time = time.time()
        if self.token is None or current_time >= self.expiry:
            self.token = self._fetch_token()
        return self.token

    def _fetch_token_with_secret(self):
        auth_header = base64.b64encode(f'{self.client_id}:{self.client_secret}'.encode('utf-8')).decode('utf-8')
        token_url = f'https://{self.domain}/oauth2/token'
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {auth_header}'
        }
        data = {
            'grant_type': 'client_credentials',
            'client_id': self.client_id,
            'scope': 'genaifoundations/read'
        }
        response = requests.post(token_url, headers=headers, data=data, timeout=60)
        if response.status_code == 200:
            token_data = response.json()
            self.expiry = time.time() + token_data['expires_in'] - 60  # Subtract 60 seconds to handle latency
            return token_data['access_token']
        else:
            raise Exception(f"Failed to get access token: {response.status_code} {response.text}")

    def _fetch_token(self):

        session = boto3.Session(region_name=conf.AWS_REGION)
        client = session.client('cognito-idp')

        # describe user pool client
        response = client.describe_user_pool_client(
            UserPoolId=self.user_pool_id,
            ClientId=self.client_id
        )

        # get client secret
        client_secret = response['UserPoolClient']['ClientSecret']
        self.client_secret = client_secret

        return self._fetch_token_with_secret()



async def get_cognito_public_keys():
    async with httpx.AsyncClient() as client:
        response = await client.get(conf.COGNITO_JWK_URL)
    response.raise_for_status()
    return response.json()

# Initialize the token manager
cognito_token_manager = CognitoTokenManager(conf.PLATFORM_APP_CLIENT_ID, "", conf.APP_USER_POOL_ID, conf.AWS_REGION, conf.PLATFORM_DOMAIN)
