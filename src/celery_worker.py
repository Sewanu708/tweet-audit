import redis
import json
from threading import Lock
from celery import Celery, shared_task
from .db_config import engine, Jobs, Tweets, Status, TweetStatus
from sqlmodel import select, Session, SQLModel
from .loader import load_data_from_content
from .logger import logger
from .agent import AgentDownStream
from .resilience import RateLimiter, CircuitBreaker, TokenBucket, DailyTokenBucket
from .api_utils import system_prompt, GeminiOutput
from .settings import env
import uuid

celery_client = Celery(
    "tasks",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0"
)

sync_r = redis.Redis(host='localhost', port=6379, decode_responses=True)

filter_words = ['tech','technology','blockchain']


def rt_filter(text:str):
    return True if "RT" in text else False

def contains_filter(text):
    for element in filter_words:
        if element in text:
            return True
    
    return False


@shared_task()
def agent_review(job_id:str):
    """Celery task to review tweets using a resilient agent to call the Gemini API."""
    job_id_uuid = uuid.UUID(job_id)
    rpm_bucket = TokenBucket(max_tokens=3, refill_rate=1, interval=60, lock=Lock)
    # Daily limit: 10,000 requests per day
    rpd_bucket = DailyTokenBucket(max_tokens=10000, lock=Lock)
    rate_limiter = RateLimiter(rpm_bucket=rpm_bucket, rpd_bucket=rpd_bucket)
    
    # Circuit breaker: Opens after 5 failures, waits 60s before retrying
    breaker = CircuitBreaker(failure_threshold=5, reset_timeout=60)

    ai_agent = AgentDownStream(
        rate_limiter=rate_limiter,
        breaker=breaker,
        api_key=env["gemini_api_key"]
    )
    
    gemini_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

    with Session(engine) as db:
        pending_tweets = db.exec(
            select(Tweets).where(Tweets.job_id == job_id_uuid, Tweets.status == TweetStatus.pending_llm)
        ).all()
    
        if not pending_tweets:
            logger.info(f"Job {job_id}: No more tweets to process with AI. Marking job as complete.")
            job = db.get(Jobs, job_id_uuid)
            if job and job.status != Status.completed:
                job.status = Status.completed
                db.add(job)
                db.commit()
            return
    
        logger.info(f"Job {job_id}: Found {len(pending_tweets)} tweets to review with Gemini.")
        
        gemini_batches = []
        for i in range(0, len(pending_tweets), 100):
            gemini_batches.append(pending_tweets[i:i+100])

        for i, batch in enumerate(gemini_batches):
            logger.info(f"Job {job_id}: Processing Gemini batch {i+1}/{len(gemini_batches)}")
            
            # Prepare payload for Gemini API
            tweet_contents = [{"id_str": t.tweet_id, "full_text": t.content} for t in batch]
            payload = {
                "contents": [{"parts": [{"text": f"{system_prompt}\nAudit these tweets:\n{json.dumps(tweet_contents)}"}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": {"type": "array", "items": GeminiOutput.model_json_schema()}
                }
            }

            try:
                response = ai_agent.call(url=gemini_url, payload=payload)
                logger.info(response)
                if not response.success:
                    raise ValueError(f"API call failed with response code {response.response_code}: {response.err_message}")
                results = response.data['candidates'][0]['content']['parts'][0]['text']
                gemini_responses = json.loads(results)

                # Efficiently map tweets in the batch by their ID for quick updates
                batch_tweets_map = {t.tweet_id: t for t in batch}

                for res in gemini_responses:
                    tweet_to_update = batch_tweets_map.get(res['id_str'])
                    if tweet_to_update:
                        tweet_to_update.flagged = res['flagged']
                        tweet_to_update.reason = res['reason']
                        tweet_to_update.status = TweetStatus.flagged_llm if res['flagged'] else TweetStatus.safe
                        db.add(tweet_to_update)
                
                db.commit()
                logger.info(f"Job {job_id}: Successfully processed and saved Gemini batch {i+1}.")

            except Exception as e:
                logger.error(f"Job {job_id}: Failed to process Gemini batch {i+1}. Error: {e}", exc_info=True)
                # Optionally, you could add logic here to mark the job as failed.




@shared_task()
def parse_analyze_path(job_id: str, file_path: str):
    job_id_uuid = uuid.UUID(job_id)
    try:
        tweets_data = load_data_from_content(file_path)

        with Session(engine) as db:
            
            tweets_to_create = []
            flag_counter = 0
            for tweet_dict in tweets_data:
                tweet_content = tweet_dict['tweet']['full_text']
                tweet_id_str = tweet_dict['tweet']['id_str']
                is_retweet = rt_filter(tweet_content)

                flagged = contains_filter(tweet_content)
                if (flagged):
                    flag_counter +=1
                tweets_to_create.append(Tweets(
                    tweet_id=tweet_id_str,
                    job_id=job_id_uuid,
                    flagged=flagged,
                    is_retweet=is_retweet,
                    content=tweet_content,
                    status=TweetStatus.flagged_filter if flagged else TweetStatus.pending_llm
                ))
            
            db.add_all(tweets_to_create)
            db.commit()
            logger.info(f"Job {job_id}: Saved {len(tweets_to_create)} raw tweets to DB.")

            job = db.exec(select(Jobs).where(Jobs.id == job_id_uuid)).first()
            if not job:
                logger.error(f"Job {job_id} not found in DB.")
                return

            job.total = len(tweets_data)
            job.status = Status.processing
            job.processed_count = flag_counter
            job.flagged_count = flag_counter
            db.add(job)
            db.commit()
            db.refresh(job)

        agent_review.delay(job_id)
    except Exception as e:
        logger.error(f"Job {job_id} failed during parsing or initial DB save: {e}", exc_info=True)
        with Session(engine) as db:
            job = db.exec(select(Jobs).where(Jobs.id == job_id_uuid)).first()
            if job:
                job.status = Status.failed
                job.error = str(e)
                db.add(job)
                db.commit()
                db.refresh(job)
        raise
