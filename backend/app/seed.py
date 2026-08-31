import json
from backend.app.models import User


async def seed_users(path: str = "data/users.json") -> int:
    with open(path) as f:
        users = json.load(f)
    n = 0
    for u in users:
        if await User.find_one(User.username == u["username"]) is None:
            await User(username=u["username"], role=u["role"],
                       display_name=u["display_name"], password_hash=u["password_hash"]).insert()
            n += 1
    return n
