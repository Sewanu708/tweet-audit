import uvicorn
from fastapi import FastAPI, UploadFile, Depends
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from analyze import stream_job
from logger import logger
from celery_worker import parse_analyze_path
from sqlmodel import Session
from db_config import get_db, Jobs
from api_utils import upload_archive

# The resilience patterns (RateLimiter, CircuitBreaker, etc.) and the agent logic
# have been moved to resilience.py and agent.py respectively.
# They are not directly used in this file anymore but are fundamental for the worker tasks.

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
    
    # Create and save the initial job record
    new_job = Jobs(id=job_id)
    db.add(new_job)
    db.commit()

    # Delegate the heavy lifting to a background task
    parse_analyze_path.delay(job_id=str(job_id), file_path=file_path)
    return {"status": "queued", "task_id": job_id}


@app.get("/{job_id}/stream")
async def stream_csv(job_id: str):
    return StreamingResponse(
        content=stream_job(job_id),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="tweet_analysis.csv"'})

if __name__ == "__main__":
    uvicorn.run("main:app", host='0.0.0.0', port=8001, reload=True)