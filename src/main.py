import uvicorn
from fastapi import FastAPI, UploadFile, Depends
from fastapi.middleware.cors import CORSMiddleware
from .celery_worker import parse_analyze_path
from sqlmodel import Session, select
from .db_config import engine, get_db, Tweets, Jobs, TweetStatus
from .api_utils import upload_archive
import uuid
from fastapi import HTTPException

app = FastAPI(title="Tweets Audit API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/upload")
async def upload_data(file: UploadFile, db: Session = Depends(get_db),):
    job_id, file_path = await upload_archive(file)
    job_id_uuid = uuid.UUID(job_id)
    
    new_job = Jobs(id=job_id_uuid)
    db.add(new_job)
    db.commit()

    parse_analyze_path.delay(job_id=job_id, file_path=file_path)
    return {"status": "queued", "task_id": job_id}


@app.get("/{job_id}/processed")
def stream_job(job_id:str):
    job_id_uuid = uuid.UUID(job_id)
    with Session(engine) as session:
        job = session.get(Jobs, job_id_uuid)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job with ID {job_id} not found.")

        tweets = session.exec(select(Tweets).where(Tweets.job_id == job_id_uuid, Tweets.status != TweetStatus.pending_llm )).all()
        
        results = [
            {"id_str": t.tweet_id, "flagged": t.flagged, "reason": t.reason}
            for t in tweets
        ]
        return {"status": job.status.value, "results": tweets}

if __name__ == "__main__":
    uvicorn.run("src.main:app", host='0.0.0.0', port=8001, reload=True, reload_dirs=["src"])