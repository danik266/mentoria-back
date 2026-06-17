import asyncio
from database import courses_collection
from seed_data import COURSES_DATA

async def update_covers():
    count = 0
    for course in COURSES_DATA:
        if "cover" in course:
            await courses_collection.update_one(
                {"id": course["id"]},
                {"$set": {"cover": course["cover"]}}
            )
            count += 1
    print(f"Updated {count} courses with covers.")

if __name__ == "__main__":
    asyncio.run(update_covers())
