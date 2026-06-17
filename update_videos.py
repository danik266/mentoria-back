import asyncio
from database import courses_collection
import re

video_map = {
    "c1": "https://youtu.be/5rhP_KK5-gE?si=uhg4IojWjo5oB8ik",
    "c2": "https://youtu.be/gz3pNZfW6q8?si=1r1cIAypD4gdiEcf",
    "c3": "https://youtu.be/iTJgIgCtNi4?si=VEyvac91O98NlhHw",
    "c4": "https://youtu.be/H7z__L4tJeM?si=QNhr1I1ZLfNS6FCo",
    "c5": "https://youtu.be/gtSvosoQ_yE?si=_b6Sbwb0aKt95GrW",
    "c6": "https://youtu.be/Eh_3RN7zYB0?si=s-TG9SnUv8oL5ZJp",
    "c7": "https://youtu.be/683LM5yMTP0?si=bYISZwBUoiDEd6vp",
    "c8": "https://youtu.be/1CtueAjMCpU?si=EUqu9D3D-U_a30GT",
    "c9": "https://youtu.be/oNXz5G5LEjM?si=K-d1SAaR5fHHjFRU",
    "c10": "https://youtu.be/34Rp6KVGIEM?si=dwqf1jRdiwdFOHYC",
    "c11": "https://youtu.be/D9CXYkfad00?si=dy8TNxMtVxf2ltQV",
    "c12": "https://youtu.be/03eqUOrQ3Zw?si=WK-t1TtvL6CkdJ9d",
    "c13": "https://youtu.be/jE4eVmwU0JA?si=l35hJLXvGL21J1ZE",
    "c14": "https://youtu.be/MVtrwcrdRgY?si=74_elQYO7FtP3Yiq",
    "c15": "https://youtu.be/ChVYSWqwZYY?si=Dl-NJKa9pwO6KOdw",
}

def get_embed_url(url):
    match = re.search(r"youtu\.be/([a-zA-Z0-9_-]+)", url)
    if match:
        return f"https://www.youtube.com/embed/{match.group(1)}"
    return url

async def main():
    for c_id, url in video_map.items():
        embed_url = get_embed_url(url)
        
        course = await courses_collection.find_one({"id": c_id})
        if course and "lessons" in course and len(course["lessons"]) > 0:
            lessons = course["lessons"]
            lessons[0]["video_url"] = embed_url
            
            await courses_collection.update_one(
                {"id": c_id},
                {"$set": {"lessons": lessons}}
            )
            print(f"Updated {c_id} lesson 1 with video: {embed_url}")
        else:
            print(f"Skipped {c_id}")

if __name__ == "__main__":
    asyncio.run(main())
