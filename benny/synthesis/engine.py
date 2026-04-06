"""
Synthesis Engine - LLM-powered triple extraction, embedding, and structural synthesis.

This module contains the three "Logic Layers":
  A. Relational Graph (NER + Relation Extraction → triples)
  B. Conceptual Cluster (Dual-model embedding → Venn clustering)
  C. Synthesis Layer (Structural Isomorphism detection)
"""

import json
import os
from typing import List, Dict, Any, Optional, Tuple
import httpx

from ..core.models import LOCAL_PROVIDERS


# =============================================================================
# A. RELATIONAL GRAPH — Triple Extraction via LLM
# =============================================================================

TRIPLE_EXTRACTION_PROMPT = """You are a knowledge graph extraction engine.
Given the following text, extract ALL meaningful knowledge triples in the form:
  (Subject, Predicate, Object)

Rules:
- Subject and Object should be concise noun phrases (concepts, entities, processes).
- Predicate should be a verb phrase describing the relationship.
- Extract as many triples as you can find.  Be thorough.
- If the text mentions a source document name, include triples that reference it.

Return ONLY a JSON array of objects, like:
[
  {{
    "subject": "Dopamine",
    "subject_type": "Biology",
    "predicate": "drives",
    "object": "reward-seeking behavior",
    "object_type": "Concept",
    "citation": "Dopamine is responsible for...",
    "confidence": 0.95
  }}
]

TEXT:
{text}

JSON TRIPLES:"""


DIRECTED_EXTRACTION_PROMPT = """You are an L2 expert reading a specific section of a document.
Your goal is to extract the core points, arguments, or mechanisms made in this section.

{direction_prompt}

Rules for Extraction:
1. Extract the points strictly as Knowledge Graph relations map.
2. Filter out any noise; only extract points structurally relevant to the direction (if provided).
3. "subject_type" and "object_type" should categorize the entity (e.g., Person, Theory, Technology, Organization, Location, Event, Concept).
4. "citation" must be the exact short sentence/excerpt from the text that justifies the claim.
5. "confidence" should be a score from 0.0 to 1.0 (1.0 = proven/stated as fact, 0.5 = hypothesized).

TEXT SECTION: {section_title}
{text}

Output ONLY a JSON array of objects. Example format:
[
  {{
    "subject": "Dopamine",
    "subject_type": "Biology",
    "predicate": "drives",
    "object": "Reward-Seeking Behavior",
    "object_type": "Concept",
    "citation": "Dopamine is responsible for the reward-seeking loop in mammalian brains.",
    "confidence": 0.9
  }}
]

JSON:"""


CONFLICT_DETECTION_PROMPT = """You are a logical consistency checker.
Given the following set of knowledge triples already in the graph, and a NEW set of triples about to be added, identify any CONFLICTS (contradictions) between the existing and new triples.

A conflict exists when:
- Two triples make opposing claims about the same subject-object pair
- A new triple directly contradicts an existing one

EXISTING TRIPLES:
{existing}

NEW TRIPLES:
{new_triples}

Return a JSON array of conflict objects. If no conflicts, return [].
Each conflict object should have:
  "concept_a": the first concept involved,
  "concept_b": the second concept involved,
  "description": a brief explanation of the contradiction

JSON CONFLICTS:"""


SYNTHESIS_PROMPT = """You are a cross-domain synthesis engine that finds structural isomorphisms —
patterns that repeat across different fields.

Given the following set of concepts and their relationships, identify any
STRUCTURAL ANALOGIES (isomorphisms) between concepts from different domains.

An analogy exists when:
- Two systems from different fields share the same underlying pattern or structure
- The way one system works is mathematically or structurally similar to another
- E.g. how a forest fire spreads (Biology) is similar to how a viral tweet spreads (Sociology)

KNOWLEDGE GRAPH:
{graph_summary}

Return a JSON array of analogy objects. If no analogies found, return [].
Each analogy object should have:
  "concept_a": first concept,
  "concept_b": second concept,
  "description": explanation of the analogy,
  "pattern": the shared abstract pattern name (e.g. "Resilience through Redundancy")

JSON ANALOGIES:"""


CROSS_DOMAIN_PROMPT = """You are a cross-domain analogy engine.
Given the concept "{concept}" and its relationships below, explain how this concept
maps to the domain of "{target_domain}".

CONCEPT RELATIONSHIPS:
{relationships}

Provide:
1. The analogous concept in {target_domain}
2. How the structural pattern maps
3. Key similarities and differences

Be specific and insightful. Format as JSON:
{{
  "analogous_concept": "...",
  "mapping": "...",
  "similarities": ["..."],
  "differences": ["..."]
}}

JSON:"""


async def call_llm(prompt: str, provider: str = "lemonade", model: str = None) -> str:
    """Call a local or cloud LLM with a prompt and return the raw text response."""
    provider_config = LOCAL_PROVIDERS.get(provider, LOCAL_PROVIDERS.get("lemonade"))
    if not provider_config:
        raise ValueError(f"Unknown LLM provider: {provider}")

    api_base = provider_config["base_url"]
    chat_url = f"{api_base}/chat/completions"
    
    # Model name resolution aligned with frontend expectations
    if model and model != "default":
        model_name = model.split("/")[-1]
    else:
        if provider == "ollama":
            model_name = "llama3"
        elif provider == "lemonade":
            model_name = "DeepSeek-R1-Distill-Llama-8B-FLM"
        elif provider == "fastflowlm":
            model_name = "gemma3:4b"
        elif provider == "lmstudio":
            # If no model provided, we'll try to use the first one from status later 
            # Or use a generic fallback. For LM Studio, it's safer to use the selected one.
            model_name = model or "default"
        else:
            model_name = "default"


    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3  # Low temp for structured extraction
    }

    async with httpx.AsyncClient(timeout=300.0) as client:
        response = await client.post(
            chat_url,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        if response.status_code == 200:
            data = response.json()
            return data["choices"][0]["message"]["content"]
        else:
            raise Exception(f"LLM call failed ({response.status_code}): {response.text}")


def _parse_json_from_llm(text: str) -> Any:
    """Robustly extract JSON from LLM output that may contain markdown fences."""
    text = text.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try to find a JSON array or object in the text
    for start_char, end_char in [("[", "]"), ("{", "}")]:
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    
    return []


async def extract_triples(
    text: str,
    source_name: str = "",
    provider: str = "lemonade",
    model: str = None
) -> List[List[str]]:
    """
    Extract knowledge triples from text using the configured LLM.
    
    Returns list of [subject, predicate, object] triples.
    """
    # Truncate very long texts to avoid context window overflow
    safe_text = text[:6000]
    prompt = TRIPLE_EXTRACTION_PROMPT.format(text=safe_text)
    
    raw = await call_llm(prompt, provider=provider, model=model)
    triples = _parse_json_from_llm(raw)
    
    if not isinstance(triples, list):
        return []
    
    # Validate each triple is a dict with required fields
    valid = []
    for t in triples:
        if isinstance(t, dict) and "subject" in t and "predicate" in t and "object" in t:
            valid.append(t)
    
    return valid


async def extract_directed_triples_from_section(
    text: str,
    section_title: str,
    direction: str = "",
    provider: str = "lemonade",
    model: str = None,
    inference_delay: float = 2.0
) -> List[List[str]]:
    """
    Extract L2 points from a document section, optionally influenced by user direction.
    """
    import asyncio
    
    # Optional delay to protect local NPU/CPU from thermal throttling
    if inference_delay > 0:
        await asyncio.sleep(inference_delay)
        
    safe_text = text[:8000]
    
    dir_prompt = ""
    if direction.strip():
        dir_prompt = f"DIRECTION / INTENT:\nThe user is specifically looking for: '{direction}'. Focus heavily on points that help answer this intent."
        
    prompt = DIRECTED_EXTRACTION_PROMPT.format(
        direction_prompt=dir_prompt,
        section_title=section_title,
        text=safe_text
    )
    
    raw = await call_llm(prompt, provider=provider, model=model)
    triples = _parse_json_from_llm(raw)
    
    if not isinstance(triples, list):
        return []
    
    valid = []
    for t in triples:
        if isinstance(t, dict) and "subject" in t and "predicate" in t and "object" in t:
            valid.append(t)
    
    return valid


async def detect_conflicts(
    existing_triples: List[List[str]],
    new_triples: List[List[str]],
    provider: str = "lemonade",
    model: str = None
) -> List[Dict[str, str]]:
    """Detect logical conflicts between existing and new triples."""
    if not existing_triples or not new_triples:
        return []
    
    # Limit array sizes to prevent context window bloat and timeout errors
    prompt = CONFLICT_DETECTION_PROMPT.format(
        existing=json.dumps(existing_triples[:30]),
        new_triples=json.dumps(new_triples[:30])
    )
    
    try:
        raw = await call_llm(prompt, provider=provider, model=model)
        conflicts = _parse_json_from_llm(raw)
        
        if not isinstance(conflicts, list):
            return []
        
        return [c for c in conflicts if isinstance(c, dict) and "concept_a" in c]
    except Exception as e:
        print(f"⚠️ Conflict detection bypassed: LLM call failed ({e})")
        return []


async def find_synthesis(
    graph_summary: str,
    provider: str = "lemonade",
    model: str = None
) -> List[Dict[str, str]]:
    """Find structural isomorphisms in the knowledge graph."""
    prompt = SYNTHESIS_PROMPT.format(graph_summary=graph_summary)
    
    raw = await call_llm(prompt, provider=provider, model=model)
    analogies = _parse_json_from_llm(raw)
    
    if not isinstance(analogies, list):
        return []
    
    return [a for a in analogies if isinstance(a, dict) and "concept_a" in a]


async def cross_domain_analogy(
    concept: str,
    relationships: str,
    target_domain: str,
    provider: str = "lemonade",
    model: str = None
) -> Dict[str, Any]:
    """Map a concept into a different domain."""
    prompt = CROSS_DOMAIN_PROMPT.format(
        concept=concept,
        relationships=relationships,
        target_domain=target_domain
    )
    
    raw = await call_llm(prompt, provider=provider, model=model)
    result = _parse_json_from_llm(raw)
    
    if isinstance(result, dict):
        return result
    return {"error": "Could not generate cross-domain analogy", "raw": raw}


# =============================================================================
# B. CONCEPTUAL CLUSTER — Dual-Model Embedding
# =============================================================================

async def get_embedding(text: str, provider: str = "local", model: str = None) -> List[float]:
    """
    Get a vector embedding for text using either a local or cloud provider.
    
    Providers:
        - "local" / "ollama": Uses ollama's embedding endpoint
        - "openai": Uses OpenAI text-embedding-3-small
    """
    if provider == "openai":
        return await _get_openai_embedding(text, model or "text-embedding-3-small")
    elif provider == "ollama" or provider == "local":
        return await _get_ollama_embedding(text, model or "nomic-embed-text")
    else:
        # For 'lemonade', 'fastflowlm', or other OpenAI-compatible local endpoints
        return await _get_generic_local_embedding(text, provider, model)

async def _get_generic_local_embedding(text: str, provider: str, model: str = None) -> List[float]:
    """Get embedding from an OpenAI-compatible local AI endpoint (e.g. Lemonade)."""
    provider_config = LOCAL_PROVIDERS.get(provider)
    if not provider_config:
        raise ValueError(f"Unknown local provider for embedding: {provider}")
    
    api_base = provider_config["base_url"] 
    # Usually OpenAI compat ends with /v1, so we add /embeddings
    url = f"{api_base}/embeddings"
    
    model_name = model.split("/")[-1] if model else "default"
    
    # FastFlowLM and Lemonade throw errors if a Chat model is passed to the Embeddings endpoint.
    if provider == "lemonade" and model_name == "default":
        model_name = "nomic-embed-text-v1-GGUF"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json={"model": model_name, "input": text})
        if response.status_code == 200:
            data = response.json()
            return data["data"][0]["embedding"]
        else:
            raise Exception(f"{provider} embedding failed: {response.status_code} {response.text}")


async def _get_ollama_embedding(text: str, model: str = "nomic-embed-text") -> List[float]:
    """Get embedding from Ollama /api/embeddings endpoint."""
    url = "http://localhost:11434/api/embeddings"
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, json={"model": model, "prompt": text})
        if response.status_code == 200:
            data = response.json()
            return data.get("embedding", [])
        else:
            raise Exception(f"Ollama embedding failed: {response.status_code}")


async def _get_openai_embedding(text: str, model: str = "text-embedding-3-small") -> List[float]:
    """Get embedding from OpenAI API."""
    import openai
    client_obj = openai.AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    response = await client_obj.embeddings.create(input=text, model=model)
    return response.data[0].embedding


async def compute_cluster_similarities(
    concepts: List[str],
    workspace: str = "default",
    threshold: float = 0.75
) -> List[Dict[str, Any]]:
    """
    Compute pairwise similarities for a list of concepts using their stored embeddings.
    Returns pairs above the threshold — this powers the "Venn" clustering.
    """
    from ..core.graph_db import vector_search, get_driver
    from math import sqrt
    
    driver = get_driver()
    embeddings = {}
    
    with driver.session() as session:
        for concept in concepts:
            result = session.run("""
                MATCH (c:Concept {name: $name, workspace: $workspace})
                RETURN c.embedding AS embedding
            """, name=concept, workspace=workspace)
            record = result.single()
            if record and record["embedding"]:
                embeddings[concept] = record["embedding"]
    
    # Pairwise cosine similarity
    def cosine_sim(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = sqrt(sum(x * x for x in a))
        nb = sqrt(sum(x * x for x in b))
        return dot / (na * nb) if (na and nb) else 0.0
    
    clusters = []
    concept_list = list(embeddings.keys())
    for i in range(len(concept_list)):
        for j in range(i + 1, len(concept_list)):
            sim = cosine_sim(embeddings[concept_list[i]], embeddings[concept_list[j]])
            if sim >= threshold:
                clusters.append({
                    "concept_a": concept_list[i],
                    "concept_b": concept_list[j],
                    "similarity": round(sim, 4)
                })
    
    clusters.sort(key=lambda x: x["similarity"], reverse=True)
    return clusters
