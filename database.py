import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

client = AsyncIOMotorClient(MONGO_URI)
db = client.mentoria # Default database name

# Collections
users_collection = db.get_collection("users")
courses_collection = db.get_collection("courses")
opportunities_collection = db.get_collection("opportunities")
