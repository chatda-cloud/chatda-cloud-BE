from pydantic import BaseModel
 
 
class LoginRequest(BaseModel):
    user_id: str
    password: str
 
 
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
 
 
class TokenPayload(BaseModel):
    sub: str
    exp: int
 