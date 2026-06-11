Architecture: Loader → Idempotency Check → Gemini Client → CSV Writer


![Architecture Diagram](./architecture.png)


### Why this architecture?

#### Duplicate Calls

This architecture, with the idempotency layer, prevents duplicate calls to the Gemini client. Every call to Gemini matters because tokens are consumed. As such, repeating calls can be expensive. This architecture eliminates that possibility.

#### Proper Batching and Asynchronous Tasks

Gemini is very strict about context length. As such, we avoid overloading it with large amounts of data.

With this architecture, a proper batching system was implemented, with each Gemini client call processing a batch of 100 tweets as payload (spread across 3 clients within a semaphore lock).

To make the process faster while taking the Gemini rate limiter into account, I ensured that calls to the Gemini client were concurrent, since this is an I/O-bound task. I opted for a fully asynchronous pattern, with coroutine functions handling the workload, ensuring proper resource utilization while still running on a single thread.

To avoid overwhelming the Gemini client with too many requests, a semaphore lock was used to ensure that only 3 requests could be made within a one-minute window. Coupled with the lock was a 15-second buffer to allow sufficient time for rate limits to reset on the Gemini side.

**Concurrency Strategy:** Batching + Full Async

Going with a sequential approach would only slow things down. As such, I opted for a proper batching system (to avoid overloading Gemini) combined with a fully asynchronous execution pattern.

**Why?**

* Batching reduces the payload sent to Gemini per request, ensuring that each request remains within the model's context limits and preventing unnecessary overload.
* The async pattern allows us to fully utilize available resources while waiting for responses from Gemini.

#### DB Type

I chose SQLite because it is file-based. The reason for this is that the project's output is also a file. Additionally, SQLite is lightweight and very easy to set up.

#### Error Handling

A proper retry mechanism with exponential backoff was implemented for retryable and transient errors. Other errors were properly logged for the client.

Other failure scenarios, such as server crashes or file-not-found errors, were also handled appropriately. For instance, the idempotency layer makes the system safe to retry after a server crash because the client can be assured that duplicate Gemini calls will not be made, which could otherwise become very costly.

### Performance vs Safety Trade-offs

The semaphore lock was the main performance-versus-safety trade-off decision I had to make.

From a performance perspective, requests could potentially be completed within a few minutes or even seconds. However, I needed to ensure that we did not exceed Gemini's context limits or violate its rate limits. Failing to do so could result in excessive token consumption and unnecessary costs.

### Why I Chose This Language

#### Python

Although Python has its limitations, particularly around asynchronous execution and multithreading, our approach operates primarily on a single thread, meaning the GIL does not significantly impact performance in this use case.

Additionally, Python is well-suited for this type of project because of its strong ecosystem, rapid development speed, and excellent support for asynchronous I/O workloads.
