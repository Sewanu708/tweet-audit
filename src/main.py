import uvicorn
from fastapi import FastAPI, UploadFile, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from .celery_worker import parse_analyze_path
from sqlmodel import Session, select, engine
from .db_config import get_db, Tweets, Jobs, TweetStatus
from .api_utils import upload_archive
import json
import uuid
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List
import csv
import io


class AuditCriteria(BaseModel):
    forbidden_words: List[str]
    professional_check: bool
    tone: str
    exclude_politics: bool


app = FastAPI(title="Tweets Audit API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/upload")
async def upload_data(file: UploadFile, db: Session = Depends(get_db), criteria:str=Form(None)):
    validated_criteria = {}
    if criteria is not None:  
        try: 
            body = json.loads(criteria)
            validated_body = AuditCriteria(**body)
            validated_criteria = validated_body.model_dump()
        except Exception as e:
            raise HTTPException(status_code=409, detail=f"Error parsing criteria: {str(e)}")

    job_id, file_path = await upload_archive(file)
    job_id_uuid = uuid.UUID(job_id)
    
    new_job = Jobs(id=job_id_uuid, criteria=validated_criteria)
    db.add(new_job)
    db.commit()

    parse_analyze_path.delay(job_id=job_id, file_path=file_path)
    return {"status": "queued", "task_id": job_id}


@app.get("/{job_id}/status")
def stream_job(job_id:str, db: Session = Depends(get_db)):
    job_id_uuid = uuid.UUID(job_id)
    job = db.get(Jobs, job_id_uuid)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID {job_id} not found.")
    return job
        

@app.get("/{job_id}/tweets")
def job_tweets(job_id: str, status: TweetStatus = None, db: Session = Depends(get_db)):
    job_id_uuid = uuid.UUID(job_id)
    job = db.get(Jobs, job_id_uuid)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID {job_id} not found.")

    conditions = [Tweets.job_id == job_id_uuid]
    if status is None:
        conditions.append(Tweets.status != TweetStatus.pending_llm)
    else:
        conditions.append(Tweets.status == status)

    tweets = db.exec(select(Tweets).where(*conditions)).all()

    return {"status": job.status.value, "results": tweets}


@app.get("/{job_id}/download")
def download_tweets(
    job_id: str,
    flagged_only: bool = False,
    db: Session = Depends(get_db)
):
    job_id_uuid = uuid.UUID(job_id)
    job = db.get(Jobs, job_id_uuid)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID {job_id} not found.")

    conditions = [Tweets.job_id == job_id_uuid]
    if flagged_only:
        conditions.append(Tweets.flagged == True)
    else:
        conditions.append(Tweets.status != TweetStatus.pending_llm)

    filename = f"tweet_audit_{job_id}.csv"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }
    return StreamingResponse(
        stream_csv(job_id_uuid, flagged_only),
        media_type="text/csv",
        headers=headers
    )


def stream_csv(job_id_uuid: uuid.UUID, flagged_only: bool):
    output = io.StringIO()
    writer = csv.writer(output)

    header = ['id_str', 'flagged', 'reason']
    writer.writerow(header)
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    with Session(engine) as db:
        conditions = [Tweets.job_id == job_id_uuid]
        if flagged_only:
            conditions.append(Tweets.flagged == True)
        else:
            conditions.append(Tweets.status != TweetStatus.pending_llm)
        tweets = db.exec(select(Tweets).where(*conditions)).all()
        for tweet in tweets:
            writer.writerow([
                tweet.tweet_id,
                "TRUE" if tweet.flagged else "FALSE",
                tweet.reason or ""
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

if __name__ == "__main__":
    uvicorn.run("src.main:app", host='0.0.0.0', port=8001, reload=True, reload_dirs=["src"])