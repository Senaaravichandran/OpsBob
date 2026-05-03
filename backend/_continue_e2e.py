"""
Continue the existing thread with code diff so pipeline proceeds to all 4 agents.
Thread from previous run: 5b18e91c-27ca-4fb7-8585-321109212a1f
"""
import asyncio, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from orchestrate_client import _invoke_agent

THREAD_ID = "473e63e6-f094-40f5-8ae0-1155474b1504"

FOLLOW_UP = """Incident ID: INC-E2E-001

Code diff for PaymentProcessor.processTransaction():

```diff
- private Map<String, byte[]> cache = new HashMap<>();
+ private WeakHashMap<String, byte[]> cache = new WeakHashMap<>();

  public void processTransaction(String txId, byte[] payload) {
-     cache.put(txId, payload);  // never evicted
+     cache.put(txId, payload);
      // ... process payment
  }
```

Repository: payments-api/src/main/java/com/payments/PaymentProcessor.java
Working directory: /opt/payments-api

Please proceed with:
1. Static analysis of this diff
2. Run regression tests
3. Route for approval  
4. Generate post-incident report
"""

async def main():
    print("=" * 60)
    print("CONTINUING THREAD WITH CODE DIFF")
    print(f"Thread: {THREAD_ID}")
    print("=" * 60)

    start = time.time()
    try:
        result = await _invoke_agent(FOLLOW_UP, thread_id=THREAD_ID)
        elapsed = time.time() - start
        print(f"\n{'='*60}")
        print(f"COMMANDER RESPONSE  ({elapsed:.1f}s)")
        print(f"{'='*60}")

        content = result.get("result", {}).get("data", {}).get("message", {}).get("content", [{}])
        text = content[0].get("text", str(result)) if content else str(result)
        print(text)

        # Print step history to see which agents were called
        step_history = result.get("result", {}).get("data", {}).get("message", {}).get("step_history", [])
        if step_history:
            print(f"\n{'='*60}")
            print("AGENTS INVOKED (step_history):")
            print(f"{'='*60}")
            for step in step_history:
                for detail in step.get("step_details", []):
                    if detail.get("type") == "tool_calls":
                        for tc in detail.get("tool_calls", []):
                            print(f"  ✓ {tc['name']}")
                    elif detail.get("type") == "tool_response":
                        print(f"    └─ response: {detail.get('content','')[:400]}")

    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(main())
