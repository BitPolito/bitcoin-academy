# ISSUE R-03: Retrieval Benchmark Report
**Date Executed:** 2026-04-28 20:40:27
**Target:** Bitcoin Academy — 20-query adversarial gauntlet

---

## 1. Definition Lookup

### Query 1: *"What is a UTXO (Unspent Transaction Output) and how is it consumed when a new Bitcoin transaction is created?"*
**Adversarial Target:** ToC Index Trap

**Top 3 Retrieved Chunks:**
- **[1]** (Dist: 0.1802) | p. 3 | **3. Transactions**
  > 3. Transactions  A transaction has inputs (spends UTXOs) and outputs (creates new UTXOs). Scripting language enables conditions like P2PKH: OP_DUP OP_HASH160 OP_EQUALVERIFY OP_CHECKSIG. Sig Hash types...
- **[2]** (Dist: 0.2984) | p. 2 | **1. Introduction**
  > 1. Introduction  Bitcoin is a decentralized digital currency that enables peer-to-peer transactions without intermediaries. Introduced in the 2008 whitepaper by Satoshi Nakamoto, it uses a proof-of-wo...
- **[3]** (Dist: 0.3070) | p. 4 | **License**
  > License  This document is released under Creative Commons Attribution 4.0 International (CC BY 4.0). You are free to share, adapt, and build upon it with attribution. Sources include Bitcoin Developer...

**Manual Relevance Grade:** [ Pass / Fail ]
**Failure Notes:** (Leave blank if passed)

---

### Query 2: *"Define the Merkle root and explain its cryptographic role inside a Bitcoin block header."*
**Adversarial Target:** Sequential Noun Cluster Trap

**Top 3 Retrieved Chunks:**
- **[1]** (Dist: 0.1778) | p. 2 | **2. Blockchain Structure**
  > 2. Blockchain Structure  Each block contains a header with: Version number Previous block hash Merkle root of transactions Timestamp Difficulty target (bits) Nonce The chain links blocks via hash poin...
- **[2]** (Dist: 0.2152) | p. 4 | **License**
  > License  This document is released under Creative Commons Attribution 4.0 International (CC BY 4.0). You are free to share, adapt, and build upon it with attribution. Sources include Bitcoin Developer...
- **[3]** (Dist: 0.2234) | p. 3 | **4. Consensus and Mining**
  > 4. Consensus and Mining  Proof-of-Work: Find nonce such that SHA256(SHA256(header)) < target. Difficulty adjusts every 2016 blocks to ~10 min intervals. Longest chain rule resolves forks.[web:21]...

**Manual Relevance Grade:** [ Pass / Fail ]
**Failure Notes:** (Leave blank if passed)

---

### Query 3: *"What is the specific definition of scriptSig and scriptPubKey and how do they interact during transaction validation?"*
**Adversarial Target:** LaTeX Fragmentation Trap

**Top 3 Retrieved Chunks:**
- **[1]** (Dist: 0.1946) | p. 3 | **3. Transactions**
  > 3. Transactions  A transaction has inputs (spends UTXOs) and outputs (creates new UTXOs). Scripting language enables conditions like P2PKH: OP_DUP OP_HASH160 OP_EQUALVERIFY OP_CHECKSIG. Sig Hash types...
- **[2]** (Dist: 0.2454) | p. 4 | **License**
  > License  This document is released under Creative Commons Attribution 4.0 International (CC BY 4.0). You are free to share, adapt, and build upon it with attribution. Sources include Bitcoin Developer...
- **[3]** (Dist: 0.2569) | p. 2 | **2. Blockchain Structure**
  > 2. Blockchain Structure  Each block contains a header with: Version number Previous block hash Merkle root of transactions Timestamp Difficulty target (bits) Nonce The chain links blocks via hash poin...

**Manual Relevance Grade:** [ Pass / Fail ]
**Failure Notes:** (Leave blank if passed)

---

### Query 4: *"What is a Hash Time-Locked Contract (HTLC) and how is it used in Lightning Network payment channels?"*
**Adversarial Target:** Disconnected Header Trap

**Top 3 Retrieved Chunks:**
- **[1]** (Dist: 0.3058) | p. 2 | **2. Blockchain Structure**
  > 2. Blockchain Structure  Each block contains a header with: Version number Previous block hash Merkle root of transactions Timestamp Difficulty target (bits) Nonce The chain links blocks via hash poin...
- **[2]** (Dist: 0.3298) | p. 3 | **3. Transactions**
  > 3. Transactions  A transaction has inputs (spends UTXOs) and outputs (creates new UTXOs). Scripting language enables conditions like P2PKH: OP_DUP OP_HASH160 OP_EQUALVERIFY OP_CHECKSIG. Sig Hash types...
- **[3]** (Dist: 0.3299) | p. 4 | **License**
  > License  This document is released under Creative Commons Attribution 4.0 International (CC BY 4.0). You are free to share, adapt, and build upon it with attribution. Sources include Bitcoin Developer...

**Manual Relevance Grade:** [ Pass / Fail ]
**Failure Notes:** (Leave blank if passed)

---

### Query 5: *"What is the precise definition of Segregated Witness (SegWit, BIP141) and which transaction malleability problem does it solve?"*
**Adversarial Target:** Equation-Heavy Context Trap

**Top 3 Retrieved Chunks:**
- **[1]** (Dist: 0.1586) | p. 3 | **3. Transactions**
  > 3. Transactions  A transaction has inputs (spends UTXOs) and outputs (creates new UTXOs). Scripting language enables conditions like P2PKH: OP_DUP OP_HASH160 OP_EQUALVERIFY OP_CHECKSIG. Sig Hash types...
- **[2]** (Dist: 0.2542) | p. 2 | **2. Blockchain Structure**
  > 2. Blockchain Structure  Each block contains a header with: Version number Previous block hash Merkle root of transactions Timestamp Difficulty target (bits) Nonce The chain links blocks via hash poin...
- **[3]** (Dist: 0.2726) | p. 4 | **License**
  > License  This document is released under Creative Commons Attribution 4.0 International (CC BY 4.0). You are free to share, adapt, and build upon it with attribution. Sources include Bitcoin Developer...

**Manual Relevance Grade:** [ Pass / Fail ]
**Failure Notes:** (Leave blank if passed)

---


## 2. Mechanisms & Processes

### Query 6: *"How does Bitcoin's difficulty adjustment algorithm recalculate the proof-of-work target every 2016 blocks?"*
**Adversarial Target:** Math Derivation Trap

**Top 3 Retrieved Chunks:**
- **[1]** (Dist: 0.1897) | p. 3 | **4. Consensus and Mining**
  > 4. Consensus and Mining  Proof-of-Work: Find nonce such that SHA256(SHA256(header)) < target. Difficulty adjusts every 2016 blocks to ~10 min intervals. Longest chain rule resolves forks.[web:21]...
- **[2]** (Dist: 0.1939) | p. 2 | **2. Blockchain Structure**
  > 2. Blockchain Structure  Each block contains a header with: Version number Previous block hash Merkle root of transactions Timestamp Difficulty target (bits) Nonce The chain links blocks via hash poin...
- **[3]** (Dist: 0.2609) | p. 2 | **1. Introduction**
  > 1. Introduction  Bitcoin is a decentralized digital currency that enables peer-to-peer transactions without intermediaries. Introduced in the 2008 whitepaper by Satoshi Nakamoto, it uses a proof-of-wo...

**Manual Relevance Grade:** [ Pass / Fail ]
**Failure Notes:** (Leave blank if passed)

---

### Query 7: *"Why does Bitcoin use a stack-based scripting language and what security properties does this design guarantee?"*
**Adversarial Target:** Historical Context Trap

**Top 3 Retrieved Chunks:**
- **[1]** (Dist: 0.2018) | p. 4 | **License**
  > License  This document is released under Creative Commons Attribution 4.0 International (CC BY 4.0). You are free to share, adapt, and build upon it with attribution. Sources include Bitcoin Developer...
- **[2]** (Dist: 0.2053) | p. 2 | **1. Introduction**
  > 1. Introduction  Bitcoin is a decentralized digital currency that enables peer-to-peer transactions without intermediaries. Introduced in the 2008 whitepaper by Satoshi Nakamoto, it uses a proof-of-wo...
- **[3]** (Dist: 0.2208) | p. 1 | **Bitcoin Technical Document**
  > Bitcoin Technical Document  A technical overview of Bitcoin protocol and architecture Released under Creative Commons Attribution 4.0 International (CC BY 4.0) Generated April 2026...

**Manual Relevance Grade:** [ Pass / Fail ]
**Failure Notes:** (Leave blank if passed)

---

### Query 8: *"How does the Bitcoin peer-to-peer network propagate new transactions using INV, GETDATA, and TX messages?"*
**Adversarial Target:** Chunk Character Limit Boundary

**Top 3 Retrieved Chunks:**
- **[1]** (Dist: 0.1605) | p. 3 | **5. Network Protocol**
  > 5. Network Protocol  P2P gossip protocol: VERSION, VERACK, INV, GETDATA, BLOCK, TX messages. Nodes maintain mempool for unconfirmed txs. BIP37 Bloom filters for SPV wallets.[web:26]...
- **[2]** (Dist: 0.1956) | p. 3 | **3. Transactions**
  > 3. Transactions  A transaction has inputs (spends UTXOs) and outputs (creates new UTXOs). Scripting language enables conditions like P2PKH: OP_DUP OP_HASH160 OP_EQUALVERIFY OP_CHECKSIG. Sig Hash types...
- **[3]** (Dist: 0.2004) | p. 2 | **1. Introduction**
  > 1. Introduction  Bitcoin is a decentralized digital currency that enables peer-to-peer transactions without intermediaries. Introduced in the 2008 whitepaper by Satoshi Nakamoto, it uses a proof-of-wo...

**Manual Relevance Grade:** [ Pass / Fail ]
**Failure Notes:** (Leave blank if passed)

---

### Query 9: *"What is the exact derivation path from a Bitcoin private key to a P2PKH address, including EC multiplication, SHA-256, RIPEMD-160, and Base58Check encoding?"*
**Adversarial Target:** Code Block Trap

**Top 3 Retrieved Chunks:**
- **[1]** (Dist: 0.2053) | p. 3 | **3. Transactions**
  > 3. Transactions  A transaction has inputs (spends UTXOs) and outputs (creates new UTXOs). Scripting language enables conditions like P2PKH: OP_DUP OP_HASH160 OP_EQUALVERIFY OP_CHECKSIG. Sig Hash types...
- **[2]** (Dist: 0.2292) | p. 3 | **4. Consensus and Mining**
  > 4. Consensus and Mining  Proof-of-Work: Find nonce such that SHA256(SHA256(header)) < target. Difficulty adjusts every 2016 blocks to ~10 min intervals. Longest chain rule resolves forks.[web:21]...
- **[3]** (Dist: 0.2310) | p. 4 | **License**
  > License  This document is released under Creative Commons Attribution 4.0 International (CC BY 4.0). You are free to share, adapt, and build upon it with attribution. Sources include Bitcoin Developer...

**Manual Relevance Grade:** [ Pass / Fail ]
**Failure Notes:** (Leave blank if passed)

---

### Query 10: *"How does Simplified Payment Verification (SPV) use Merkle proofs to verify transactions without downloading the full blockchain?"*
**Adversarial Target:** Pseudocode Trap

**Top 3 Retrieved Chunks:**
- **[1]** (Dist: 0.2402) | p. 2 | **2. Blockchain Structure**
  > 2. Blockchain Structure  Each block contains a header with: Version number Previous block hash Merkle root of transactions Timestamp Difficulty target (bits) Nonce The chain links blocks via hash poin...
- **[2]** (Dist: 0.2419) | p. 2 | **1. Introduction**
  > 1. Introduction  Bitcoin is a decentralized digital currency that enables peer-to-peer transactions without intermediaries. Introduced in the 2008 whitepaper by Satoshi Nakamoto, it uses a proof-of-wo...
- **[3]** (Dist: 0.2494) | p. 4 | **License**
  > License  This document is released under Creative Commons Attribution 4.0 International (CC BY 4.0). You are free to share, adapt, and build upon it with attribution. Sources include Bitcoin Developer...

**Manual Relevance Grade:** [ Pass / Fail ]
**Failure Notes:** (Leave blank if passed)

---


## 3. Relational Logic

### Query 11: *"What are the primary structural and security differences between Pay-to-Public-Key-Hash (P2PKH) and Pay-to-Script-Hash (P2SH) output types?"*
**Adversarial Target:** Isolated Code Block Trap

**Top 3 Retrieved Chunks:**
- **[1]** (Dist: 0.1994) | p. 3 | **3. Transactions**
  > 3. Transactions  A transaction has inputs (spends UTXOs) and outputs (creates new UTXOs). Scripting language enables conditions like P2PKH: OP_DUP OP_HASH160 OP_EQUALVERIFY OP_CHECKSIG. Sig Hash types...
- **[2]** (Dist: 0.2514) | p. 2 | **2. Blockchain Structure**
  > 2. Blockchain Structure  Each block contains a header with: Version number Previous block hash Merkle root of transactions Timestamp Difficulty target (bits) Nonce The chain links blocks via hash poin...
- **[3]** (Dist: 0.2585) | p. 2 | **1. Introduction**
  > 1. Introduction  Bitcoin is a decentralized digital currency that enables peer-to-peer transactions without intermediaries. Introduced in the 2008 whitepaper by Satoshi Nakamoto, it uses a proof-of-wo...

**Manual Relevance Grade:** [ Pass / Fail ]
**Failure Notes:** (Leave blank if passed)

---

### Query 12: *"Compare soft fork and hard fork upgrade mechanisms in Bitcoin in terms of backward compatibility and coordination requirements."*
**Adversarial Target:** Exercise Question Trap

**Top 3 Retrieved Chunks:**
- **[1]** (Dist: 0.1757) | p. 2 | **1. Introduction**
  > 1. Introduction  Bitcoin is a decentralized digital currency that enables peer-to-peer transactions without intermediaries. Introduced in the 2008 whitepaper by Satoshi Nakamoto, it uses a proof-of-wo...
- **[2]** (Dist: 0.1817) | p. 3 | **4. Consensus and Mining**
  > 4. Consensus and Mining  Proof-of-Work: Find nonce such that SHA256(SHA256(header)) < target. Difficulty adjusts every 2016 blocks to ~10 min intervals. Longest chain rule resolves forks.[web:21]...
- **[3]** (Dist: 0.1917) | p. 2 | **2. Blockchain Structure**
  > 2. Blockchain Structure  Each block contains a header with: Version number Previous block hash Merkle root of transactions Timestamp Difficulty target (bits) Nonce The chain links blocks via hash poin...

**Manual Relevance Grade:** [ Pass / Fail ]
**Failure Notes:** (Leave blank if passed)

---

### Query 13: *"How does an HTLC on the Lightning Network differ from a standard on-chain Bitcoin transaction in its locking and settlement mechanism?"*
**Adversarial Target:** Cross-Chapter Fragmentation

**Top 3 Retrieved Chunks:**
- **[1]** (Dist: 0.3349) | p. 4 | **License**
  > License  This document is released under Creative Commons Attribution 4.0 International (CC BY 4.0). You are free to share, adapt, and build upon it with attribution. Sources include Bitcoin Developer...
- **[2]** (Dist: 0.3353) | p. 2 | **1. Introduction**
  > 1. Introduction  Bitcoin is a decentralized digital currency that enables peer-to-peer transactions without intermediaries. Introduced in the 2008 whitepaper by Satoshi Nakamoto, it uses a proof-of-wo...
- **[3]** (Dist: 0.3507) | p. 2 | **2. Blockchain Structure**
  > 2. Blockchain Structure  Each block contains a header with: Version number Previous block hash Merkle root of transactions Timestamp Difficulty target (bits) Nonce The chain links blocks via hash poin...

**Manual Relevance Grade:** [ Pass / Fail ]
**Failure Notes:** (Leave blank if passed)

---

### Query 14: *"What are the specific differences between BIP32 hierarchical deterministic wallets and BIP44 multi-account wallet derivation?"*
**Adversarial Target:** Code Syntax Domination Trap

**Top 3 Retrieved Chunks:**
- **[1]** (Dist: 0.2660) | p. 3 | **3. Transactions**
  > 3. Transactions  A transaction has inputs (spends UTXOs) and outputs (creates new UTXOs). Scripting language enables conditions like P2PKH: OP_DUP OP_HASH160 OP_EQUALVERIFY OP_CHECKSIG. Sig Hash types...
- **[2]** (Dist: 0.2740) | p. 4 | **License**
  > License  This document is released under Creative Commons Attribution 4.0 International (CC BY 4.0). You are free to share, adapt, and build upon it with attribution. Sources include Bitcoin Developer...
- **[3]** (Dist: 0.2877) | p. 2 | **2. Blockchain Structure**
  > 2. Blockchain Structure  Each block contains a header with: Version number Previous block hash Merkle root of transactions Timestamp Difficulty target (bits) Nonce The chain links blocks via hash poin...

**Manual Relevance Grade:** [ Pass / Fail ]
**Failure Notes:** (Leave blank if passed)

---

### Query 15: *"Compare the security guarantees and trust assumptions of a Bitcoin full node versus an SPV light client in a hostile network environment."*
**Adversarial Target:** Generic Acronym Density Trap

**Top 3 Retrieved Chunks:**
- **[1]** (Dist: 0.2235) | p. 4 | **License**
  > License  This document is released under Creative Commons Attribution 4.0 International (CC BY 4.0). You are free to share, adapt, and build upon it with attribution. Sources include Bitcoin Developer...
- **[2]** (Dist: 0.2253) | p. 2 | **1. Introduction**
  > 1. Introduction  Bitcoin is a decentralized digital currency that enables peer-to-peer transactions without intermediaries. Introduced in the 2008 whitepaper by Satoshi Nakamoto, it uses a proof-of-wo...
- **[3]** (Dist: 0.2294) | p. 3 | **5. Network Protocol**
  > 5. Network Protocol  P2P gossip protocol: VERSION, VERACK, INV, GETDATA, BLOCK, TX messages. Nodes maintain mempool for unconfirmed txs. BIP37 Bloom filters for SPV wallets.[web:26]...

**Manual Relevance Grade:** [ Pass / Fail ]
**Failure Notes:** (Leave blank if passed)

---


## 4. Adversarial Stress Tests

### Query 16: *"What is the exact mathematical formula for Bitcoin's difficulty target T given the ratio of actual to expected time for the last 2016 blocks?"*
**Adversarial Target:** Pure LaTeX/Unicode Trap

**Top 3 Retrieved Chunks:**
- **[1]** (Dist: 0.1653) | p. 2 | **2. Blockchain Structure**
  > 2. Blockchain Structure  Each block contains a header with: Version number Previous block hash Merkle root of transactions Timestamp Difficulty target (bits) Nonce The chain links blocks via hash poin...
- **[2]** (Dist: 0.2108) | p. 3 | **4. Consensus and Mining**
  > 4. Consensus and Mining  Proof-of-Work: Find nonce such that SHA256(SHA256(header)) < target. Difficulty adjusts every 2016 blocks to ~10 min intervals. Longest chain rule resolves forks.[web:21]...
- **[3]** (Dist: 0.2667) | p. 4 | **License**
  > License  This document is released under Creative Commons Attribution 4.0 International (CC BY 4.0). You are free to share, adapt, and build upon it with attribution. Sources include Bitcoin Developer...

**Manual Relevance Grade:** [ Pass / Fail ]
**Failure Notes:** (Leave blank if passed)

---

### Query 17: *"Design a 2-of-3 multisig P2SH locking script and detail each opcode (OP_2, OP_CHECKMULTISIG) together with the corresponding unlocking script."*
**Adversarial Target:** Verbatim Textbook Exercise Trap

**Top 3 Retrieved Chunks:**
- **[1]** (Dist: 0.2328) | p. 3 | **3. Transactions**
  > 3. Transactions  A transaction has inputs (spends UTXOs) and outputs (creates new UTXOs). Scripting language enables conditions like P2PKH: OP_DUP OP_HASH160 OP_EQUALVERIFY OP_CHECKSIG. Sig Hash types...
- **[2]** (Dist: 0.2784) | p. 4 | **License**
  > License  This document is released under Creative Commons Attribution 4.0 International (CC BY 4.0). You are free to share, adapt, and build upon it with attribution. Sources include Bitcoin Developer...
- **[3]** (Dist: 0.2845) | p. 2 | **2. Blockchain Structure**
  > 2. Blockchain Structure  Each block contains a header with: Version number Previous block hash Merkle root of transactions Timestamp Difficulty target (bits) Nonce The chain links blocks via hash poin...

**Manual Relevance Grade:** [ Pass / Fail ]
**Failure Notes:** (Leave blank if passed)

---

### Query 18: *"Provide a summary of the introduction to Bitcoin, including its peer-to-peer architecture, the role of cryptographic proof, and the mechanism for preventing double-spending."*
**Adversarial Target:** Massive ToC Sequence Trap

**Top 3 Retrieved Chunks:**
- **[1]** (Dist: 0.1003) | p. 2 | **1. Introduction**
  > 1. Introduction  Bitcoin is a decentralized digital currency that enables peer-to-peer transactions without intermediaries. Introduced in the 2008 whitepaper by Satoshi Nakamoto, it uses a proof-of-wo...
- **[2]** (Dist: 0.1500) | p. 1 | **Bitcoin Technical Document**
  > Bitcoin Technical Document  A technical overview of Bitcoin protocol and architecture Released under Creative Commons Attribution 4.0 International (CC BY 4.0) Generated April 2026...
- **[3]** (Dist: 0.1705) | p. 4 | **License**
  > License  This document is released under Creative Commons Attribution 4.0 International (CC BY 4.0). You are free to share, adapt, and build upon it with attribution. Sources include Bitcoin Developer...

**Manual Relevance Grade:** [ Pass / Fail ]
**Failure Notes:** (Leave blank if passed)

---

### Query 19: *"Show the specific Python code using the 'ecdsa' or 'bitcoinlib' library for generating a Bitcoin private key and deriving the corresponding P2PKH address."*
**Adversarial Target:** Framework Action Block Trap

**Top 3 Retrieved Chunks:**
- **[1]** (Dist: 0.2524) | p. 3 | **3. Transactions**
  > 3. Transactions  A transaction has inputs (spends UTXOs) and outputs (creates new UTXOs). Scripting language enables conditions like P2PKH: OP_DUP OP_HASH160 OP_EQUALVERIFY OP_CHECKSIG. Sig Hash types...
- **[2]** (Dist: 0.2638) | p. 4 | **License**
  > License  This document is released under Creative Commons Attribution 4.0 International (CC BY 4.0). You are free to share, adapt, and build upon it with attribution. Sources include Bitcoin Developer...
- **[3]** (Dist: 0.2640) | p. 2 | **1. Introduction**
  > 1. Introduction  Bitcoin is a decentralized digital currency that enables peer-to-peer transactions without intermediaries. Introduced in the 2008 whitepaper by Satoshi Nakamoto, it uses a proof-of-wo...

**Manual Relevance Grade:** [ Pass / Fail ]
**Failure Notes:** (Leave blank if passed)

---

### Query 20: *"Explain the symptoms of sel昀椀sh mining compared to honest mining and how the attacker gains a disproportionate share of block rewards."*
**Adversarial Target:** PDF Ligature Corruption Typo Trap

**Top 3 Retrieved Chunks:**
- **[1]** (Dist: 0.1775) | p. 2 | **2. Blockchain Structure**
  > 2. Blockchain Structure  Each block contains a header with: Version number Previous block hash Merkle root of transactions Timestamp Difficulty target (bits) Nonce The chain links blocks via hash poin...
- **[2]** (Dist: 0.2122) | p. 2 | **1. Introduction**
  > 1. Introduction  Bitcoin is a decentralized digital currency that enables peer-to-peer transactions without intermediaries. Introduced in the 2008 whitepaper by Satoshi Nakamoto, it uses a proof-of-wo...
- **[3]** (Dist: 0.2149) | p. 3 | **4. Consensus and Mining**
  > 4. Consensus and Mining  Proof-of-Work: Find nonce such that SHA256(SHA256(header)) < target. Difficulty adjusts every 2016 blocks to ~10 min intervals. Longest chain rule resolves forks.[web:21]...

**Manual Relevance Grade:** [ Pass / Fail ]
**Failure Notes:** (Leave blank if passed)

---
