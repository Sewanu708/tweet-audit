from google import genai
from settings import env
import asyncio
from google.api_core import retry_async
from google.genai import errors
from pydantic import BaseModel, Field
from typing import List, Optional
import json

system_prompt = """

    You are a tweet auditor. Your job is to evaluate tweets and decide whether they should be flagged for deletion.

Flag a tweet if it meets ANY of the following criteria:
- Complains about a specific tool, language, or technology in a way that sounds bitter or unprofessional (e.g. "I hate CSS", "MySQL is trash")
- Expresses frustration or negativity about work, colleagues, or the industry in a way that could embarrass a professional
- Is a retweet with no original thought added — starts with "RT @"
- Makes a hot take or controversial claim that could age poorly or be taken out of context
- Is vague, low-effort, or adds no value (e.g. "honestly just happy the CI passed")

Do NOT flag a tweet if it:
- Shares a genuine insight, lesson learned, or technical observation
- Is positive, neutral, or constructive in tone
- Celebrates a milestone or achievement professionally

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
- Preserve the order of tweets as given.

"""


class GeminiOutput(BaseModel):
    id_str: str = Field(description="Unique id of the tweet")
    flagged: bool = Field(description="Whether the tweet should be flagged")
    reason: str | None = Field(
        default=None,
        description="Reason for flagging, null if not flagged"
    )

client = genai.Client(api_key=env['GEMINI_API_KEY'])

def if_genai_transient_error(exception):
    return isinstance(exception, errors.APIError) and exception.code in {408, 429, 500, 502, 503, 504}

@retry_async.AsyncRetry(
    predicate=if_genai_transient_error,
    initial=2.0,
    maximum=64.0,
    multiplier=2.0,
    timeout=600,
)
async def gemini_client(data:dict)->List[GeminiOutput]:
        response = await client.aio.models.generate_content(
        model="gemini-2.5-flash" ,
        contents=f"Audit these tweets:\n{json.dumps(data)}",
        config=genai.types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_json_schema={
                "type":"array",
                "schema":GeminiOutput.model_json_schema()
            }
            )
        )

        return response.text
    
