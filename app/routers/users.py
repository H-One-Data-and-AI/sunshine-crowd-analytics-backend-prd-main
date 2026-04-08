# app/routers/users.py
import sqlite3
from typing import List, Literal
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator
from settings import DB_PATH
from auth import get_password_hash, get_current_admin_user, User

router = APIRouter(
    prefix="/users",
    tags=["User Management"],
    dependencies=[Depends(get_current_admin_user)]
)


# --- Pydantic Models for User Management ---

class UserCreate(BaseModel):
    email: EmailStr 
    role: Literal["admin", "user"] 
    password: str

    @field_validator('role', 'email')
    def no_html_tags(cls, v):
        if "<" in v or ">" in v or "script" in v:
            raise ValueError("Input contains forbidden characters")
        return v


class UserOut(User):
    pass


# --- Endpoint Definitions ---

@router.post("/", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(user: UserCreate):
    """
    Create a new user (admin only). A password is required.
    """
    hashed_password = get_password_hash(user.password)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (email, role, hashed_password) VALUES (?, ?, ?)",
            (user.email, user.role, hashed_password)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Email already registered.")
    finally:
        conn.close()

    return user


@router.get("/", response_model=List[UserOut])
def read_users():
    """
    Retrieve all users (admin only).
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT email, role FROM users").fetchall()
    conn.close()
    return [UserOut(**row) for row in rows]


@router.delete("/{email}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(email: str):
    """
    Delete a user by email (admin only).
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE email = ?", (email,))
    conn.commit()
    conn.close()
    return