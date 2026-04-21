import os
import sys
import logging
from datetime import datetime

# --- MONOREPO PATH FIX ---
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
sys.path.insert(0, project_root)
services_ai_root = os.path.join(project_root, "services", "ai")
sys.path.insert(0, services_ai_root)
# -------------------------

# Silence ChromaDB telemetry bug
os.environ["CHROMA_TELEMETRY_IMPL"] = "INMEMORY"

from retrieval_3_searcher import VerilocalSearcher

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# --- THE 20-QUERY ADVERSARIAL GAUNTLET ---
BENCHMARK_QUERIES = [
    # CATEGORY 1: DEFINITIONS
    {"cat": "1. Definition Lookup", "q": "Define perplexity in the context of language modeling and explain its best and worst-case scenarios.", "trap": "ToC Index Trap"},
    {"cat": "1. Definition Lookup", "q": "What is a tensor and how does it relate to scalars, vectors, and matrices in fundamental linear algebra?", "trap": "Sequential Noun Cluster Trap"},
    {"cat": "1. Definition Lookup", "q": "What is the specific definition of Weight Decay and how does it restrict the values that parameters can take?", "trap": "LaTeX Fragmentation Trap"},
    {"cat": "1. Definition Lookup", "q": "Provide the definition of Xavier initialization and explain how it addresses symmetry in neural network design.", "trap": "Disconnected Header Trap"},
    {"cat": "1. Definition Lookup", "q": "What is the specific definition of the Gated Recurrent Unit (GRU) Update Gate?", "trap": "Equation-Heavy Context Trap"},
    
    # CATEGORY 2: WHY/HOW
    {"cat": "2. Mechanisms & Processes", "q": "How does the backpropagation through time (BPTT) algorithm address hidden states and why is truncation necessary?", "trap": "Math Derivation Trap"},
    {"cat": "2. Mechanisms & Processes", "q": "Why does the vanishing gradient problem occur specifically when using sigmoid activation functions in deep neural networks?", "trap": "Historical Context Trap"},
    {"cat": "2. Mechanisms & Processes", "q": "How does batch normalization mathematically transform data during the training phase, and how does this differ from the prediction phase?", "trap": "Chunk Character Limit Boundary"},
    {"cat": "2. Mechanisms & Processes", "q": "What is the mechanism by which Multi-Head Attention combines different representation subspaces of queries, keys, and values?", "trap": "Tensor Code Block Trap"},
    {"cat": "2. Mechanisms & Processes", "q": "How does the Adam optimizer integrate momentum and adaptive learning concepts computationally using moving averages?", "trap": "Pseudocode Trap"},
    
    # CATEGORY 3: COMPARISONS
    {"cat": "3. Relational Logic", "q": "What are the primary architectural and structural differences between AlexNet and LeNet-5?", "trap": "Isolated Code Block Trap"},
    {"cat": "3. Relational Logic", "q": "Compare the mechanisms and use cases of L1 regularization with L2 weight decay.", "trap": "Exercise Question Trap"},
    {"cat": "3. Relational Logic", "q": "How does a Gated Recurrent Unit (GRU) memory cell differ from a Long Short-Term Memory (LSTM) cell in terms of gating mechanisms?", "trap": "Cross-Chapter Fragmentation"},
    {"cat": "3. Relational Logic", "q": "What are the specific differences between the PyTorch and MXNet primitive implementations of a Dropout layer from scratch?", "trap": "Code Syntax Domination Trap"},
    {"cat": "3. Relational Logic", "q": "Compare the performance, directional sharpness, and gradient convergence characteristics of the Adam optimizer versus Stochastic Gradient Descent (SGD).", "trap": "Generic Acronym Density Trap"},
    
    # CATEGORY 4: EDGE CASES
    {"cat": "4. Adversarial Stress Tests", "q": "What is the exact mathematical equation for the Batch Normalization output $\\text{BN}(\\mathbf{x})$ during training, including the scale and shift parameters?", "trap": "Pure LaTeX/Unicode Trap"},
    {"cat": "4. Adversarial Stress Tests", "q": "Design a CNN architecture that includes multiple convolutional and pooling layers, detailing the types of layers, their sequence, and their primary functions.", "trap": "Verbatim Textbook Exercise Trap"},
    {"cat": "4. Adversarial Stress Tests", "q": "Provide a summary of the introduction to deep learning, including a motivating example and the key components of machine learning problems.", "trap": "Massive ToC Sequence Trap"},
    {"cat": "4. Adversarial Stress Tests", "q": "Show the specific PyTorch concise implementation code using high-level APIs for initializing a Dropout Multilayer Perceptron.", "trap": "Framework Action Block Trap"},
    {"cat": "4. Adversarial Stress Tests", "q": "Explain the symptoms of model under昀椀tting compared to over昀椀tting and how generalization error is impacted.", "trap": "PDF Ligature Corruption Typo Trap"}
]

def run_benchmark():
    logger.info("Booting Verilocal Search Engine for Automated Benchmark...")
    searcher = VerilocalSearcher()
    
    report_lines = [
        "# ISSUE R-03: Retrieval Benchmark Report",
        f"**Date Executed:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "**Target:** Dive Into Deep Learning (PDF Baseline Test)\n",
        "---"
    ]
    
    current_cat = ""
    
    for i, item in enumerate(BENCHMARK_QUERIES, 1):
        if item['cat'] != current_cat:
            current_cat = item['cat']
            report_lines.append(f"\n## {current_cat}\n")
            
        logger.info(f"Running Query {i}/20: {item['trap']}...")
        
        report_lines.append(f"### Query {i}: *\"{item['q']}\"*")
        report_lines.append(f"**Adversarial Target:** {item['trap']}\n")
        
        results = searcher.search(query=item['q'], top_k=3)
        
        report_lines.append("**Top 3 Retrieved Chunks:**")
        for rank, res in enumerate(results, 1):
            dist = res['distance']
            source = res['label']
            section = res['section']
            # Clean up the text preview (remove newlines so it fits in a markdown table nicely)
            preview = res['text'][:200].replace('\n', ' ') + "..."
            
            report_lines.append(f"- **[{rank}]** (Dist: {dist:.4f}) | {source} | **{section}**")
            report_lines.append(f"  > {preview}")
            
        report_lines.append("\n**Manual Relevance Grade:** [ Pass / Fail ]")
        report_lines.append("**Failure Notes:** (Leave blank if passed)\n")
        report_lines.append("---\n")

    # Save the report
    report_path = os.path.join(os.path.dirname(__file__), "../R-03_Benchmark_Report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
        
    logger.info(f"\nBenchmark Complete! Report generated at: {os.path.abspath(report_path)}")

if __name__ == "__main__":
    run_benchmark()