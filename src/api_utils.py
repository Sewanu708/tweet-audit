import uuid
import os
import zipfile
import aiofiles
from pydantic import BaseModel, Field
from fastapi import UploadFile, HTTPException


async def upload_archive(file: UploadFile) -> tuple[str, str]:
    """
    Saves the uploaded file, validates it, and returns a job ID and file path.
    Supports .zip archives containing 'tweets.js' and raw .js files.
    """
    job_id = str(uuid.uuid4())
    upload_dir = os.path.join(os.getcwd(), "data", "uploads")
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
        file.file.seek(0) # Reset file pointer again after reading namelist

    elif not file.filename.endswith(".js"):
        raise HTTPException(status_code=400, detail="Unsupported file type. Please provide a .zip or .js file.")

    async with aiofiles.open(file_path, mode="wb") as f:
        while chunk := await file.read(1024 * 64): # Read in 64KB chunks
            await f.write(chunk)

    return job_id, file_path

criteria =  {
    "forbidden_words": ["crypto", "NFT", "hustlegrindset"],
    "professional_check": True,
    "tone": "respectful and thoughtful",
    "exclude_politics": True
}

system_prompt = """

    You are a tweet auditor. Your job is to evaluate tweets and decide whether they should be flagged for deletion.

Flag a tweet if it meets ANY of the following criteria:
- Is a retweet with no original thought added — starts with "RT @"
- Is vague, low-effort, or adds no value (e.g. "honestly just happy the CI passed")
You will receive a list of tweets. For each tweet, respond with a JSON array in this exact format:

[
  {
    "id_str": "the tweet id",
    "flagged": true,
    "reason": "one sentence explaining why"
  },
  {
    "id_str": "the tweet id",
    "flagged": false,
    "reason": null
  }
]

Rules:
- Return ONLY the JSON array. No preamble, no explanation, no markdown code fences.
- Every tweet in the input must have a corresponding entry in the output.
- Keep reasons concise — one sentence maximum.
"""


class GeminiOutput(BaseModel):
    id_str: str = Field(description="Unique id of the tweet")
    flagged: bool = Field(description="Whether the tweet should be flagged")
    reason: str | None = Field(
        default=None,
        description="Reason for flagging, null if not flagged"
    )
