import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .domain import Role

bearer = HTTPBearer(auto_error=False)


def hash_password(password, salt=None):
    salt = secrets.token_hex(16) if salt is None else salt
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 300_000)
    return f'{salt}.{digest.hex()}'


def check_password(password, stored):
    return hmac.compare_digest(hash_password(password, stored.split('.', 1)[0]), stored)


def issue(user):
    now = datetime.now(timezone.utc)
    return jwt.encode({'sub': user['username'], 'role': user['role'], 'iat': now,
                       'exp': now + timedelta(hours=6), 'iss': 'vineyard-ledger'},
                      os.environ['JWT_SECRET'], algorithm='HS256')


def identity(token: HTTPAuthorizationCredentials | None = Depends(bearer)):
    try:
        if token is not None:
            claims = jwt.decode(token.credentials, os.environ['JWT_SECRET'], algorithms=['HS256'],
                                issuer='vineyard-ledger', options={'require': ['exp', 'iat', 'sub', 'role']})
            return {'name': claims['sub'], 'role': Role(claims['role'])}
    except (jwt.InvalidTokenError, ValueError):
        pass
    raise HTTPException(401, '请重新登录', headers={'WWW-Authenticate': 'Bearer'})


def require(*roles):
    def authorize(user=Depends(identity)):
        if user['role'] not in roles:
            raise HTTPException(403, '当前角色无权执行该操作')
        return user
    return authorize
