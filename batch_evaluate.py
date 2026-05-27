import pandas as pd
import requests
import time
import json

# 1. Load your dataset
print("Loading dataset...")
df = pd.read_csv("dataset.csv", encoding="cp1252").iloc[75:]

# Ensure we have a place to store results
results = []

# API Endpoint mapping
endpoints = {
    "Pipeline_A": "http://localhost:8000/query/naive",
    "Pipeline_B": "http://localhost:8000/query/hybrid",
    "Pipeline_C": "http://localhost:8000/query/multihop",
    "Pipeline_D": "http://localhost:8000/query/self_correct",
}

# 2. Loop through every question in your CSV
for index, row in df.iterrows():
    question = row["Question"]
    expected_answer = row["Expected Answer"]
    q_type = row["Type"]

    print(f"\n[{index + 1}/{len(df)}] Testing: {question[:50]}...")

    row_result = {
        "ID": row.get("ID", index),
        "Type": q_type,
        "Question": question,
        "Expected Answer": expected_answer,
    }

    # 3. Test each pipeline
    # 3. Test each pipeline
    for pipeline_name, url in endpoints.items():
        MAX_RETRIES = 5

        for attempt in range(MAX_RETRIES):
            try:
                # 💡 THE FIX: Pad the baseline sleep to 7 seconds.
                # 4 pipelines * 7s = 28 seconds per question block.
                # This guarantees we stay safely below the 10 requests-per-minute ceiling!
                time.sleep(7)

                response = requests.post(url, json={"question": question})

                if response.status_code == 200:
                    data = response.json()
                    row_result[f"{pipeline_name}_Answer"] = data.get("answer", "")
                    row_result[f"{pipeline_name}_Latency"] = data.get("latency", 0)

                    tokens = data.get("tokens", {})
                    row_result[f"{pipeline_name}_Tokens"] = tokens.get(
                        "total_tokens",
                        tokens.get("output_tokens", 0) + tokens.get("input_tokens", 0),
                    )

                    row_result[f"{pipeline_name}_Context"] = "\n".join(
                        data.get("retrieved_chunks", [])
                    )

                    # Success! Break out of the retry loop
                    break

                # 💡 THE FIX: Handle the 429 or 500 status gracefully by sleeping longer
                else:
                    print(
                        f"  ⚠️ {pipeline_name} returned status {response.status_code}. (Attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    if attempt < MAX_RETRIES - 1:
                        # If we get rate limited, sit out for 45 seconds to clear the window
                        print(
                            "  ⏳ Windows rate limit reached. Cooling down for 45 seconds..."
                        )
                        time.sleep(45)
                    else:
                        print("  ❌ Max retries reached. Logging API ERROR.")
                        row_result[f"{pipeline_name}_Answer"] = "API ERROR"

            except Exception as e:
                print(f"  🛑 CRASH on {pipeline_name}: {str(e)}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(15)
                else:
                    row_result[f"{pipeline_name}_Answer"] = f"CRASH: {str(e)}"

    results.append(row_result)

    # Save incrementally
    pd.DataFrame(results).to_csv("evaluation_results_raw.csv", index=False)

print("\n✅ Batch testing complete! Results saved to evaluation_results_raw.csv")
