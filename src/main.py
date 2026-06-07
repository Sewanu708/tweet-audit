from db_config import Idemptency, engine
from gemini_client import gemini_client
from sqlmodel import select, Session
import math
from loader import fetch_data
import csv
import asyncio
import json


rate_limit_lock = asyncio.Semaphore(3) 

async def gemini_client_mock(batch):
    # temporary mock
    return [
        {"id_str": tweet["tweet"]["id_str"], "flagged": False, "reason": None}
        for tweet in batch
    ]

async def gemini_client_lock(data):
    async with rate_limit_lock:

        resp = await gemini_client_mock(data)
        asyncio.sleep(15)
        return resp

def save_csv(data):
    with open("tweets.csv", mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f=f, fieldnames=["id_str", "flagged","reason"])
        writer.writeheader()
        writer.writerows(data)


async def work():
    path = input("Enter your file path: ")
    prefix_to_remove = input("Enter any prefix to strip: ")
    output:list = fetch_data(path, prefix_to_strip=prefix_to_remove)
   
    grouped_batches = []

    for i in range(0, len(output), 100):
        grouped_batches.append(output[i:i+100])

    final_response = []
    for batch in grouped_batches:
        ids = [tweet['tweet']["id_str"] for tweet in batch]
       
        to_be_processed=[]
        main_p = []
        with Session(engine) as session:
            statement = select(Idemptency).where(
                Idemptency.tweet_id.in_(ids)
            )
            result = session.exec(statement).all()
            saved_ids = {tweet.tweet_id for tweet in result}
            
            for tweet_id in ids:
                if tweet_id in saved_ids:
                    for tweet in result:
                        if tweet.tweet_id == tweet_id:
                            final_response.append(tweet.response)
                else:
                    to_be_processed.append(tweet_id)
           
            to_be_processed_set = set(to_be_processed)

            main_p = [tweet for tweet in batch if  tweet["tweet"]['id_str'] in to_be_processed_set]

            gem_rounds = math.ceil(len(main_p)/25)
            gem_group_batches = []
            for i  in range(0, len(main_p), 25):
                gem_group_batches.append(main_p[i:i+25])

            print(len(gem_group_batches))

        final_output =  await asyncio.gather(
          *[ gemini_client_lock(i) for i in gem_group_batches
            ]
        )

        
        to_save=[]
        print(final_output)
        for output in final_output:
            print("=========================================================================================================================")
            try:
                output = json.loads(output)
            except TypeError:
                pass
            print((output))
            final_response.extend((output))
            # return
            for gem_data in output:
                print(gem_data)
                to_save.append(Idemptency(tweet_id=gem_data['id_str'], response=gem_data))
            
        with Session(engine) as session:
            session.add_all(to_save)
            session.commit()
        
    
    save_csv(final_response)
    print("Done")





if __name__ == "__main__":
    # with Session(engine) as session:
    #     statement = select(Idemptency)
    #     result = session.exec(statement).all()
    #     print(result)

    asyncio.run(work())