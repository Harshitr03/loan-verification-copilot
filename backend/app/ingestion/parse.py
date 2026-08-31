import io
import pandas as pd


def read_upload(content: bytes, filename: str) -> list[dict]:
    df = pd.read_csv(io.BytesIO(content), dtype=str, keep_default_na=False)
    return df.to_dict(orient="records")
