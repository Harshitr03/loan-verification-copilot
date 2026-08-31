from beanie import Document
import pymongo


class User(Document):
    username: str
    password_hash: str
    role: str                  # data_operator | reviewer | data_consumer
    display_name: str

    class Settings:
        name = "users"
        indexes = [pymongo.IndexModel([("username", pymongo.ASCENDING)], unique=True)]
