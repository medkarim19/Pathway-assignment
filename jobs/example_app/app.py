import time
import os

print("Starting example_app...")
print("ENV VARS:")
for k in ["APP_NAME", "REPLICA_ID"]:
    print(f"  {k}={os.getenv(k)}")

# Simulate a service that keeps running
for i in range(60):
    print(f"[{i}] hello from replica={os.getenv('REPLICA_ID')}")
    time.sleep(2)

print("Done.")

