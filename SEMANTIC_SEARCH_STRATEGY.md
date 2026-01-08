# Semantic Search Strategy for Document Generation

## Overview

This document explains the semantic search approach used for generating clinical documents from therapy session transcripts, along with the enhancements made to mitigate risks of missing important context.

## The Challenge

When generating documents from large transcripts (potentially hours of therapy sessions), we face two competing constraints:

1. **Context Window Limits**: LLMs have token limits (e.g., GPT-4o has ~128K context window)
2. **Completeness**: We need enough context to generate accurate, comprehensive documents

Using ALL transcript content often exceeds context limits. Using too little risks missing critical information.

## Our Solution: Intelligent Semantic Search with Safeguards

### Core Approach

1. **Template Analysis**: Analyze the document template to understand what information is needed
2. **Targeted Queries**: Generate 10-20 semantic search queries based on template structure
3. **Adaptive Retrieval**: Fetch relevant segments with smart threshold adjustment
4. **Temporal Context**: Add surrounding segments to high-relevance matches
5. **Fallback Strategy**: If semantic search fails, retrieve ALL segments

### Configuration

The system is configured via `SEMANTIC_SEARCH_CONFIG` in `main.py`:

```python
SEMANTIC_SEARCH_CONFIG = {
    # Base similarity threshold (will be relaxed if results are sparse)
    "base_similarity_threshold": 0.5,
    
    # Minimum similarity threshold (won't go below this)
    "min_similarity_threshold": 0.2,
    
    # Threshold reduction per retry attempt
    "threshold_reduction_step": 0.15,
    
    # Temporal context window (segments before/after high-relevance matches)
    "temporal_context_window": 2,
    
    # Minimum relevance score to fetch temporal context (0.0-1.0)
    "min_relevance_for_context": 0.6,
    
    # Maximum retry attempts when relaxing threshold
    "max_threshold_attempts": 3,
    
    # Minimum expected results as fraction of requested (e.g., 0.33 = expect at least 1/3)
    "min_result_fraction": 0.33
}
```

## Risk Mitigation Strategies

### 1. **Adaptive Similarity Thresholds**

**Problem**: A fixed threshold (e.g., 0.5) might be too strict for some queries, missing relevant content.

**Solution**: Start with strict threshold, automatically relax if insufficient results:
- Attempt 1: 0.5 similarity threshold
- Attempt 2: 0.35 threshold (if < 33% of expected results)
- Attempt 3: 0.2 threshold (minimum)

**Example**:
```
🔎 Searching: 'mood and emotional state...' (max: 10)
  ↻ Only got 2 results with threshold 0.50, retrying with 0.35
✅ Found 7 relevant segments (scores: ['0.62', '0.58', '0.42']...)
```

### 2. **Temporal Context Windows**

**Problem**: Semantically "distant" segments might provide crucial context.

**Solution**: For high-relevance matches (score >= 0.6), automatically include 2 segments before and after.

**Example**:
- Segment matched: "I feel very anxious" (similarity: 0.85)
- Context added:
  - [Before]: "My father passed away last week"
  - [Before]: "The funeral was yesterday"
  - [Match]: "I feel very anxious"
  - [After]: "I can't sleep at night"
  - [After]: "Work has been difficult"

**Impact**: Captures narrative flow and causal relationships.

### 3. **Zero-Results Fallback**

**Problem**: If semantic search returns nothing, document generation would fail or be content-less.

**Solution**: Automatically fall back to retrieving ALL segments from the sessions (with threshold=0.0).

**Trigger**: `if len(all_relevant_segments) == 0`

### 4. **Query Diversity**

**Problem**: Generic queries might miss specific content.

**Solution**: Template analysis generates diverse, targeted queries:
- "mental health concerns and symptoms discussed..."
- "current life stressors and challenges mentioned..."  
- "mood and emotional state described..."
- "therapeutic interventions used..."
- etc.

### 5. **Purpose Tagging**

Each retrieved segment is tagged with its search purpose, allowing the LLM to understand why each piece of context is included:

```python
segment["_search_purpose"] = "Subjective - Mood and Emotional State"
segment["_search_query"] = "mood and emotional state described"
segment["_is_context"] = True  # For temporal context additions
```

## Quality vs. Coverage Trade-offs

| Configuration | Coverage | Token Usage | Risk of Missing Content |
|---------------|----------|-------------|------------------------|
| **Conservative** (threshold: 0.7, no context) | Low | Low | High |
| **Balanced** (threshold: 0.5, window: 2) | Medium | Medium | Medium |
| **Aggressive** (threshold: 0.2, window: 3) | High | High | Low |
| **Fallback** (threshold: 0.0, all segments) | Complete | Very High | None |

**Current Settings**: Balanced with adaptive escalation

## Monitoring & Logging

The system provides detailed logging to understand search quality:

```
🔎 STEP 2: Executing 19 semantic searches
🔎 Searching: 'mental health concerns...' (max: 15)
✅ Found 12 relevant segments (scores: ['0.78', '0.65', '0.59']...), added 12 to context
📊 STEP 2 Complete: Total 157 relevant segments retrieved
🔍 Fetching temporal context (±2 segments) for 45 high-relevance matches
✅ Added 87 temporal context segments
📊 Total segments after context enrichment: 244
```

**Warning indicators**:
```
⚠️ Only got 2 results with threshold 0.50, retrying with 0.35
⚠️ Query returned few results (3) even with relaxed threshold
📊 5 queries returned limited results:
   • 'risk assessment findings...' (Assessment): 2 results
```

## Tuning Recommendations

### For Short Sessions (< 30 minutes)
- Increase `base_similarity_threshold` to 0.6 (be more selective)
- Reduce `temporal_context_window` to 1
- Risk: Low (not much content to miss)

### For Long Sessions (> 90 minutes)  
- Keep `base_similarity_threshold` at 0.5
- Increase `temporal_context_window` to 3
- Risk: Medium-High (more content, more potential to miss)

### For Simple Templates (1-3 sections)
- Increase `min_result_fraction` to 0.5 (expect more results per query)
- Can use higher thresholds safely

### For Complex Templates (10+ sections)
- Keep adaptive thresholds enabled
- Consider increasing `max_threshold_attempts` to 4
- Monitor "low result queries" carefully

## Alternative Approaches Considered

### 1. **Chronological Sampling** (Not Implemented)
Evenly sample segments across the session timeline.
- **Pros**: Guaranteed temporal coverage
- **Cons**: Might miss concentrated important discussions
- **Decision**: Could add as hybrid (70% semantic, 30% chronological)

### 2. **Sliding Window Chunking** (Not Implemented)
Break session into overlapping chunks, semantic search within chunks.
- **Pros**: Better local context
- **Cons**: Complex implementation, potential duplication
- **Decision**: Temporal context window achieves similar effect more simply

### 3. **Two-Pass Retrieval** (Partially Implemented via temporal context)
First pass: semantic search. Second pass: fill temporal gaps.
- **Pros**: Comprehensive coverage
- **Cons**: Slower (2x API calls)
- **Decision**: Temporal context window is a simplified version of this

### 4. **LLM-Guided Retrieval** (Not Implemented)
Use LLM to iteratively request more context.
- **Pros**: Very intelligent, adaptive
- **Cons**: Slow, expensive, complex
- **Decision**: Too complex for v1, consider for future

## Success Metrics

Track these metrics to assess search quality:

1. **Coverage**: % of segments retrieved vs. total available
2. **Relevance**: Average similarity scores of retrieved segments
3. **Threshold Relaxations**: How often thresholds need to be relaxed
4. **Context Additions**: How many temporal context segments are added
5. **Fallback Frequency**: How often zero-results fallback triggers

## Future Enhancements

### Priority 1: Add Metrics Dashboard
Create endpoint to expose search quality metrics for monitoring.

### Priority 2: Template Complexity Scoring
Automatically adjust search strategy based on template complexity:
- Simple templates: More selective (higher threshold)
- Complex templates: More comprehensive (lower threshold)

### Priority 3: User Feedback Loop
Allow practitioners to flag when generated documents missed important content, use this to tune thresholds.

### Priority 4: Hybrid Semantic + Chronological
Add configurable chronological sampling to guarantee temporal coverage:
```python
if SEMANTIC_SEARCH_CONFIG["chronological_weight"] > 0:
    chronological_samples = sample_evenly_across_session(
        session_ids, 
        fraction=SEMANTIC_SEARCH_CONFIG["chronological_weight"]
    )
```

## Conclusion

The current semantic search approach balances quality and coverage through:
1. ✅ Adaptive thresholds (prevents too-strict filtering)
2. ✅ Temporal context (captures narrative flow)
3. ✅ Zero-results fallback (ensures completeness)
4. ✅ Diverse queries (comprehensive coverage of template needs)
5. ✅ Detailed logging (visibility into search quality)

**Risk Level**: **LOW to MEDIUM**
- Low risk for simple templates with abundant matching content
- Medium risk for complex templates with sparse relevant content
- Mitigated by adaptive thresholds and fallback strategy

**Recommended Actions**:
1. Monitor "low result queries" warnings in logs
2. If patterns emerge, adjust `SEMANTIC_SEARCH_CONFIG` thresholds
3. Consider adding chronological sampling for very long sessions (>2 hours)
4. Gather practitioner feedback on document completeness

