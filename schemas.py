from pydantic import BaseModel
from typing import List


class DocumentUploadResponse(BaseModel):
    status: str
    filename: str
    message: str


class UserAuthPayload(BaseModel):
    user_id: str
    role: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    user_id: str
