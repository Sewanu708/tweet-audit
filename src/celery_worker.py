import redis
import json
from celery import Celery, shared_task, signals
from .db_config import engine, Jobs, Tweets, Status, TweetStatus
from sqlmodel import select, Session
from .loader import load_data_from_content
import time
from .logger import logger
import threading
from .agent import AgentDownStream
from .resilience import RateLimiter, CircuitBreaker, TokenBucket, DailyTokenBucket
from .api_utils import system_prompt, GeminiOutput, criteria
from .settings import env
import asyncio
from .redis_client import redis_cnn
import uuid

rpm_key = "rpm_bucket"
rpd_key = "rpd_bucket"
breaker_key = "circuit_breaker"
redis_host=env.get('redis_host', 'localhost')
redis_port=env.get('redis_port', 6379)

celery_client = Celery(
    "tasks",
    broker=f"redis://{redis_host}:{redis_port}/0",
    backend=f"redis://{redis_host}:{redis_port}/0"
)

filter_words = criteria.get("forbidden_words",[])

def rt_filter(text:str):
    return True if "RT" in text else False



@signals.worker_ready.connect
def requeue_failed_jobs(sender, **kwargs):
    with Session(engine) as db:
        pending_jobs = db.exec(
            select(Jobs).where(Jobs.status != Status.completed, Jobs.status != Status.processing, (time.time() - Jobs.updated_at )>= 300)
        ).all()

        if not pending_jobs:
            return

        for job in pending_jobs:
            asyncio.run(agent_review_coroutine(str(job.id)))


@shared_task()
def agent_review(job_id:str):
    asyncio.run(agent_review_coroutine(job_id))

async def agent_review_coroutine(job_id:str):
    lock = threading.Lock
    job_id_uuid = uuid.UUID(job_id)
    rpm_bucket = TokenBucket(max_tokens=3, refill_rate=1, interval=60, lock=lock, redis_client=redis_cnn, key=rpm_key)
    rpd_bucket = DailyTokenBucket(max_tokens=10000, lock=lock, redis_client=redis_cnn, key=rpd_key)
    rate_limiter = RateLimiter(rpm_bucket=rpm_bucket, rpd_bucket=rpd_bucket)
    
    breaker = CircuitBreaker(failure_threshold=5, reset_timeout=60, key=breaker_key,redis_client=redis_cnn)

    # Fetch job-specific criteria
    with Session(engine) as db:
        job = db.get(Jobs, job_id_uuid)
        if not job:
            logger.error(f"Job {job_id} not found in DB for agent review.")
            return
        
        job_criteria = job.criteria if job.criteria else criteria
        dynamic_system_prompt = build_system_prompt(job_criteria)


    ai_agent = AgentDownStream(
        rate_limiter=rate_limiter,
        breaker=breaker,
        api_key=env["gemini_api_key"]
    )
    

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

        for idx in range(0,len(gemini_batches),3):
            try:
                payloads = []
                batch_tweets_map = {}
                formatted_batches = []
                for batches in gemini_batches[idx:idx+3]:
                    batch_tweet_formatted = []
                    for tweet_ls in batches:
                        batch_tweets_map[tweet_ls.tweet_id] = tweet_ls
                        batch_tweet_formatted.append({"id_str": tweet_ls.tweet_id, "full_text": tweet_ls.content})
                    formatted_batches.append(batch_tweet_formatted)
                payloads = [ prep_payload(b, dynamic_system_prompt) for b in formatted_batches]
                resp = await batch_call(ai_agent,payloads)

                for response in resp:
                    if isinstance(response, Exception):
                        raise response
                    if not response.success:
                        raise ValueError(f"API call failed with response code {response.response_code}: {response.err_message}")
                    results = response.data['candidates'][0]['content']['parts'][0]['text']
                    gemini_responses = json.loads(results)
                    processed_count = 0
                    flagged_count = 0
                    for res in gemini_responses:
                        tweet_to_update = batch_tweets_map.get(res['id_str'])
                        if tweet_to_update:
                            
                            tweet_to_update.flagged = res['flagged']
                            tweet_to_update.reason = res['reason']
                            tweet_to_update.status = TweetStatus.flagged_llm if res['flagged'] else TweetStatus.safe
                            db.add(tweet_to_update)
                            processed_count +=1
                            if res['flagged']:
                                flagged_count +=1
                    
                    job = db.get(Jobs, job_id_uuid)
                    if job:
                        job.processed_count+=processed_count
                        job.flagged_count += flagged_count
                        db.add(job)
                    db.commit()

                    logger.info(f"Job {job_id}: Successfully processed and saved Gemini batch {idx // 3 + 1}.")

            except Exception as e:
                logger.error(f"Job {job_id}: Failed to process Gemini batch {i+1}. Error: {e}", exc_info=True)
                db.rollback() 
                job = db.get(Jobs, job_id_uuid)
                if job and job.status != Status.completed:
                    job.status = Status.failed
                    job.error = f" Error: {e}"
                    db.add(job)
                    db.commit()
                return
    

        job = db.get(Jobs, job_id_uuid)
        if job and job.status != Status.completed:
            job.status = Status.completed
            db.add(job)
            db.commit()


                


def build_system_prompt(crit: dict) -> str:
    base_prompt = system_prompt
    
    crit_instructions = "\nAdditionally, pay close attention to the following job-specific criteria:"
    if crit.get("professional_check"):
        crit_instructions += "\n- Ensure tweets maintain a professional tone."
    if crit.get("exclude_politics"):
        crit_instructions += "\n- Flag any tweets that are political in nature."
    
    return base_prompt + crit_instructions

def prep_payload(tweet_contents, dynamic_prompt: str):
    payload = {
                "contents": [{"parts": [{"text": f"{dynamic_prompt}\nAudit these tweets:\n{json.dumps(tweet_contents)}"}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": {"type": "array", "items": GeminiOutput.model_json_schema()}
                }
            }
    return payload



async def batch_call(ai_agent:AgentDownStream, batch:list) ->list :
    
    semaphore = asyncio.Semaphore(3)
    
    async def call(tweet):
        async with  semaphore:
            response = await ai_agent.call(url=env['gemini_url'], payload=tweet)
            return response
        
    tasks = [ asyncio.create_task(call(tweet)) for tweet in batch]

    return await asyncio.gather(*tasks,return_exceptions=True)

@shared_task()
def parse_analyze_path(job_id: str, file_path: str):
    job_id_uuid = uuid.UUID(job_id)
    try:
        tweets_data = load_data_from_content(file_path)

        with Session(engine) as db:
            job = db.exec(select(Jobs).where(Jobs.id == job_id_uuid)).first()
            if not job:
                logger.error(f"Job {job_id} not found in DB.")
                return
            criteria = job.criteria if job.criteria else {}
            forbidden_words = criteria.get("forbidden_words",filter_words)
            
            def contains_filter(text):
                for element in forbidden_words:
                    if element in text:
                        return True
                
                return False
            
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
