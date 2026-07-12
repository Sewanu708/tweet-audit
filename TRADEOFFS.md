## Architecture Choices

This system serves as a miniature version of what a large-scale file processing and audit system might look like architecturally.

### Core Components
*   **FastAPI Server**: A single-threaded server that handles incoming requests. Its primary role is to offload heavy tasks, keeping the event loop free to respond to other requests instantly.
*   **Celery Worker**: Handles all heavy background operations, including file parsing and AI-based analysis.
*   **Local Disk Storage**: For this miniature version, uploaded files are saved directly to disk. In a production system, this would be an object store (like S3) to decouple storage from the application. The server would only receive a file ID.

### Worker Responsibilities
1.  **Parsing & Filtering Worker**:
    *   Fetches the uploaded file, parses its content, and performs an initial analysis.
    *   Uses simple regex checks based on job criteria to flag tweets.
    *   Flagged tweets are excluded from AI analysis to reduce cost and processing time.
2.  **AI Agent Worker**:
    *   Receives unflagged tweets that require deeper analysis.
    *   Calls the external AI agent (Gemini) to perform the audit.
    *   Updates the status of each tweet and the overall job in the database.

### Database and Schema
*   **Database**: A simple in-memory SQLite database is used for speed and simplicity, suitable for this project's scale.
*   **Schema**:
    *   **Jobs Table**: Tracks the overall status of each upload and analysis job (e.g., `processing`, `completed`, `failed`).
    *   **Tweets Table**: Stores individual tweet content, its flag status, and its processing status (e.g., `pending_llm`, `safe`, `flagged_llm`). This provides a clear audit trail for each tweet.

---

## Concurrency Strategy

The system uses a **fully asynchronous, batch-processing** model. This approach trades some simplicity for significant gains in speed and cost-effectiveness.

*   **Async Batching**: Tweets are grouped into batches before being sent to the AI.
*   **Semaphore Lock**: A semaphore is used to make concurrent calls to the AI API, which dramatically speeds up the analysis of a batch.

---

## Error Handling and Resilience

Given the multiple components (workers, database, downstream AI), a robust error-handling strategy is crucial.

*   **Startup Sweeper**: On worker startup, a "sweeper" function queries the database for jobs or tweets that were stuck in a processing state (e.g., due to a crash). It re-queues them for AI review, ensuring no data is lost.
*   **Rate Limiting**: The `AgentDownStream` service implements rate limiters for both requests-per-minute and requests-per-day to avoid hitting the AI provider's limits.
*   **Circuit Breaker**: This pattern prevents the system from repeatedly calling the AI agent if it's down or returning errors. It "opens" the circuit after a threshold of failures and only allows periodic retries, preventing cascading failures.
*   **Intelligent Retries**: A decorator on the HTTP call to the AI agent manages retries. It intelligently handles different error types:
    *   **Transient Errors**: Retries after a given backoff time automatically.
    *   **Deterministic Errors**: Fails fast without retrying.
*   **Persistent State**: The state of the circuit breaker and rate limiters is persisted in Redis. This ensures that even if a worker restarts, it won't immediately overwhelm the downstream API.

---

## Performance vs. Safety Trade-offs

### Performance Optimizations
*   **Task Offloading**: All heavy lifting is relegated to background Celery workers, keeping the API responsive.
*   **Early Filtering**: A simple, fast validation layer flags many tweets without needing the expensive AI agent.
*   **Concurrent API Calls**: A semaphore allows for parallel processing of tweets within a batch, maximizing throughput.

### Safety Measures
*   **Resilience Layer**: The combination of rate limiters, circuit breakers, and intelligent retries makes the system robust, even if it adds a small amount of overhead.
*   **Concurrency Bottleneck**: While the semaphore speeds things up, it also means that if one API call in a batch hangs or fails slowly, the entire batch is delayed until that single request resolves. This is a trade-off for ensuring all data in a batch is processed together.