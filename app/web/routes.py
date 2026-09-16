from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/ui", include_in_schema=False)
def ui():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@router.get("/ui/static/{asset_path:path}", include_in_schema=False)
def ui_asset(asset_path: str):
    root = (Path(__file__).parent / "static").resolve()
    file = (root / asset_path).resolve()
    if root not in file.parents or not file.is_file():
        raise HTTPException(404, "UI asset not found")
    return FileResponse(file)
