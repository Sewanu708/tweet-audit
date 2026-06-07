from db_config import Idemptency, engine
from gemini_client import gemini_client, config_gemini_client
from sqlmodel import select, Session
from loader import fetch_data
from logger import logger
import csv
import asyncio
import getpass


rate_limit_lock = asyncio.Semaphore(3) 

async def gemini_client_mock(batch, client):
    # temporary mock
    return [
        {"id_str": tweet["tweet"]["id_str"], "flagged": False, "reason": None}
        for tweet in batch
    ]

async def gemini_client_lock(data, client):
    async with rate_limit_lock:
        logger.info(f"Sending batch of {len(data)} tweets to Gemini")
        resp = await gemini_client_mock(data, client)
        logger.info(f"Received response for {len(resp)} tweets, sleeping to respect rate limit")
        await asyncio.sleep(15)
        return resp

def save_csv(data):
    with open("tweets.csv", mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f=f, fieldnames=["id_str", "flagged", "reason"])
        writer.writeheader()
        writer.writerows(data)
    logger.info(f"CSV saved with {len(data)} records")


async def work():
    path = input("Enter your file path: ")
    prefix_to_remove = input("Enter any prefix to strip: ")
    gemini_api_key = getpass.getpass("Enter your Gemini API key: ")

    output: list = fetch_data(path, prefix_to_strip=prefix_to_remove)
    client = config_gemini_client(gemini_api_key)

    grouped_batches = []
    for i in range(0, len(output), 100):
        grouped_batches.append(output[i:i+100])

    logger.info(f"Processing {len(output)} tweets across {len(grouped_batches)} batches")

    final_response = []
    for batch_index, batch in enumerate(grouped_batches):
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
        for i in range(0, len(main_p), 25):
            gem_group_batches.append(main_p[i:i+25])

        if not gem_group_batches:
            logger.info(f"Batch {batch_index + 1}: nothing new to process, skipping Gemini")
            continue

        logger.info(f"Batch {batch_index + 1}: sending {len(gem_group_batches)} sub-batches to Gemini concurrently")
        final_output = await asyncio.gather(
            *[gemini_client_lock(i, client) for i in gem_group_batches]
        )

        to_save = []
        flagged_count = 0
        for output in final_output:
            final_response.extend(output)
            for gem_data in output:
                if gem_data['flagged']:
                    flagged_count += 1
                to_save.append(Idemptency(tweet_id=gem_data['id_str'], response=gem_data))

        with Session(engine) as session:
            session.add_all(to_save)
            session.commit()

        logger.info(f"Batch {batch_index + 1}: saved {len(to_save)} results, {flagged_count} flagged")

    save_csv(final_response)
    logger.info("Audit complete")


if __name__ == "__main__":
    asyncio.run(work())