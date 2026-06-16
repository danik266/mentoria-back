from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any

class UserCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    name: str
    email: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

# Quiz Schema
class QuizItem(BaseModel):
    question: str
    options: List[str]
    correct: int

# Lesson Schema
class Lesson(BaseModel):
    id: str
    title: str
    content: List[str]
    quiz: List[QuizItem]

# Course Schema
class Course(BaseModel):
    id: str
    title: str
    description: str
    level: str
    icon: str
    gradient: str
    tags: List[str]
    lessonsCount: Optional[int] = 4
    lessons: Optional[List[Lesson]] = []

# Opportunity Schema
class Opportunity(BaseModel):
    id: str
    title: str
    category: str
    deadline: str  # YYYY-MM-DD
    grades: List[int]
    format: str
    description: str
    requirements: str
    tags: List[str]

# User Profile Schema
class UserProfile(BaseModel):
    name: Optional[str] = ""
    grade: Optional[int] = 8
    interests: Optional[List[str]] = []
    goals: Optional[List[str]] = []

# Full User Sync Payload
class UserSyncData(BaseModel):
    profile: Optional[UserProfile] = None
    progress: Optional[Dict[str, Dict[str, bool]]] = {}
    saved_opportunities: Optional[List[str]] = []

