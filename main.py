import subprocess
import sys
import time

def main():
    print("=" * 60)
    print("Starting Tweets Audit App (Celery Worker & FastAPI Server)...")
    print("=" * 60)
    
    # Celery worker process
    # Run as module with 'solo' pool for Windows compatibility
    celery_cmd = [
        sys.executable, "-m", "celery", 
        "-A", "src.celery_worker.celery_client", 
        "worker", 
        "--loglevel=info", 
        "--pool=solo"
    ]
    print(f"Launching Celery: {' '.join(celery_cmd)}")
    celery_proc = subprocess.Popen(celery_cmd)
    
    # FastAPI app process
    web_cmd = [
        sys.executable, "-m", "src.main"
    ]
    print(f"Launching FastAPI: {' '.join(web_cmd)}")
    web_proc = subprocess.Popen(web_cmd)
    
    print("\nBoth processes are running. Press Ctrl+C to terminate.")
    print("-" * 60)

    try:
        while True:
            # Check if any process terminated early
            if celery_proc.poll() is not None:
                print("Celery worker stopped unexpectedly.")
                break
            if web_proc.poll() is not None:
                print("FastAPI server stopped unexpectedly.")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Ctrl+C] Stopping processes...")
    finally:
        celery_proc.terminate()
        web_proc.terminate()
        
        # Wait for them to exit
        celery_proc.wait()
        web_proc.wait()
        print("Both processes stopped.")

if __name__ == "__main__":
    main()
