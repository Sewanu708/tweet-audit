import json
import csv
import asyncio
from logger import logger
from relegated.gemini_client import client, gemini_client
from sqlmodel import Session, select
from db_config import engine, Idemptency, Tweets, Jobs, Status
import uuid

rate_limit_lock = asyncio.Semaphore(3)


async def gemini_client_mock(batch, c):
    # temporary mock
    return [
        {"id_str": tweet["tweet"]["id_str"], "flagged": False, "reason": None}
        for tweet in batch
    ]


async def gemini_client_lock(data):
    async with rate_limit_lock:
        logger.info(f"Sending batch of {len(data)} tweets to Gemini")
        resp = await gemini_client(data, client)
        logger.info(f"Received response for {len(resp)} tweets, sleeping to respect rate limit")
        await asyncio.sleep(15)
        return resp


def save_csv(data):
    with open("tweets.csv", mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f=f, fieldnames=["id_str", "flagged", "reason"])
        writer.writeheader()
        writer.writerows(data)
    logger.info(f"CSV saved with {len(data)} records")



async def work(content: str, job_id:str, prefix_to_strip: str | None = None, ):
    async with redis.Redis(host='localhost', port=6379, decode_responses=True) as job_r:
        if prefix_to_strip:
            logger.info(f"Stripping prefix: '{prefix_to_strip}'")
            content = content.replace(prefix_to_strip, "")

        if not content.startswith("[") and " = " in content:
            content = content[content.index(" = ") + 3:]

        try:
            output: list = json.loads(content)
            logger.info(f"Loaded {len(output)} records successfully")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            raise ValueError(f"Error parsing file: {e}")

        grouped_batches = []
        for i in range(0, len(output), 1000):
            grouped_batches.append(output[i:i+1000])

        logger.info(f"Processing {len(output)} tweets across {len(grouped_batches)} batches")

        for batch_index, batch in enumerate(grouped_batches):
            final_response = []
            logger.info(f"Processing batch {batch_index + 1}/{len(grouped_batches)}")
            ids = [tweet['tweet']["id_str"] for tweet in batch]

            to_be_processed = []
            with Session(engine) as session:
                statement = select(Idemptency).where(Idemptency.tweet_id.in_(ids))
                result = session.exec(statement).all()
                saved_ids = {tweet.tweet_id: tweet for tweet in result}

                for tweet_id in ids:
                    if tweet_id in saved_ids:
                        final_response.append(saved_ids[tweet_id].response)
                    else:
                        to_be_processed.append(tweet_id)

            logger.info(f"Batch {batch_index + 1}: {len(saved_ids)} already processed, {len(to_be_processed)} to send to Gemini")

            to_be_processed_set = set(to_be_processed)
            main_p = [tweet for tweet in batch if tweet["tweet"]['id_str'] in to_be_processed_set]

            gem_group_batches = []
            for i in range(0, len(main_p), 100):
                gem_group_batches.append(main_p[i:i+100])

            if not gem_group_batches:
                logger.info(f"Batch {batch_index + 1}: nothing new to process, skipping Gemini")
                await job_r.publish(job_id, json.dumps(final_response))
                continue

            logger.info(f"Batch {batch_index + 1}: sending {len(gem_group_batches)} sub-batches to Gemini concurrently")
            final_output = await asyncio.gather(
                *[gemini_client_lock(i) for i in gem_group_batches]
            )

            to_save = []
            flagged_count = 0
            for gem_output in final_output:
                final_response.extend(gem_output)
                for gem_data in gem_output:
                    if gem_data['flagged']:
                        flagged_count += 1
                    to_save.append(Idemptency(tweet_id=gem_data['id_str'], response=gem_data))

            with Session(engine) as session:
                session.add_all(to_save)
                session.commit()

            logger.info(f"Batch {batch_index + 1}: saved {len(to_save)} results, {flagged_count} flagged")
            await job_r.publish(job_id, json.dumps(final_response))

        logger.info("Audit complete")
        await job_r.publish(job_id, "done")

