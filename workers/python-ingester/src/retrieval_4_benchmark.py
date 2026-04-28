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

# --- THE 20-QUERY ADVERSARIAL GAUNTLET (Bitcoin Academy edition) ---
# Each query targets the same structural trap as the original DL suite
# but uses Bitcoin-domain content so results are meaningful against
# the course material indexed in ChromaDB.
BENCHMARK_QUERIES = [
    # CATEGORY 1: DEFINITIONS
    {"cat": "1. Definition Lookup",
     "q": "What is a UTXO (Unspent Transaction Output) and how is it consumed when a new Bitcoin transaction is created?",
     "trap": "ToC Index Trap"},
    {"cat": "1. Definition Lookup",
     "q": "Define the Merkle root and explain its cryptographic role inside a Bitcoin block header.",
     "trap": "Sequential Noun Cluster Trap"},
    {"cat": "1. Definition Lookup",
     "q": "What is the specific definition of scriptSig and scriptPubKey and how do they interact during transaction validation?",
     "trap": "LaTeX Fragmentation Trap"},
    {"cat": "1. Definition Lookup",
     "q": "What is a Hash Time-Locked Contract (HTLC) and how is it used in Lightning Network payment channels?",
     "trap": "Disconnected Header Trap"},
    {"cat": "1. Definition Lookup",
     "q": "What is the precise definition of Segregated Witness (SegWit, BIP141) and which transaction malleability problem does it solve?",
     "trap": "Equation-Heavy Context Trap"},

    # CATEGORY 2: WHY/HOW
    {"cat": "2. Mechanisms & Processes",
     "q": "How does Bitcoin's difficulty adjustment algorithm recalculate the proof-of-work target every 2016 blocks?",
     "trap": "Math Derivation Trap"},
    {"cat": "2. Mechanisms & Processes",
     "q": "Why does Bitcoin use a stack-based scripting language and what security properties does this design guarantee?",
     "trap": "Historical Context Trap"},
    {"cat": "2. Mechanisms & Processes",
     "q": "How does the Bitcoin peer-to-peer network propagate new transactions using INV, GETDATA, and TX messages?",
     "trap": "Chunk Character Limit Boundary"},
    {"cat": "2. Mechanisms & Processes",
     "q": "What is the exact derivation path from a Bitcoin private key to a P2PKH address, including EC multiplication, SHA-256, RIPEMD-160, and Base58Check encoding?",
     "trap": "Code Block Trap"},
    {"cat": "2. Mechanisms & Processes",
     "q": "How does Simplified Payment Verification (SPV) use Merkle proofs to verify transactions without downloading the full blockchain?",
     "trap": "Pseudocode Trap"},

    # CATEGORY 3: COMPARISONS
    {"cat": "3. Relational Logic",
     "q": "What are the primary structural and security differences between Pay-to-Public-Key-Hash (P2PKH) and Pay-to-Script-Hash (P2SH) output types?",
     "trap": "Isolated Code Block Trap"},
    {"cat": "3. Relational Logic",
     "q": "Compare soft fork and hard fork upgrade mechanisms in Bitcoin in terms of backward compatibility and coordination requirements.",
     "trap": "Exercise Question Trap"},
    {"cat": "3. Relational Logic",
     "q": "How does an HTLC on the Lightning Network differ from a standard on-chain Bitcoin transaction in its locking and settlement mechanism?",
     "trap": "Cross-Chapter Fragmentation"},
    {"cat": "3. Relational Logic",
     "q": "What are the specific differences between BIP32 hierarchical deterministic wallets and BIP44 multi-account wallet derivation?",
     "trap": "Code Syntax Domination Trap"},
    {"cat": "3. Relational Logic",
     "q": "Compare the security guarantees and trust assumptions of a Bitcoin full node versus an SPV light client in a hostile network environment.",
     "trap": "Generic Acronym Density Trap"},

    # CATEGORY 4: ADVERSARIAL STRESS TESTS
    {"cat": "4. Adversarial Stress Tests",
     "q": "What is the exact mathematical formula for Bitcoin's difficulty target T given the ratio of actual to expected time for the last 2016 blocks?",
     "trap": "Pure LaTeX/Unicode Trap"},
    {"cat": "4. Adversarial Stress Tests",
     "q": "Design a 2-of-3 multisig P2SH locking script and detail each opcode (OP_2, OP_CHECKMULTISIG) together with the corresponding unlocking script.",
     "trap": "Verbatim Textbook Exercise Trap"},
    {"cat": "4. Adversarial Stress Tests",
     "q": "Provide a summary of the introduction to Bitcoin, including its peer-to-peer architecture, the role of cryptographic proof, and the mechanism for preventing double-spending.",
     "trap": "Massive ToC Sequence Trap"},
    {"cat": "4. Adversarial Stress Tests",
     "q": "Show the specific Python code using the 'ecdsa' or 'bitcoinlib' library for generating a Bitcoin private key and deriving the corresponding P2PKH address.",
     "trap": "Framework Action Block Trap"},
    # Deliberate ligature corruption (昀椀 = fi) — tests _sanitize_query() in retrieval_3_searcher.py
    {"cat": "4. Adversarial Stress Tests",
     "q": "Explain the symptoms of sel昀椀sh mining compared to honest mining and how the attacker gains a disproportionate share of block rewards.",
     "trap": "PDF Ligature Corruption Typo Trap"},
]

def run_benchmark():
    logger.info("Booting Verilocal Search Engine for Automated Benchmark...")
    searcher = VerilocalSearcher()
    
    report_lines = [
        "# ISSUE R-03: Retrieval Benchmark Report",
        f"**Date Executed:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "**Target:** Bitcoin Academy — 20-query adversarial gauntlet\n",
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