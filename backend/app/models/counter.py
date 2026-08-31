from beanie import Document


class Counter(Document):
    # _id is the chain name (set via raw motor find_one_and_update in HashChain);
    # accessed through the motor collection, never loaded via Beanie.
    value: int = 0

    class Settings:
        name = "counters"
