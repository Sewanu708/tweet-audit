from google.api_core import retry
from google.genai import errors

def if_genai_transient_error(exception):
    return isinstance(exception, errors.APIError) and exception.code in {408, 429, 500, 502, 503, 504}


retried_times = 0

@retry.Retry(
    predicate=if_genai_transient_error,
    initial=2.0,
    maximum=64.0,
    multiplier=2.0,
    timeout=600,
)
def generate_content_first_fail(prompt):
    if not hasattr(generate_content_first_fail, "call_counter"):
        generate_content_first_fail.call_counter = 0

    generate_content_first_fail.call_counter += 1
    global retried_times
    retried_times+=1

    try:
        if generate_content_first_fail.call_counter < 9:
            raise errors.ServerError(
                503,
                {"error": {"code": 503, "message": "Service Unavailable", "status": "UNAVAILABLE"}},
                None,
            )

        response = {
            "text":"Thiss is lige"
        }
        return response
    except errors.ServerError as e:
        print(f"Error: {e}")
        raise


prompt = "Write a one-liner advertisement for magic backpack."

generate_content_first_fail(prompt=prompt)

assert retried_times == 2