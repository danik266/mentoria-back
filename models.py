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

# Activity schema (flexible - supports read/flashcards/match/quiz)
class Activity(BaseModel):
    type: str  # 'read' | 'flashcards' | 'match' | 'quiz'
    title: str
    content: Optional[List[Any]] = None      # for 'read'
    cards: Optional[List[Any]] = None        # for 'flashcards'
    pairs: Optional[List[Any]] = None        # for 'match'
    questions: Optional[List[Any]] = None    # for 'quiz'

# Lesson Schema
class Lesson(BaseModel):
    id: str
    title: str
    content: Optional[List[str]] = Field(default_factory=list)
    quiz: Optional[List[Any]] = Field(default_factory=list)
    activities: Optional[List[Activity]] = Field(default_factory=list)

# Course Schema
class Course(BaseModel):
    id: str
    title: str
    description: str
    level: str
    icon: str
    gradient: str
    cover: Optional[str] = None
    tags: List[str]
    lessonsCount: Optional[int] = 4
    lessons: Optional[List[Lesson]] = Field(default_factory=list)

# Opportunity Schema
class Opportunity(BaseModel):
    id: str
    title: str
    category: str
    deadline: str
    grades: List[int]
    format: str
    description: str
    requirements: str
    tags: List[str]

# User Profile Schema
class UserProfile(BaseModel):
    name: Optional[str] = ""
    grade: Optional[int] = 8
    interests: Optional[List[str]] = Field(default_factory=list)
    goals: Optional[List[str]] = Field(default_factory=list)

# Full User Sync Payload
class UserSyncData(BaseModel):
    profile: Optional[UserProfile] = None
    progress: Optional[Dict[str, Dict[str, bool]]] = Field(default_factory=dict)
    saved_opportunities: Optional[List[str]] = Field(default_factory=list)
