from fastapi import FastAPI, HTTPException, status, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database import users_collection, courses_collection, opportunities_collection
from models import (
    UserCreate, UserLogin, UserResponse, Token, UserSyncData, Course, Opportunity,
    EmailConfirmRequest, ForgotPasswordRequest, ResetPasswordRequest
)
from auth import get_password_hash, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY, ALGORITHM
from datetime import timedelta, datetime, date
from bson import ObjectId
import os
from jose import jwt, JWTError
from seed_data import COURSES_DATA, OPPORTUNITIES_DATA
import asyncio
import random
from notifications import send_email, send_telegram
from telegram_bot import telegram_polling_worker

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")


async def deadline_notifier_loop():
    print("[Deadline Notifier] Starting background check loop...")
    while True:
        try:
            # Fetch all users
            users_cursor = users_collection.find({})
            users = await users_cursor.to_list(length=1000)
            
            # Fetch all opportunities
            opportunities_cursor = opportunities_collection.find({})
            opportunities = await opportunities_cursor.to_list(length=1000)
            
            for user in users:
                profile = user.get("profile", {})
                email_enabled = profile.get("email_notifications", True)
                tg_enabled = profile.get("telegram_notifications", True)
                chat_id = user.get("telegram_chat_id")
                
                if not email_enabled and not (tg_enabled and chat_id):
                    continue
                    
                user_interests = [i.lower() for i in profile.get("interests", [])]
                saved_ops = user.get("saved_opportunities", [])
                notified = user.get("notified_deadlines", [])
                
                for op in opportunities:
                    op_id = op["id"]
                    if op_id in notified:
                        continue
                        
                    try:
                        deadline_date = datetime.strptime(op["deadline"], "%Y-%m-%d").date()
                        today = date.today()
                        days_left = (deadline_date - today).days
                    except Exception:
                        continue
                        
                    # Notify if deadline is within 3 days
                    if 0 <= days_left <= 3:
                        op_tags = [t.lower() for t in op.get("tags", [])]
                        is_relevant = op_id in saved_ops or any(tag in user_interests for tag in op_tags)
                        
                        if is_relevant:
                            user_name = profile.get("name") or user.get("name", "Ученик")
                            msg_text = (
                                f"⏰ Внимание, {user_name}!\n\n"
                                f"Приближается дедлайн по направлению «{op.get('category', 'Возможность')}»!\n"
                                f"📌 Название: {op.get('title')}\n"
                                f"📅 Дата дедлайна: {op.get('deadline')} (осталось дней: {days_left})\n\n"
                                f"Не шали, давай участвуй! Ссылка на платформу: {FRONTEND_URL}/app/opportunities"
                            )
                            
                            sent_any = False
                            if email_enabled:
                                await send_email(
                                    to_email=user["email"],
                                    subject=f"Срочно: дедлайн по {op.get('title')}",
                                    body=msg_text
                                )
                                sent_any = True
                                
                            if tg_enabled and chat_id:
                                await send_telegram(
                                    chat_id=chat_id,
                                    text=msg_text
                                )
                                sent_any = True
                                
                            if sent_any:
                                await users_collection.update_one(
                                    {"_id": user["_id"]},
                                    {"$addToSet": {"notified_deadlines": op_id}}
                                )
                                print(f"[Deadline Notifier] Notified user {user['email']} about opportunity {op_id}")
                                
        except Exception as e:
            print(f"[Deadline Notifier Error] {e}")
            
        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    courses_count = await courses_collection.count_documents({})
    if courses_count == 0:
        await courses_collection.insert_many(COURSES_DATA)
        print("Seeded default courses in database.")

    ops_count = await opportunities_collection.count_documents({})
    if ops_count == 0:
        await opportunities_collection.insert_many(OPPORTUNITIES_DATA)
        print("Seeded default opportunities in database.")

    admin_user = await users_collection.find_one({"email": "admin@makquiz.site"})
    if not admin_user:
        hashed_password = get_password_hash("admin123")
        await users_collection.insert_one({
            "name": "Администратор",
            "email": "admin@makquiz.site",
            "password": hashed_password,
            "is_admin": True,
            "is_confirmed": True,
            "profile": {
                "name": "Администратор",
                "grade": 11,
                "interests": [],
                "goals": []
            },
            "progress": {},
            "saved_opportunities": []
        })
        print("Seeded default admin user in database: admin@makquiz.site / admin123")
        
    polling_task = asyncio.create_task(telegram_polling_worker())
    notifier_task = asyncio.create_task(deadline_notifier_loop())
    
    yield
    
    polling_task.cancel()
    notifier_task.cancel()


app = FastAPI(lifespan=lifespan)

# Allow CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://makquiz.site",
        "http://makquiz.site"
    ],
    allow_origin_regex="https://.*\\.vercel\\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "ты че запарил лее, бекенд работает"}

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

@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
async def register_user(user: UserCreate):
    existing_user = await users_collection.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = get_password_hash(user.password)
    is_admin = False
    if user.email in ["admin@makquiz.site", "admin@admin.com", "admin@makquiz.com"]:
        is_admin = True
        
    confirm_code = f"{random.randint(100000, 999999)}"
    
    new_user = {
        "name": user.name,
        "email": user.email,
        "password": hashed_password,
        "is_admin": is_admin,
        "is_confirmed": False,
        "confirm_code": confirm_code,
        "profile": {
            "name": user.name,
            "grade": 8,
            "interests": [],
            "goals": []
        },
        "progress": {},
        "saved_opportunities": []
    }
    
    await users_collection.insert_one(new_user)
    
    # Send confirmation code email
    subject = "Код подтверждения регистрации на Makquiz Hub"
    body = (
        f"👋 Привет, {user.name}!\n\n"
        f"Спасибо за регистрацию на образовательной платформе Makquiz Hub.\n"
        f"Ваш код подтверждения почты:\n\n"
        f"👉  {confirm_code}  👈\n\n"
        f"Введите его на странице верификации, чтобы активировать аккаунт.\n"
        f"Удачи в учебе!"
    )
    await send_email(to_email=user.email, subject=subject, body=body)
    
    return {
        "status": "confirmation_required",
        "email": user.email
    }

@app.post("/api/auth/confirm-email", response_model=Token)
async def confirm_email(payload: EmailConfirmRequest):
    user = await users_collection.find_one({"email": payload.email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user.get("is_confirmed"):
        # If already confirmed, just log them in
        pass
    else:
        saved_code = user.get("confirm_code")
        if not saved_code or saved_code != payload.code.strip():
            raise HTTPException(status_code=400, detail="Invalid verification code")
            
        await users_collection.update_one(
            {"_id": user["_id"]},
            {
                "$set": {"is_confirmed": True},
                "$unset": {"confirm_code": ""}
            }
        )
        # Fetch updated user
        user = await users_collection.find_one({"_id": user["_id"]})
        
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user["email"]}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": str(user["_id"]),
            "name": user["name"],
            "email": user["email"]
        }
    }

@app.post("/api/auth/resend-confirmation")
async def resend_confirmation(payload: ForgotPasswordRequest):
    user = await users_collection.find_one({"email": payload.email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if user.get("is_confirmed"):
        return {"status": "already_confirmed"}
        
    new_code = f"{random.randint(100000, 999999)}"
    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"confirm_code": new_code}}
    )
    
    subject = "Новый код подтверждения — Makquiz Hub"
    body = (
        f"Ваш новый код подтверждения почты:\n\n"
        f"👉  {new_code}  👈\n\n"
        f"Введите его на сайте, чтобы активировать аккаунт."
    )
    await send_email(to_email=user["email"], subject=subject, body=body)
    return {"status": "code_resent"}

@app.post("/api/auth/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest):
    user = await users_collection.find_one({"email": payload.email})
    # If user doesn't exist, we return a success response anyway to avoid email enumeration security issues
    if not user:
        return {"status": "reset_code_sent"}
        
    reset_code = f"{random.randint(100000, 999999)}"
    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {"reset_code": reset_code}}
    )
    
    subject = "Код для сброса пароля — Makquiz Hub"
    body = (
        f"Здравствуйте!\n\n"
        f"Мы получили запрос на сброс пароля для вашей учетной записи Makquiz Hub.\n"
        f"Ваш одноразовый код для восстановления доступа:\n\n"
        f"👉  {reset_code}  👈\n\n"
        f"Если вы не запрашивали сброс пароля, проигнорируйте это письмо."
    )
    await send_email(to_email=user["email"], subject=subject, body=body)
    return {"status": "reset_code_sent"}

@app.post("/api/auth/reset-password")
async def reset_password(payload: ResetPasswordRequest):
    user = await users_collection.find_one({"email": payload.email})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    saved_code = user.get("reset_code")
    if not saved_code or saved_code != payload.code.strip():
        raise HTTPException(status_code=400, detail="Invalid or expired reset code")
        
    hashed_password = get_password_hash(payload.new_password)
    await users_collection.update_one(
        {"_id": user["_id"]},
        {
            "$set": {"password": hashed_password},
            "$unset": {"reset_code": ""}
        }
    )
    
    # Notify user that password was changed
    subject = "Пароль успешно изменен — Makquiz Hub"
    body = (
        f"Уважаемый пользователь!\n\n"
        f"Пароль для вашей учетной записи {payload.email} на Makquiz Hub был успешно изменен.\n"
        f"Если вы этого не делали, немедленно свяжитесь с поддержкой."
    )
    await send_email(to_email=user["email"], subject=subject, body=body)
    return {"status": "password_reset_success"}

@app.post("/api/auth/login", response_model=Token)
async def login_user(user: UserLogin):
    db_user = await users_collection.find_one({"email": user.email})
    if not db_user:
        raise HTTPException(status_code=400, detail="Invalid email or password")
        
    if not verify_password(user.password, db_user["password"]):
        raise HTTPException(status_code=400, detail="Invalid email or password")

    if not db_user.get("is_confirmed", False):
        raise HTTPException(status_code=400, detail="Email not confirmed")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user["email"]}, expires_delta=access_token_expires
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
    
    from telegram_bot import get_bot_username
    return {
        "courses": courses,
        "opportunities": ops,
        "profile": profile,
        "progress": progress,
        "saved": saved,
        "telegram_bot_username": get_bot_username()
    }

@app.post("/api/sync")
async def sync_post(data: UserSyncData, user = Depends(get_current_user)):
    update_data = {}
    if data.profile is not None:
        update_data["profile"] = data.profile.model_dump()
    if data.progress is not None:
        update_data["progress"] = data.progress
    if data.saved_opportunities is not None:
        update_data["saved_opportunities"] = data.saved_opportunities
        
    if update_data:
        await users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": update_data}
        )
        
    # Check for newly completed courses and trigger certificate notifications
    if data.progress is not None:
        try:
            courses_cursor = courses_collection.find({})
            all_courses = await courses_cursor.to_list(length=100)
            
            profile = data.profile.model_dump() if data.profile is not None else user.get("profile", {})
            # Fetch latest user document to avoid race conditions with previous sync operations
            latest_user = await users_collection.find_one({"_id": user["_id"]})
            completed_certs = latest_user.get("completed_certificates", [])
            chat_id = latest_user.get("telegram_chat_id")
            
            for course in all_courses:
                course_id = course["id"]
                if course_id in completed_certs:
                    continue
                    
                lessons_in_course = [l["id"] for l in course.get("lessons", [])]
                if not lessons_in_course:
                    continue
                    
                user_course_progress = data.progress.get(course_id, {})
                completed_lessons_count = sum(1 for lid in lessons_in_course if user_course_progress.get(lid) is True)
                
                is_completed = completed_lessons_count == len(lessons_in_course)
                
                if is_completed:
                    user_name = profile.get("name") or latest_user.get("name", "Ученик")
                    cert_url = f"{FRONTEND_URL}/certificate/{course_id}"
                    
                    msg_text = (
                        f"🎓 Поздравляем, {user_name}!\n\n"
                        f"Вы успешно завершили курс «{course.get('title')}»!\n"
                        f"За ваши успехи и старания вам сгенерирован именной сертификат.\n\n"
                        f"Посмотреть и скачать сертификат можно по ссылке:\n{cert_url}\n\n"
                        f"Так держать! Продолжайте обучение на Makquiz Hub!"
                    )
                    
                    email_enabled = profile.get("email_certs", True)
                    tg_enabled = profile.get("telegram_certs", True)
                    
                    if email_enabled:
                        await send_email(
                            to_email=latest_user["email"],
                            subject=f"Поздравляем с окончанием курса: {course.get('title')}!",
                            body=msg_text
                        )
                        
                    if tg_enabled and chat_id:
                        await send_telegram(
                            chat_id=chat_id,
                            text=msg_text
                        )
                        
                    await users_collection.update_one(
                        {"_id": latest_user["_id"]},
                        {"$addToSet": {"completed_certificates": course_id}}
                    )
                    print(f"[Certificate Trigger] Sent certificate for course {course_id} to user {latest_user['email']}")
        except Exception as e:
            print(f"[Certificate Trigger Error] {e}")
            
    return {"status": "ok"}


# Admin CRUD - Courses
@app.post("/api/admin/courses")
async def admin_save_course(course: Course, user = Depends(get_current_user)):
    is_user_admin = user.get("is_admin", False) or user["email"] in ["admin@makquiz.site", "admin@admin.com", "admin@makquiz.com"]
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
    is_user_admin = user.get("is_admin", False) or user["email"] in ["admin@makquiz.site", "admin@admin.com", "admin@makquiz.com"]
    if not is_user_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        
    await courses_collection.delete_one({"id": course_id})
    return {"status": "ok"}

# Admin CRUD - Opportunities
@app.post("/api/admin/opportunities")
async def admin_save_opportunity(op: Opportunity, user = Depends(get_current_user)):
    is_user_admin = user.get("is_admin", False) or user["email"] in ["admin@makquiz.site", "admin@admin.com", "admin@makquiz.com"]
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
    is_user_admin = user.get("is_admin", False) or user["email"] in ["admin@makquiz.site", "admin@admin.com", "admin@makquiz.com"]
    if not is_user_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        
    await opportunities_collection.delete_one({"id": op_id})
    return {"status": "ok"}

# Admin - Student & Course Analytics
@app.get("/api/admin/analytics")
async def admin_analytics(user = Depends(get_current_user)):
    is_user_admin = user.get("is_admin", False) or user["email"] in ["admin@makquiz.site", "admin@admin.com", "admin@makquiz.com"]
    if not is_user_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
        
    # Get all users (except admins)
    users_cursor = users_collection.find({"email": {"$nin": ["admin@makquiz.site", "admin@admin.com", "admin@makquiz.com"]}})
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
