from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException, status
from backend.app.models import Dataset
from backend.app.auth import require_role, get_current_user
from backend.app.ingestion.service import ingest_dataset
from backend.app.validation.runner import run_validation

router = APIRouter(tags=["datasets"])


@router.post("/datasets")
async def upload_dataset(
    loan_tape: UploadFile = File(...),
    source_system: str = Form(...),
    servicer_update: UploadFile | None = File(None),
    document_manifest: UploadFile | None = File(None),
    user=Depends(require_role("data_operator")),
):
    async def _pair(f):
        return (f.filename, await f.read()) if f is not None else None

    ds = await ingest_dataset(await _pair(loan_tape), source_system, user.username,
                              servicer_update=await _pair(servicer_update),
                              document_manifest=await _pair(document_manifest))
    return {"dataset_id": str(ds.id), "row_count": ds.row_count,
            "imported_count": ds.imported_count, "failed_count": ds.failed_count}


@router.get("/datasets")
async def list_datasets(_=Depends(require_role("data_operator"))):
    items = await Dataset.find().sort(-Dataset.uploaded_at).to_list()
    return {"items": [d.model_dump(mode="json") for d in items]}


@router.get("/datasets/{dataset_id}")
async def get_dataset(dataset_id: str, _=Depends(get_current_user)):
    ds = await Dataset.get(dataset_id)
    if ds is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dataset not found")
    return ds.model_dump(mode="json")


@router.post("/datasets/{dataset_id}/validate")
async def validate_dataset_endpoint(dataset_id: str, _=Depends(require_role("data_operator"))):
    ds = await Dataset.get(dataset_id)
    if ds is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dataset not found")
    return await run_validation(dataset_id)      # default rule set

