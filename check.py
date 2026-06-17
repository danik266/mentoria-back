import asyncio
from database import courses_collection
async def check():
    c = await courses_collection.find_one({'id': 'c1'})
    print('Cover in DB:', c.get('cover'))
asyncio.run(check())
