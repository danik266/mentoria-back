import asyncio
from database import courses_collection

async def update_all_covers():
    courses = await courses_collection.find({}).to_list(length=100)
    print(f"Total courses in DB: {len(courses)}")
    
    covers_map = {
        f"c{i}": f"/courses/{i}.{'png' if i in [1, 2, 4, 7, 8, 10, 11, 13, 14, 15] else 'jpg'}"
        for i in range(1, 16)
    }
    # Fix the mapping based on exactly what files we copied:
    # 1.png, 2.png, 3.jpg, 4.png, 5.jpg
    # 6.jpg, 7.png, 8.png, 9.jpg, 10.png
    # 11.png, 12.jpg, 13.png, 14.png, 15.png
    
    actual_covers = {
        "c1": "/courses/1.png",
        "c2": "/courses/2.png",
        "c3": "/courses/3.jpg",
        "c4": "/courses/4.png",
        "c5": "/courses/5.jpg",
        "c6": "/courses/6.jpg",
        "c7": "/courses/7.png",
        "c8": "/courses/8.png",
        "c9": "/courses/9.jpg",
        "c10": "/courses/10.png",
        "c11": "/courses/11.png",
        "c12": "/courses/12.jpg",
        "c13": "/courses/13.png",
        "c14": "/courses/14.png",
        "c15": "/courses/15.png"
    }

    count = 0
    for course in courses:
        cid = course.get("id")
        if cid in actual_covers:
            await courses_collection.update_one(
                {"id": cid},
                {"$set": {"cover": actual_covers[cid]}}
            )
            count += 1
            print(f"Updated {cid} with {actual_covers[cid]}")
            
    print(f"Total updated: {count}")

asyncio.run(update_all_covers())
