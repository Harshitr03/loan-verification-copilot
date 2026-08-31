from beanie import init_beanie
from backend.app.models import ALL_DOCUMENTS


async def init_db(client, db_name: str) -> None:
    await init_beanie(database=client[db_name], document_models=ALL_DOCUMENTS)
