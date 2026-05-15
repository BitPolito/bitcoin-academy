"""RAG quality evaluation using the RAGAS framework.

Run manually before deployment (requires a live stack):

    docker-compose up -d api qvac redis postgres
    uv run pytest tests/eval/test_rag_quality.py -v --no-cov -s

Prerequisites:
    uv add ragas --dev
    At least one course must be indexed with Bitcoin materials.

Thresholds (fail if any drops below):
    context_recall   > 0.70
    faithfulness     > 0.85
    answer_relevance > 0.75
"""

import os
import httpx
import pytest

# ---------------------------------------------------------------------------
# QA pairs — 35 question / answer / reference triplets
# ---------------------------------------------------------------------------

QA_PAIRS = [
    # --- Foundations ---
    {
        "question": "What is a UTXO?",
        "ground_truth": "A UTXO (Unspent Transaction Output) is an output of a Bitcoin transaction that has not been spent. It represents the amount of Bitcoin that a user can spend in a future transaction.",
        "reference_keywords": ["unspent transaction output", "UTXO", "output", "spend"],
    },
    {
        "question": "How does Bitcoin mining work?",
        "ground_truth": "Bitcoin mining is the process by which new transactions are added to the blockchain. Miners compete to find a nonce such that the SHA-256 hash of the block header is below the network's target difficulty. The winning miner earns the block reward plus transaction fees.",
        "reference_keywords": ["proof of work", "hash", "nonce", "difficulty", "block reward"],
    },
    {
        "question": "What is the Merkle tree and why is it used in Bitcoin?",
        "ground_truth": "A Merkle tree is a binary tree of cryptographic hashes. In Bitcoin, transactions in a block are hashed pairwise until a single Merkle root is produced. It allows efficient and secure verification of whether a transaction was included in a block without downloading the full block.",
        "reference_keywords": ["Merkle", "hash", "transaction", "root", "verification"],
    },
    {
        "question": "Why does Bitcoin have a 21 million coin limit?",
        "ground_truth": "The 21 million BTC supply cap is encoded in the Bitcoin protocol via the halving schedule. The block subsidy started at 50 BTC and halves approximately every 210,000 blocks, converging to zero over time. This creates predictable monetary scarcity.",
        "reference_keywords": ["supply", "halving", "21 million", "scarcity", "block reward"],
    },
    {
        "question": "What is a blockchain fork?",
        "ground_truth": "A blockchain fork occurs when the chain diverges into two potential paths. A hard fork is a protocol change that is not backward-compatible, causing a permanent chain split if not universally adopted. A soft fork is a backward-compatible tightening of the rules.",
        "reference_keywords": ["hard fork", "soft fork", "consensus", "chain split"],
    },
    # --- Cryptography ---
    {
        "question": "What is a digital signature in Bitcoin?",
        "ground_truth": "Bitcoin uses ECDSA (Elliptic Curve Digital Signature Algorithm) over the secp256k1 curve. A private key produces a signature for a transaction; the corresponding public key allows anyone to verify it without knowing the private key.",
        "reference_keywords": ["ECDSA", "private key", "public key", "signature", "secp256k1"],
    },
    {
        "question": "How is a Bitcoin address derived from a public key?",
        "ground_truth": "A Bitcoin address is derived by applying SHA-256 then RIPEMD-160 to the public key (compressed or uncompressed), then adding a version byte and a checksum and encoding the result in Base58Check.",
        "reference_keywords": ["SHA-256", "RIPEMD-160", "Base58Check", "address", "public key hash"],
    },
    {
        "question": "What is the difference between SegWit and Taproot?",
        "ground_truth": "SegWit (BIP141) separates the signature data from the transaction body, fixing transaction malleability and reducing fees. Taproot (BIP340-342) introduces Schnorr signatures and MAST, improving privacy and efficiency for complex scripts.",
        "reference_keywords": ["SegWit", "Taproot", "witness", "signature", "Schnorr"],
    },
    {
        "question": "What is Script in Bitcoin transactions?",
        "ground_truth": "Bitcoin Script is a Forth-like stack-based language used to define spending conditions (locking scripts) and their solutions (unlocking scripts). Common types include P2PKH, P2SH, and P2WPKH.",
        "reference_keywords": ["Script", "locking", "unlocking", "P2PKH", "stack"],
    },
    # --- Network & Consensus ---
    {
        "question": "How does a Bitcoin transaction get confirmed?",
        "ground_truth": "An unconfirmed transaction is broadcast to the peer-to-peer network and waits in miners' mempools. Miners select transactions (prioritised by fee rate) to include in a block. A transaction is confirmed when the block containing it is accepted by the network.",
        "reference_keywords": ["mempool", "miner", "fee", "confirmation", "block"],
    },
    {
        "question": "How does the difficulty adjustment algorithm work?",
        "ground_truth": "Every 2,016 blocks (approximately two weeks) Bitcoin recalculates the proof-of-work target. If blocks were found faster than 10 minutes on average, the difficulty increases; if slower, it decreases. The maximum adjustment per period is 4×.",
        "reference_keywords": ["difficulty", "2016 blocks", "target", "retargeting", "hashrate"],
    },
    {
        "question": "Why is double spending a problem and how does Bitcoin solve it?",
        "ground_truth": "Double spending means spending the same bitcoin twice. Bitcoin prevents it through the proof-of-work consensus rule: the longest valid chain wins, and rewriting history requires more than 50% of the total network hashrate.",
        "reference_keywords": ["double spend", "consensus", "longest chain", "proof of work", "51%"],
    },
    {
        "question": "What is the difference between a full node and a light node?",
        "ground_truth": "A full node downloads and validates every block and transaction, maintaining the complete UTXO set. An SPV (Simplified Payment Verification) light node only downloads block headers and uses Merkle proofs to verify specific transactions.",
        "reference_keywords": ["full node", "SPV", "light client", "block header", "verification"],
    },
    {
        "question": "What is the Lightning Network?",
        "ground_truth": "The Lightning Network is a second-layer payment channel network built on Bitcoin. Two parties lock funds in a multisig UTXO and exchange off-chain commitment transactions. Payments can be routed across channels using HTLCs without on-chain settlement for every transaction.",
        "reference_keywords": ["Lightning", "payment channel", "off-chain", "routing", "HTLC"],
    },
    # --- Transactions & Fees ---
    {
        "question": "How are transaction fees calculated in Bitcoin?",
        "ground_truth": "Bitcoin transaction fees are based on transaction size in virtual bytes (vbytes) multiplied by the fee rate (sat/vbyte) set by the sender. Miners pick transactions with the highest fee rates to maximise revenue.",
        "reference_keywords": ["fee", "sat/vbyte", "virtual bytes", "mempool", "priority"],
    },
    {
        "question": "What is a coinbase transaction?",
        "ground_truth": "A coinbase transaction is the first transaction in every block. It has no inputs and creates new Bitcoin (the block subsidy). The miner can include an arbitrary data field and collects all transaction fees from the block.",
        "reference_keywords": ["coinbase", "block reward", "subsidy", "miner", "first transaction"],
    },
    {
        "question": "What is Replace-By-Fee (RBF)?",
        "ground_truth": "Replace-By-Fee is a mechanism (BIP125) that allows a sender to replace an unconfirmed transaction with a higher-fee version. Nodes that support RBF will evict the original transaction from their mempool when they see the replacement.",
        "reference_keywords": ["RBF", "Replace-By-Fee", "BIP125", "mempool", "fee bump"],
    },
    # --- Wallets & Keys ---
    {
        "question": "What is a BIP-32 HD wallet?",
        "ground_truth": "A Hierarchical Deterministic (HD) wallet derives an unlimited number of public/private key pairs from a single root seed using a chain of HMAC-SHA512 operations. This allows wallet backup from a single mnemonic phrase.",
        "reference_keywords": ["BIP-32", "HD wallet", "hierarchical deterministic", "seed", "mnemonic"],
    },
    {
        "question": "What is the purpose of a seed phrase (mnemonic)?",
        "ground_truth": "A seed phrase (BIP-39) is a human-readable encoding of a wallet's root entropy, typically 12 or 24 words. It allows complete wallet recovery: all keys, addresses, and balances can be regenerated from it.",
        "reference_keywords": ["seed phrase", "mnemonic", "BIP-39", "entropy", "recovery"],
    },
    {
        "question": "What is the difference between a hot wallet and a cold wallet?",
        "ground_truth": "A hot wallet is connected to the internet and allows quick spending but is exposed to network attacks. A cold wallet stores keys offline (hardware device, paper) and is more secure for long-term storage at the cost of convenience.",
        "reference_keywords": ["hot wallet", "cold wallet", "hardware wallet", "security", "offline"],
    },
    # --- Bitcoin history ---
    {
        "question": "When did the first Bitcoin halving occur and what was its effect?",
        "ground_truth": "The first Bitcoin halving occurred in November 2012 at block 210,000. The block reward decreased from 50 BTC to 25 BTC. Historically halvings have been associated with reduced sell pressure from miners and subsequent price appreciation.",
        "reference_keywords": ["halving", "2012", "block reward", "50 BTC", "25 BTC"],
    },
    {
        "question": "What was the Bitcoin genesis block?",
        "ground_truth": "The genesis block (block 0) was mined by Satoshi Nakamoto on January 3, 2009. Its coinbase contains the headline 'The Times 03/Jan/2009 Chancellor on brink of second bailout for banks'. The 50 BTC reward is unspendable.",
        "reference_keywords": ["genesis block", "Satoshi", "2009", "The Times", "block 0"],
    },
    # --- Advanced topics ---
    {
        "question": "What is a multisig transaction?",
        "ground_truth": "A multisignature (multisig) transaction requires M of N private key signatures to unlock funds. For example, a 2-of-3 multisig requires any two of three key holders to sign. It is used for shared custody and enhanced security.",
        "reference_keywords": ["multisig", "M-of-N", "multiple signatures", "P2SH", "custody"],
    },
    {
        "question": "What is Taproot and why was it introduced?",
        "ground_truth": "Taproot (activated in November 2021) introduced Schnorr signatures and Merkelized Abstract Syntax Trees (MAST). It improves privacy by making complex smart contracts look like simple payments, and reduces the on-chain footprint of complex spending conditions.",
        "reference_keywords": ["Taproot", "Schnorr", "MAST", "privacy", "BIP340", "2021"],
    },
    {
        "question": "What is Simplified Payment Verification (SPV)?",
        "ground_truth": "SPV is a method described in the Bitcoin whitepaper that allows a lightweight client to verify payments without downloading the full blockchain. It downloads only block headers and requests Merkle proofs for specific transactions from full nodes.",
        "reference_keywords": ["SPV", "block headers", "Merkle proof", "lightweight", "whitepaper"],
    },
    {
        "question": "What is the mempool?",
        "ground_truth": "The mempool (memory pool) is the set of unconfirmed transactions that a node has received and validated but not yet seen in a block. Miners select transactions from the mempool to fill new blocks, prioritising by fee rate.",
        "reference_keywords": ["mempool", "unconfirmed", "transactions", "fee rate", "miners"],
    },
    {
        "question": "How does the Bitcoin P2P network propagate transactions?",
        "ground_truth": "When a node receives a new transaction it validates it and announces it to its peers via an INV message. Peers that haven't seen it request the full transaction. This gossip propagation reaches the whole network within seconds.",
        "reference_keywords": ["P2P", "INV", "broadcast", "gossip", "propagation", "peer"],
    },
    {
        "question": "What is ECDSA and why does Bitcoin use it?",
        "ground_truth": "ECDSA (Elliptic Curve Digital Signature Algorithm) allows compact key sizes with high security. Bitcoin uses the secp256k1 curve: a 256-bit private key provides ~128 bits of security. It enables transaction authorisation without revealing the private key.",
        "reference_keywords": ["ECDSA", "elliptic curve", "secp256k1", "private key", "signature"],
    },
    {
        "question": "What is the block size limit and what problem does it cause?",
        "ground_truth": "Bitcoin originally had a 1 MB block size limit (now 4 MB in weight units with SegWit). This caps throughput at roughly 7 transactions per second, causing mempool congestion and high fees during demand spikes.",
        "reference_keywords": ["block size", "1 MB", "throughput", "congestion", "SegWit weight"],
    },
    {
        "question": "What is a hash function and why is it important in Bitcoin?",
        "ground_truth": "A cryptographic hash function maps arbitrary input to a fixed-length digest. Bitcoin uses SHA-256 for proof-of-work, address derivation, and block chaining. Key properties: deterministic, fast to compute, collision-resistant, and irreversible (preimage resistant).",
        "reference_keywords": ["SHA-256", "hash", "deterministic", "collision resistant", "one-way"],
    },
    # --- Programming / protocol ---
    {
        "question": "What is OP_RETURN used for?",
        "ground_truth": "OP_RETURN is a Bitcoin Script opcode that marks an output as provably unspendable. It allows attaching up to 80 bytes of arbitrary data to a transaction, used for timestamping, coloured coins, and other metadata applications.",
        "reference_keywords": ["OP_RETURN", "unspendable", "data", "80 bytes", "metadata"],
    },
    {
        "question": "What is BIP (Bitcoin Improvement Proposal)?",
        "ground_truth": "A Bitcoin Improvement Proposal is a design document for proposing new features or changes to the Bitcoin protocol, similar to Python's PEPs. BIPs are numbered and categorised (Standards Track, Informational, Process) and must go through community review before activation.",
        "reference_keywords": ["BIP", "improvement proposal", "protocol", "standards", "community"],
    },
    {
        "question": "What is Proof of Work?",
        "ground_truth": "Proof of Work is the consensus mechanism used by Bitcoin. Miners must find a block header nonce such that SHA-256(SHA-256(header)) produces a hash below the current target. This requires enormous computational effort but is trivially verifiable by any node.",
        "reference_keywords": ["proof of work", "nonce", "target", "SHA-256", "consensus"],
    },
    {
        "question": "What is a blockchain?",
        "ground_truth": "A blockchain is a chain of blocks where each block contains a cryptographic hash of the previous block, a timestamp, and transaction data. This structure makes it computationally impractical to alter past blocks without redoing all subsequent proof-of-work.",
        "reference_keywords": ["blockchain", "block", "hash", "immutable", "chain"],
    },
    {
        "question": "What is a Schnorr signature and how does it differ from ECDSA?",
        "ground_truth": "Schnorr signatures (BIP340) are linear: multiple signatures can be aggregated into a single signature (MuSig). Unlike ECDSA they are provably secure and non-malleable. In Taproot, key-path spends use Schnorr, making multisig indistinguishable from single-sig on-chain.",
        "reference_keywords": ["Schnorr", "aggregation", "MuSig", "ECDSA", "BIP340", "non-malleable"],
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api")
EVAL_COURSE_ID = os.getenv("EVAL_COURSE_ID", "")
RAGAS_AVAILABLE = True

try:
    from ragas import evaluate
    from ragas.metrics import context_recall, faithfulness, answer_relevancy
    from datasets import Dataset
except ImportError:
    RAGAS_AVAILABLE = False


def _get_auth_token() -> str:
    email = os.getenv("EVAL_USER_EMAIL", "test@bitpolito.it")
    password = os.getenv("EVAL_USER_PASSWORD", "testpassword")
    resp = httpx.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
    resp.raise_for_status()
    return resp.json()["access_token"]


def _chat(token: str, course_id: str, question: str) -> dict:
    resp = httpx.post(
        f"{BASE_URL}/chat/{course_id}",
        json={"question": question},
        headers={"Authorization": f"Bearer {token}"},
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not RAGAS_AVAILABLE, reason="ragas not installed — run: uv add ragas --dev")
@pytest.mark.skipif(not EVAL_COURSE_ID, reason="EVAL_COURSE_ID env var not set")
class TestRagQuality:
    """End-to-end RAG quality evaluation.

    Requires a live stack and an indexed course. Run manually:
        EVAL_COURSE_ID=<course-id> uv run pytest tests/eval/test_rag_quality.py -v --no-cov -s
    """

    @pytest.fixture(scope="class")
    def token(self):
        return _get_auth_token()

    @pytest.fixture(scope="class")
    def pipeline_outputs(self, token):
        """Run all QA pairs through the live pipeline and collect results."""
        outputs = []
        for pair in QA_PAIRS:
            try:
                result = _chat(token, EVAL_COURSE_ID, pair["question"])
                answer = result.get("answer", "")
                contexts = [c.get("snippet", "") for c in result.get("citations", [])]
                outputs.append({
                    "question": pair["question"],
                    "answer": answer,
                    "contexts": contexts if contexts else [""],
                    "ground_truth": pair["ground_truth"],
                })
            except Exception as exc:
                pytest.fail(f"Pipeline call failed for '{pair['question']}': {exc}")
        return outputs

    def test_context_recall(self, pipeline_outputs):
        ds = Dataset.from_list(pipeline_outputs)
        result = evaluate(ds, metrics=[context_recall])
        score = result["context_recall"]
        assert score > 0.70, f"context_recall {score:.3f} < 0.70"

    def test_faithfulness(self, pipeline_outputs):
        ds = Dataset.from_list(pipeline_outputs)
        result = evaluate(ds, metrics=[faithfulness])
        score = result["faithfulness"]
        assert score > 0.85, f"faithfulness {score:.3f} < 0.85"

    def test_answer_relevancy(self, pipeline_outputs):
        ds = Dataset.from_list(pipeline_outputs)
        result = evaluate(ds, metrics=[answer_relevancy])
        score = result["answer_relevancy"]
        assert score > 0.75, f"answer_relevancy {score:.3f} < 0.75"


@pytest.mark.skipif(not EVAL_COURSE_ID, reason="EVAL_COURSE_ID env var not set")
class TestKeywordRecall:
    """Lightweight keyword-based recall check — no RAGAS dependency required."""

    @pytest.fixture(scope="class")
    def token(self):
        return _get_auth_token()

    def test_keyword_recall_per_question(self, token):
        """At least 50% of expected keywords appear in the answer for each question."""
        failures = []
        for pair in QA_PAIRS:
            result = _chat(token, EVAL_COURSE_ID, pair["question"])
            answer = (result.get("answer") or "").lower()
            keywords = pair["reference_keywords"]
            hits = [kw for kw in keywords if kw.lower() in answer]
            recall = len(hits) / len(keywords) if keywords else 1.0
            if recall < 0.5:
                failures.append(
                    f"Q: {pair['question']!r}\n"
                    f"  recall={recall:.2f}  missing={[kw for kw in keywords if kw.lower() not in answer]}"
                )
        if failures:
            pytest.fail("Low keyword recall for:\n" + "\n".join(failures))
