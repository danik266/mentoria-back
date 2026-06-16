from fastapi import FastAPI, HTTPException, status, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from database import users_collection, courses_collection, opportunities_collection
from models import UserCreate, UserLogin, UserResponse, Token, UserSyncData, Course, Opportunity
from auth import get_password_hash, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY, ALGORITHM
from datetime import timedelta
from bson import ObjectId
from jose import jwt, JWTError
from seed_data import COURSES_DATA, OPPORTUNITIES_DATA

app = FastAPI()

# Allow CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup Seeding
@app.on_event("startup")
async def seed_db():
    courses_count = await courses_collection.count_documents({})
    if courses_count == 0:
        await courses_collection.insert_many(COURSES_DATA)
        print("Seeded default courses in database.")

    ops_count = await opportunities_collection.count_documents({})
    if ops_count == 0:
        await opportunities_collection.insert_many(OPPORTUNITIES_DATA)
        print("Seeded default opportunities in database.")
        
    admin_user = await users_collection.find_one({"email": "admin@mentoria.kz"})
    if not admin_user:
        hashed_password = get_password_hash("admin123")
        await users_collection.insert_one({
            "name": "Администратор",
            "email": "admin@mentoria.kz",
            "password": hashed_password,
            "is_admin": True,
            "profile": {
                "name": "Администратор",
                "grade": 11,
                "interests": [],
                "goals": []
            },
            "progress": {},
            "saved_opportunities": []
        })
        print("Seeded default admin user in database: admin@mentoria.kz / admin123")

# Helper to verify token and get current user
async def get_current_user(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid token")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token claims")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
    user = await users_collection.find_one({"email": email})
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user

@app.post("/api/auth/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register_user(user: UserCreate):
    existing_user = await users_collection.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = get_password_hash(user.password)
    # Check if first user or admin email to set admin role
    is_admin = False
    if user.email in ["admin@mentoria.kz", "admin@admin.com", "admin@mentoria.com"]:
        is_admin = True
        
    new_user = {
        "name": user.name,
        "email": user.email,
        "password": hashed_password,
        "is_admin": is_admin,
        "profile": {
            "name": user.name,
            "grade": 8,
            "interests": [],
            "goals": []
        },
        "progress": {},
        "saved_opportunities": []
    }
    
    result = await users_collection.insert_one(new_user)
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(result.inserted_id),
            "name": user.name,
            "email": user.email
        }
    }

@app.post("/api/auth/login", response_model=Token)
async def login_user(user: UserLogin):
    db_user = await users_collection.find_one({"email": user.email})
    if not db_user:
        raise HTTPException(status_code=400, detail="Invalid email or password")
        
    if not verify_password(user.password, db_user["password"]):
        raise HTTPException(status_code=400, detail="Invalid email or password")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(db_user["_id"]),
            "name": db_user["name"],
            "email": db_user["email"]
        }
    }

# Sync user data with MongoDB
@app.get("/api/sync")
async def sync_get(user = Depends(get_current_user)):
    courses_cursor = courses_collection.find({})
    courses = await courses_cursor.to_list(length=100)
    for c in courses:
        c["_id"] = str(c["_id"])
        
    ops_cursor = opportunities_collection.find({})
    ops = await ops_cursor.to_list(length=100)
    for o in ops:
        o["_id"] = str(o["_id"])
        
    profile = user.get("profile", {
        "name": user.get("name", ""),
        "grade": 8,
        "interests": [],
        "goals": []
    })
    progress = user.get("progress", {})
    saved = user.get("saved_opportunities", [])
    
    return {
        "courses": courses,
        "opportunities": ops,
        "profile": profile,
        "progress": progress,
        "saved": saved
    }

@app.post("/api/sync")
async def sync_post(data: UserSyncData, user = Depends(get_current_user)):
    update_data = {}
    if data.profile is not None:
        update_data["profile"] = data.profile.dict()
    if data.progress is not None:
        update_data["progress"] = data.progress
    if data.saved_opportunities is not None:
        update_data["saved_opportunities"] = data.saved_opportunities
        
    if update_data:
        await users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": update_data}
        )
    return {"status": "ok"}

# Admin CRUD - Courses
@app.post("/api/admin/courses")
async def admin_save_course(course: Course, user = Depends(get_current_user)):
    is_user_admin = user.get("is_admin", False) or user["email"] in ["admin@mentoria.kz", "admin@admin.com", "admin@mentoria.com"]
    if not is_user_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        
    course_dict = course.dict()
    existing = await courses_collection.find_one({"id": course.id})
    if existing:
        await courses_collection.update_one({"id": course.id}, {"$set": course_dict})
    else:
        await courses_collection.insert_one(course_dict)
    return {"status": "ok", "course": course_dict}

@app.delete("/api/admin/courses/{course_id}")
async def admin_delete_course(course_id: str, user = Depends(get_current_user)):
    is_user_admin = user.get("is_admin", False) or user["email"] in ["admin@mentoria.kz", "admin@admin.com", "admin@mentoria.com"]
    if not is_user_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        
    await courses_collection.delete_one({"id": course_id})
    return {"status": "ok"}

# Admin CRUD - Opportunities
@app.post("/api/admin/opportunities")
async def admin_save_opportunity(op: Opportunity, user = Depends(get_current_user)):
    is_user_admin = user.get("is_admin", False) or user["email"] in ["admin@mentoria.kz", "admin@admin.com", "admin@mentoria.com"]
    if not is_user_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        
    op_dict = op.dict()
    existing = await opportunities_collection.find_one({"id": op.id})
    if existing:
        await opportunities_collection.update_one({"id": op.id}, {"$set": op_dict})
    else:
        await opportunities_collection.insert_one(op_dict)
    return {"status": "ok", "opportunity": op_dict}

@app.delete("/api/admin/opportunities/{op_id}")
async def admin_delete_opportunity(op_id: str, user = Depends(get_current_user)):
    is_user_admin = user.get("is_admin", False) or user["email"] in ["admin@mentoria.kz", "admin@admin.com", "admin@mentoria.com"]
    if not is_user_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        
    await opportunities_collection.delete_one({"id": op_id})
    return {"status": "ok"}

# Admin - Student & Course Analytics
@app.get("/api/admin/analytics")
async def admin_analytics(user = Depends(get_current_user)):
    is_user_admin = user.get("is_admin", False) or user["email"] in ["admin@mentoria.kz", "admin@admin.com", "admin@mentoria.com"]
    if not is_user_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        
    # Get all users (except admins)
    users_cursor = users_collection.find({"email": {"$nin": ["admin@mentoria.kz", "admin@admin.com", "admin@mentoria.com"]}})
    students = await users_cursor.to_list(length=1000)
    
    total_students = len(students)
    active_students = 0
    total_completed_lessons = 0
    
    student_list = []
    for s in students:
        progress = s.get("progress", {})
        profile = s.get("profile", {})
        
        started_courses_count = len(progress)
        completed_lessons_count = sum(len(lessons) for lessons in progress.values())
        if started_courses_count > 0:
            active_students += 1
        total_completed_lessons += completed_lessons_count
        
        student_list.append({
            "id": str(s["_id"]),
            "name": profile.get("name") or s.get("name") or "Ученик",
            "email": s["email"],
            "grade": profile.get("grade", 8),
            "interests": profile.get("interests", []),
            "goals": profile.get("goals", []),
            "progress": progress,
            "completed_lessons": completed_lessons_count
        })
        
    # Fetch all courses to calculate completion metrics
    courses_cursor = courses_collection.find({})
    courses = await courses_cursor.to_list(length=100)
    
    course_stats = []
    for c in courses:
        course_id = c["id"]
        lessons_in_course = c.get("lessons", [])
        total_lessons = len(lessons_in_course)
        
        started_count = 0
        completed_count = 0
        
        for s in students:
            prog = s.get("progress", {}).get(course_id, {})
            completed_in_course = len(prog)
            if completed_in_course > 0:
                started_count += 1
            if total_lessons > 0 and completed_in_course == total_lessons:
                completed_count += 1
                
        course_stats.append({
            "id": course_id,
            "title": c["title"],
            "total_lessons": total_lessons,
            "started_students": started_count,
            "completed_students": completed_count
        })
        
    return {
        "total_students": total_students,
        "active_students": active_students,
        "total_completed_lessons": total_completed_lessons,
        "students": student_list,
        "courses": course_stats
    }
