import requests
import time
import base64
import httpx
import requests
import boto3

class CognitoTokenManager:
    def __init__(self, client_id, client_secret, user_pool_id, region, domain):
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_pool_id = user_pool_id
        self.region = region
        self.token = None
        self.expiry = 0
        self.domain = domain

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
        response.raise_for_status()
        if response.status_code == 200:
            token_data = response.json()
            self.expiry = time.time() + token_data['expires_in'] - 60  # Subtract 60 seconds to handle latency
            return token_data['access_token']
        else:
            raise Exception(f"Failed to get access token: {response.status_code} {response.text}")


async def get_cognito_public_keys():
    async with httpx.AsyncClient() as client:
        response = await client.get(conf.COGNITO_JWK_URL)
    response.raise_for_status()
    return response.json()
