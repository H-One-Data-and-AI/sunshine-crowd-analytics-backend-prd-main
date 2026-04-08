# app/auth.py
import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
import sqlite3
from settings import DB_PATH
from dotenv import load_dotenv

load_dotenv()

# ... (Configuration and pwd_context remain the same) ...
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") # Ensure .env has SECRET_KEY, not JWT_SECRET_KEY
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


# --- Pydantic Models ---
class Token(BaseModel):
    access_token: str
    token_type: str

# --- UPDATED TokenData Model ---
class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None # Add the role field

class User(BaseModel):
    email: str
    role: str

class UserInDB(User):
    hashed_password: str

# --- Database Functions ---
# This is now only used for authentication, not for every request
def get_user_from_db(email: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    user_row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    if user_row:
        return UserInDB(**user_row)
    return None

# --- Security Functions ---
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def authenticate_user(email: str, password: str):
    user = get_user_from_db(email) # Renamed for clarity
    if not user or not verify_password(password, user.hashed_password):
        return False
    return user

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        # Let's use the configured expiration time
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- UPDATED Dependency to Get Current User ---
async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        role: str = payload.get("role") # <-- Extract the role from the payload
        if email is None or role is None:
            raise credentials_exception
        # No need to create TokenData model instance anymore, we have the data
    except JWTError:
        raise credentials_exception

    # We are trusting the token. We return a User model directly from the payload.
    # No database call is needed here anymore! This is much faster.
    return User(email=email, role=role)

# --- Dependency for Role-Based Access (No changes needed) ---
async def get_current_admin_user(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user does not have enough privileges"
        )
    return current_user