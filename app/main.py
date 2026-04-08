import os
from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from routers import location, cargills, competitor, scoring, users # Add users router
from auth import authenticate_user, create_access_token, Token # Import auth functions
import requests
from pydantic import BaseModel
import sqlite3
from settings import DB_PATH

# SHOW_DOCS_URL = "/docs" if os.getenv("ENVIRONMENT") == "development" else None
# SHOW_REDOC_URL = "/redoc" if os.getenv("ENVIRONMENT") == "development" else None
# SHOW_OPENAPI_URL = "/openapi.json" if os.getenv("ENVIRONMENT") == "development" else None


app = FastAPI(
    title="Crowd Analytics API"
    # docs_url=SHOW_DOCS_URL,   
    # redoc_url=SHOW_REDOC_URL,
    # openapi_url=SHOW_OPENAPI_URL
)

origins = [
    "http://localhost:8000",                          
    "https://sunshineca-be-sea.azurewebsites.net/",
    "https://sunshineca-be-sea.azurewebsites.net" 
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    
    response.headers["X-Content-Type-Options"] = "nosniff"
    
    response.headers["Permissions-Policy"] = "geolocation=(self), microphone=(), camera=()"
    
    csp_policy = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://apis.google.com https://login.microsoftonline.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://api.maptiler.com https://login.microsoftonline.com https://graph.microsoft.com; "
        "frame-src 'self' https://login.microsoftonline.com;"
    )

    response.headers["Content-Security-Policy"] = csp_policy
    
    return response

class MicrosoftTokenRequest(BaseModel):
    access_token: str

@app.post("/auth/microsoft", tags=["Authentication"])
async def microsoft_auth(token_data: MicrosoftTokenRequest):
    """
    1. Receive Microsoft Token from Frontend
    2. Call Microsoft Graph API to verify token and get Email
    3. Check Local DB for Email
    4. Issue JWT Token with correct Role
    """
    
    # 1. VERIFY TOKEN WITH MICROSOFT
    headers = {"Authorization": f"Bearer {token_data.access_token}"}
    graph_response = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers)
    
    if graph_response.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid Microsoft Token")
    
    ms_user = graph_response.json()
    # Get email (Microsoft sometimes uses 'mail' or 'userPrincipalName')
    email = ms_user.get("mail") or ms_user.get("userPrincipalName")
    
    if not email:
        raise HTTPException(status_code=400, detail="Could not retrieve email from Microsoft account")

    # 2. CHECK LOCAL DATABASE FOR USER & ROLE
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT role FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        # Reject login if Admin hasn't added them yet
        raise HTTPException(
            status_code=403, 
            detail=f"User {email} is not registered. Please ask an Admin to add you."
        )
    
    # User found! Get their specific role (admin/viewer)
    user_role = row[0]
    
    # 3. ISSUE APP TOKEN
    # This token now lets them act as 'admin' or 'user' based on DB
    access_token = create_access_token(data={"sub": email, "role": user_role})
    
    return {"access_token": access_token, "token_type": "bearer"}

# --- NEW: Login Endpoint ---
@app.post("/token", response_model=Token, tags=["Authentication"])
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)  # username is the email
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # --- THIS IS THE KEY CHANGE ---
    # Create a dictionary with both email (sub) and role
    token_data = {"sub": user.email, "role": user.role}

    access_token = create_access_token(data=token_data)
    return {"access_token": access_token, "token_type": "bearer"}

# --- Include Routers ---
app.include_router(location.router)
app.include_router(cargills.router)
app.include_router(competitor.router)
app.include_router(scoring.router)
app.include_router(users.router) # Add the new users router
