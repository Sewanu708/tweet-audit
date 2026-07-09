import uuid
import os
import zipfile
import aiofiles
from fastapi import UploadFile, HTTPException


async def upload_archive(file: UploadFile) -> tuple[str, str]:
    """
    Saves the uploaded file, validates it, and returns a job ID and file path.
    Supports .zip archives containing 'tweets.js' and raw .js files.
    """
    job_id = str(uuid.uuid4())
    # NOTE: Ensure the '/data/uploads' directory exists in your environment.
    upload_dir = "/data/uploads" 
    os.makedirs(upload_dir, exist_ok=True)
    
    filename = f"{job_id}-{file.filename}"
    file_path = os.path.join(upload_dir, filename)

    if file.content_type == "application/zip" or file.filename.endswith(".zip"):
        if not zipfile.is_zipfile(file.file):
            raise HTTPException(status_code=400, detail="Corrupted or invalid ZIP file.")
        file.file.seek(0)
        z_file = zipfile.ZipFile(file.file)
        if not any(name.endswith("data/tweets.js") or name == "tweets.js" for name in z_file.namelist()):
            raise HTTPException(status_code=400, detail="Missing 'tweets.js' or 'data/tweets.js' in the ZIP archive.")

    elif not file.filename.endswith(".js"):
        raise HTTPException(status_code=400, detail="Unsupported file type. Please provide a .zip or .js file.")

    async with aiofiles.open(file_path, mode="wb") as f:
        while chunk := await file.read(1024 * 64): # Read in 64KB chunks
            await f.write(chunk)

    return job_id, file_path