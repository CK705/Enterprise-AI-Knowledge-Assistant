import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import os

# Set style for academic/enterprise look
plt.style.use("seaborn-v0_8-darkgrid")
sns.set_context("paper", font_scale=1.4)
colors = ["#ef4444", "#3b82f6", "#10b981", "#f59e0b"]  # Red, Blue, Green, Amber
pipelines = ["Pipeline_A", "Pipeline_B", "Pipeline_C", "Pipeline_D"]
labels = ["Naive (A)", "Hybrid (B)", "Multi-hop (C)", "Self-Correcting (D)"]

# --- 1. GATHER RAGAS DATA ---
ragas_metrics = {
    "faithfulness": [],
    "answer_relevancy": [],
    "context_precision": [],
    "context_recall": [],
}
valid_pipelines = []
valid_labels = []

for i, p in enumerate(pipelines):
    file_path = f"{p}_graded_results.csv"
    if os.path.exists(file_path):
        df = pd.read_csv(file_path)
        valid_pipelines.append(p)
        valid_labels.append(labels[i])
        for metric in ragas_metrics.keys():
            if metric in df.columns:
                ragas_metrics[metric].append(df[metric].mean())
            else:
                ragas_metrics[metric].append(0)

# --- CHART 1: MASTER RAGAS BAR CHART ---
x = np.arange(len(ragas_metrics["faithfulness"]))
width = 0.2

fig, ax = plt.subplots(figsize=(12, 7))
ax.bar(
    x - width * 1.5,
    ragas_metrics["faithfulness"],
    width,
    label="Faithfulness (Safety)",
    color="#10b981",
)
ax.bar(
    x - width * 0.5,
    ragas_metrics["answer_relevancy"],
    width,
    label="Answer Relevancy",
    color="#3b82f6",
)
ax.bar(
    x + width * 0.5,
    ragas_metrics["context_precision"],
    width,
    label="Context Precision",
    color="#8b5cf6",
)
ax.bar(
    x + width * 1.5,
    ragas_metrics["context_recall"],
    width,
    label="Context Recall",
    color="#f59e0b",
)

ax.set_ylabel("RAGAS Score (0 to 1)")
ax.set_title(
    "Master Architecture Comparison: Generative Safety vs. Retrieval Focus",
    pad=20,
    fontsize=16,
    fontweight="bold",
)
ax.set_xticks(x)
ax.set_xticklabels(valid_labels)
ax.set_ylim(0, 1.1)
ax.legend(loc="upper right", bbox_to_anchor=(1, 1.05))

plt.tight_layout()
plt.savefig("master_ragas_bar_chart.png", dpi=300)
plt.close()

# --- CHART 2: RADAR CHART ---
angles = np.linspace(0, 2 * np.pi, 4, endpoint=False).tolist()
angles += angles[:1]  # Close the loop

fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(polar=True))
for i in range(len(valid_pipelines)):
    values = [
        ragas_metrics["faithfulness"][i],
        ragas_metrics["answer_relevancy"][i],
        ragas_metrics["context_precision"][i],
        ragas_metrics["context_recall"][i],
    ]
    values += values[:1]
    ax.plot(angles, values, color=colors[i], linewidth=2, label=valid_labels[i])
    ax.fill(angles, values, color=colors[i], alpha=0.1)

ax.set_xticks(angles[:-1])
ax.set_xticklabels(["Faithfulness", "Relevancy", "Precision", "Recall"], fontsize=12)
ax.set_ylim(0, 1)
plt.title("Architectural Footprint Matrix", size=16, fontweight="bold", pad=20)
plt.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))
plt.tight_layout()
plt.savefig("master_radar_chart.png", dpi=300)
plt.close()

# --- CHART 3: ENTERPRISE COST/LATENCY (From Raw CSV) ---
raw_file = "evaluation_results_raw.csv"
if os.path.exists(raw_file):
    df_raw = pd.read_csv(raw_file)
    latencies = []
    tokens = []

    for p in valid_pipelines:
        latencies.append(df_raw[f"{p}_Latency"].mean())
        tokens.append(df_raw[f"{p}_Tokens"].mean())

    fig, ax1 = plt.subplots(figsize=(10, 6))

    # Bar chart for Latency (Left Axis)
    x = np.arange(len(valid_pipelines))
    bar1 = ax1.bar(
        x - 0.2,
        latencies,
        0.4,
        label="Avg Latency (Seconds)",
        color="#ef4444",
        alpha=0.8,
    )
    ax1.set_ylabel("Latency (Seconds)", color="#ef4444", fontweight="bold")
    ax1.tick_params(axis="y", labelcolor="#ef4444")
    ax1.set_xticks(x)
    ax1.set_xticklabels(valid_labels)

    # Line chart for Tokens (Right Axis)
    ax2 = ax1.twinx()
    line1 = ax2.plot(
        x + 0.2,
        tokens,
        color="#1e3a8a",
        marker="o",
        linewidth=3,
        markersize=10,
        label="Avg Token Usage",
    )
    ax2.set_ylabel("Token Usage (Cost Proxy)", color="#1e3a8a", fontweight="bold")
    ax2.tick_params(axis="y", labelcolor="#1e3a8a")

    plt.title(
        "Enterprise Constraints: Processing Time vs. Token Cost",
        pad=20,
        fontsize=15,
        fontweight="bold",
    )

    # Combine legends
    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax2.legend(lines + lines2, labels + labels2, loc="upper left")

    plt.tight_layout()
    plt.savefig("enterprise_cost_latency_chart.png", dpi=300)
    plt.close()

print("✅ SUCCESS! 3 Master Charts generated in your folder!")
