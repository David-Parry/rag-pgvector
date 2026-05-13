# Vector Search Indexing in pgvector  

## Why This Matters

In AI systems using embeddings, vector search becomes the foundation for:

- RAG (Retrieval Augmented Generation)
- Semantic search
- Agent memory
- Recommendation systems
- Code search
- Context retrieval

Without indexing, every query performs a full scan:

```text
Compare query vector against every vector in the database
```

At scale, this becomes computationally expensive and introduces latency.

Approximate Nearest Neighbor (ANN) indexes solve this problem.

In PostgreSQL with pgvector, the two primary ANN index types are:

- IVFFlat
- HNSW

---

# Exact Search vs Approximate Search

## Exact Search

```sql
SELECT *
FROM documents
ORDER BY embedding <=> '[...]'
LIMIT 5;
```

Behavior:

- Scans all vectors
- Highest accuracy
- Slow at scale

Complexity:

```text
O(n)
```

Out of the box, pgvector runs this query with no index — a sequential scan.
Fine for ~10k–100k rows, painful beyond that.

---

## Understanding k (the LIMIT)

The `LIMIT 5` above is the `k` in k-Nearest Neighbors.

```text
ORDER BY embedding <=> query   → rank every row by distance
LIMIT k                        → keep only the k closest
```

In RAG pipelines, `k` is typically 3–10:

- Too low → relevant context is missed, the LLM hallucinates
- Too high → context window bloats, irrelevant chunks dilute the prompt, latency rises

`k` is independent of the index type. IVFFlat and HNSW only change *how fast*
and *how accurately* the top-k is found.

---

## Approximate Nearest Neighbor (ANN)

Behavior:

- Searches intelligently
- Trades tiny accuracy loss for massive performance gains
- Used in production AI systems

---

# Distance Operators in pgvector

pgvector ships three distance operators, each with a matching index operator
class. The class must match the operator used at query time, otherwise the
index is ignored and Postgres falls back to a sequential scan.

| Operator | Meaning                       | Operator class       | Typical use                          |
|----------|-------------------------------|----------------------|--------------------------------------|
| `<->`    | Euclidean (L2) distance       | `vector_l2_ops`      | Geometric similarity                 |
| `<#>`    | Negative inner product        | `vector_ip_ops`      | Pre-normalized vectors, fastest math |
| `<=>`    | Cosine distance (`1 - cos θ`) | `vector_cosine_ops`  | Text/semantic embeddings (RAG)       |

## Cosine in depth

### The formula

Cosine similarity measures the angle between two vectors:

```text
              A · B
cos(θ) = ─────────────────
          ‖A‖ × ‖B‖
```

- `A · B` — dot product (sum of element-wise products)
- `‖A‖`   — Euclidean length (magnitude) of `A`
- `‖B‖`   — Euclidean length of `B`

Dividing by the magnitudes cancels them out. Only the direction matters.

### Similarity vs distance

| Metric              | Range        | Meaning                              |
|---------------------|--------------|--------------------------------------|
| Cosine similarity   | `-1 … +1`    | `+1` identical, `0` unrelated, `-1` opposite |
| Cosine distance     | `0 … 2`      | `0` identical, `1` orthogonal, `2` opposite  |

pgvector's `<=>` returns **cosine distance**:

```text
cosine_distance = 1 - cos(θ)
```

Smaller is closer — which is why queries use `ORDER BY embedding <=> query ASC`.

### Why it suits embeddings

Embedding models (OpenAI, sentence-transformers, etc.) encode:

```text
direction = meaning
magnitude = noise (length, token count, formatting, etc.)
```

A short headline and a long article on the same topic will have similar
direction but very different magnitudes. Cosine ignores magnitude, so they
land near each other in the vector space.

### Worked example: magnitude doesn't matter

```text
A = [1, 0]
B = [3, 0]    ← same direction, 3× the magnitude
C = [0, 1]    ← orthogonal direction

cos(A, B) = (1·3 + 0·0) / (1 × 3)     = 1.0   → identical meaning
cos(A, C) = (1·0 + 0·1) / (1 × 1)     = 0.0   → unrelated

distance(A, B) = 1 - 1.0 = 0.0
distance(A, C) = 1 - 0.0 = 1.0
```

Euclidean (L2) distance would call `A` and `B` *far apart* (distance = 2),
even though they mean the same thing. Cosine correctly calls them identical.

### Performance shortcut: normalized vectors

If every vector is unit-length (`‖v‖ = 1`), then:

```text
cos(A, B) = A · B
```

Cosine similarity collapses into a plain dot product — no division needed.
That's why some pipelines pre-normalize embeddings and use the inner-product
operator (`<#>` with `vector_ip_ops`) for a small speed win. It's
mathematically equivalent to cosine in that case.

### What `vector_cosine_ops` actually is

In the index definition:

```sql
CREATE INDEX ON documents
  USING ivfflat (embedding vector_cosine_ops);
              ── ── ─────── ────────────────
                 │       │              │
                 │       │              └── operator class (the metric)
                 │       └── column being indexed
                 └── access method (ivfflat or hnsw)
```

The operator class is the second argument and tells the index *which distance
function to organize itself around*. `vector_cosine_ops` means "build the
clusters / graph so that cosine-distance lookups are fast." The other choices
are `vector_l2_ops` and `vector_ip_ops`.

## Operator must match operator class

```sql
-- index built for cosine
CREATE INDEX ON documents
  USING hnsw (embedding vector_cosine_ops);

-- query using cosine → uses the index
SELECT * FROM documents ORDER BY embedding <=> '[...]' LIMIT 5;

-- query using L2 → ignores the index, sequential scan
SELECT * FROM documents ORDER BY embedding <-> '[...]' LIMIT 5;
```

---

# IVFFlat

## Concept

IVFFlat works by clustering vectors into groups.

Instead of searching the entire dataset:

```text
Search only the most relevant clusters
```

---

# IVFFlat Architecture

## Step 1: Clustering

Vectors are grouped into buckets called lists.

Example:

```text
10 million vectors
→ grouped into 1000 clusters
```

Each cluster has a centroid representing its semantic center.

---

## Step 2: Query Search

At query time:

1. Find closest cluster centroids
2. Search only those clusters
3. Return nearest vectors

---

# IVFFlat Visualization

```text
Entire Dataset
┌────────────────────┐
│ Cluster 1          │
│ Cluster 2          │
│ Cluster 3          │
│ Cluster 4          │
└────────────────────┘

Query
   ↓

Find nearest clusters
   ↓

Search only those clusters
```

---

# IVFFlat Example

```sql
CREATE INDEX idx_docs_embedding
ON documents
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
```

---

# IVFFlat Parameters

## lists

Controls number of clusters.

Higher values:
- Better recall
- Slower indexing
- More memory

Lower values:
- Faster
- Less accurate

Typical guidance:

```text
lists ≈ sqrt(number_of_rows)
```

---

## probes

Controls how many clusters are searched during queries.

Example:

```sql
SET ivfflat.probes = 10;
```

Higher probes:
- Better accuracy
- Slower queries

Lower probes:
- Faster
- Lower recall

---

# IVFFlat Strengths

| Strength | Details |
|---|---|
| Lower memory usage | Smaller index footprint |
| Faster index builds | Simpler clustering |
| Simpler operational model | Easier to tune |
| Good for static datasets | Stable embeddings |

---

# IVFFlat Weaknesses

| Weakness | Details |
|---|---|
| Lower recall | Can miss nearest neighbors |
| Requires training | Clustering phase required |
| Sensitive tuning | lists/probes matter significantly |
| Dynamic inserts degrade quality | Cluster distribution can drift |

---

# HNSW

## Concept

HNSW is graph-based vector indexing.

Instead of clusters:

```text
Vectors become nodes connected to nearby vectors
```

Search traverses the graph to find nearest neighbors efficiently.

---

# HNSW Architecture

Each vector connects to semantically nearby vectors.

Query execution:

```text
Start at a node
→ hop toward closer nodes
→ continue until convergence
```

This behaves similarly to navigating a map.

---

# HNSW Visualization

```text
Node A ── Node B ── Node C
   │         │
Node D ── Node E
```

Search traverses the graph toward the closest semantic region.

---

# Hierarchical Layers

HNSW uses multiple graph layers.

```text
Top Layer      → coarse navigation
Middle Layer   → regional refinement
Bottom Layer   → detailed nearest neighbors
```

Search flow:

1. Start high-level
2. Narrow semantic region
3. Descend into detailed search

This produces very fast retrieval times.

---

# HNSW Example

```sql
CREATE INDEX idx_docs_embedding
ON documents
USING hnsw (embedding vector_cosine_ops);
```

---

# HNSW Parameters

## m

Controls graph connectivity.

Higher values:
- Better recall
- Larger indexes
- Slower builds

---

## ef_construction

Controls build-time search depth.

Higher values:
- Better graph quality
- Slower indexing

---

## ef_search

Controls query-time exploration depth.

```sql
SET hnsw.ef_search = 100;
```

Higher values:
- Better recall
- Slower queries

---

# HNSW Strengths

| Strength | Details |
|---|---|
| Excellent recall | Often near exact search quality |
| Extremely fast queries | Efficient graph traversal |
| Better dynamic inserts | Graph adapts over time |
| Strong enterprise scalability | Millions to billions of vectors |

---

# HNSW Weaknesses

| Weakness | Details |
|---|---|
| Higher memory usage | Graph structure overhead |
| Slower index creation | More expensive build process |
| More tuning complexity | More operational parameters |
| RAM intensive | Large deployments require planning |

---

# IVFFlat vs HNSW

| Capability | IVFFlat | HNSW |
|---|---|---|
| Data Structure | Clusters | Graph |
| Query Speed | Good | Excellent |
| Recall Accuracy | Moderate | Very High |
| Build Speed | Faster | Slower |
| Memory Usage | Lower | Higher |
| Dynamic Updates | Weaker | Better |
| Complexity | Simpler | More Advanced |
| Production Scale | Moderate | Enterprise Grade |

---

# Enterprise Recommendations

## Use IVFFlat When

- Smaller deployments
- Limited infrastructure
- Lower memory budgets
- Mostly static datasets
- Simpler operational needs

Typical use cases:
- Internal documentation search
- Small RAG systems
- Proof of concepts

---

## Use HNSW When

- Enterprise-scale AI systems
- High recall requirements
- Low latency requirements
- Large embedding datasets
- Agentic workflows
- Production semantic search

Typical use cases:
- AI copilots
- Enterprise search
- Code intelligence
- Agent memory systems
- Recommendation platforms

---

# Important Engineering Reality

Vector search quality directly impacts LLM quality.

Poor retrieval leads to:
- hallucinations
- irrelevant context
- incorrect grounding
- noisy prompts
- operational instability

ANN indexes improve speed, but production systems still require:

- metadata filtering
- reranking
- chunk quality control
- governance layers
- deterministic constraints
- observability

Example:

```sql
SELECT *
FROM documents
WHERE repo = 'payments-service'
ORDER BY embedding <=> '[...]'
LIMIT 5;
```

Filtering before vector search often matters as much as the ANN index itself.

---

# What pgvector Gives You Out of the Box

A reference summary of capabilities shipped with the extension itself.

## Vector types

| Type          | Description                       | Typical use                         |
|---------------|-----------------------------------|-------------------------------------|
| `vector(N)`   | Float32 dense vector              | Default workhorse                   |
| `halfvec(N)`  | Float16 dense vector              | ~½ storage/RAM, tiny recall hit     |
| `sparsevec(N)`| Sparse vector                     | BM25-style, hybrid search           |
| `bit(N)`      | Binary vector with Hamming distance | Compact, very fast                |

## Distance operators

Three operators (`<->`, `<#>`, `<=>`) with matching operator classes.
See the *Distance Operators in pgvector* section above.

## Index types

| Index     | Build requirement                 | Dynamic inserts            |
|-----------|-----------------------------------|----------------------------|
| `ivfflat` | Needs data inserted before build  | Quality drifts over time   |
| `hnsw`    | Can be built on an empty table    | Graph adapts as rows arrive|

## Dimension limits

| Column kind         | `vector` max | `halfvec` max |
|---------------------|--------------|---------------|
| Indexed             | 2,000        | 4,000         |
| Unindexed           | 16,000       | 16,000        |

This is why teams sometimes downsize 3,072-dim embeddings to 1,536 — to
stay within the indexable range.

## Runtime tunables

Set per session, no rebuild required.

```sql
SET ivfflat.probes = 10;
SET hnsw.ef_search = 100;
```

Useful for swapping between fast-default and high-precision query modes
without touching the index.

## HNSW defaults shipped by pgvector

```text
m              = 16
ef_construction = 64
ef_search       = 40
```

Conservative but reasonable. Most teams only tune `ef_search` upward
(60–200) when recall isn't good enough.

## Filtering + ANN

Pre-filtering combines a B-tree/GIN predicate with the vector index:

```sql
SELECT *
FROM documents
WHERE repo = 'payments-service'
ORDER BY embedding <=> '[...]'
LIMIT 5;
```

Caveats:

- Highly selective filters may cause the planner to abandon the ANN index
  and exact-scan the filtered subset (sometimes faster, sometimes a recall trap).
- Hoisting frequently-filtered metadata into typed columns (instead of
  leaving it inside JSONB) avoids per-row JSON extraction at query time.
