from fastapi import Request, HTTPException, Depends
import jwt
from utils import get_cognito_public_keys
import json
import config
from utils import cognito_token_manager
# from jwt.contrib.algorithms.pycrypto import RSAAlgorithm
# jwt.register_algorithm('RS256', RSAAlgorithm(RSAAlgorithm.SHA256))
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import base64
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

conf = config.ConfManager()

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

async def verify_token(request: Request):
    id_token = request.cookies.get("access_token")
    if not id_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        keys = await get_cognito_public_keys()
        unverified_header = jwt.get_unverified_header(id_token)
        rsa_key_pem = None
        for key in keys["keys"]:
            if key["kid"] == unverified_header["kid"]:
                rsa_key_pem = jwk_to_pem(key)
                break

        if rsa_key_pem:
            payload = jwt.decode(
                id_token,
                rsa_key_pem,
                algorithms=["RS256"],
                options={"verify_signature": True, "verify_aud":False}
            )

            return payload
        else:
            print("Invalid token header")
            raise HTTPException(status_code=401, detail="Invalid token header")
    except jwt.PyJWTError as e:
        logger.error(f"Token verification failed: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Token verification failed: {str(e)}")

def get_cognito_token():
    return cognito_token_manager.get_token()
