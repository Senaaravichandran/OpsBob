"""
Full end-to-end pipeline test — sends an incident to commander and watches for
all 4 sub-agent tool calls to hit the backend.
"""
import asyncio, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from orchestrate_client import _invoke_agent

INCIDENT = """INCIDENT: INC-E2E-001
SERVICE: payments-api
SEVERITY: P1
DESCRIPTION: Memory leak detected in PaymentProcessor.processTransaction() causing OOM kills every 45 minutes.

PROPOSED FIX (code diff):
```diff
- private Map<String, byte[]> cache = new HashMap<>();
+ private WeakHashMap<String, byte[]> cache = new WeakHashMap<>();

  public void processTransaction(String txId, byte[] payload) {
-     cache.put(txId, payload);  // never evicted, causes OOM
+     cache.put(txId, payload);
      executePayment(txId, payload);
  }
```

TEST COMMAND: npm test
WORKING DIRECTORY: /opt/payments-api
REPOSITORY: payments-api/src/main/java/com/payments/PaymentProcessor.java

Please now run the full incident response pipeline:
1. Run static analysis on the code diff above
2. Run regression tests using: npm test
3. Route for approval based on results
4. Generate the post-incident report
"""

async def main():
    print("=" * 60)
    print("SENDING INCIDENT TO COMMANDER")
    print("=" * 60)
    print(f"\nIncident: INC-E2E-001 | Service: payments-api | Severity: P1\n")

    start = time.time()
    try:
        result = await _invoke_agent(INCIDENT)
        elapsed = time.time() - start
        print(f"\n{'='*60}")
        print(f"COMMANDER RESPONSE  ({elapsed:.1f}s)")
        print(f"{'='*60}")
        import json
        text = result.get("data", {}).get("message", {}).get("content", [{}])[0].get("text", str(result))
        print(text)
    except Exception as e:
        print(f"ERROR: {e}")

asyncio.run(main())
