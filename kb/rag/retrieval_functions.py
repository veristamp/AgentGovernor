# rag/retrieval_functions.py
"""
Database Retrieval Functions - The "N+1 Killer"
Postgres RPC functions for graph context retrieval.
"""

# ============================================================================
# STEP 1: The "One-Shot" Graph Context Retriever
# ============================================================================
GET_GRAPH_CONTEXT_SQL = """
CREATE OR REPLACE FUNCTION get_graph_context(
    start_node_id BIGINT, 
    max_depth INT DEFAULT 1
)
RETURNS TABLE (
    node_id BIGINT,
    node_type TEXT,
    node_content TEXT,
    distance INT,
    path TEXT
) AS $$
BEGIN
    RETURN QUERY
    WITH RECURSIVE walk AS (
        -- 1. Anchor: The starting chunk
        SELECT 
            n.id,
            n.type::TEXT,
            n.content AS c,
            0 as depth,
            'START'::TEXT as path_type
        FROM nodes n 
        WHERE n.id = start_node_id
        
        UNION ALL
        
        -- 2. Recursion: Follow Hard Edges (Parent/Next) & Strong Soft Edges
        SELECT 
            n.id,
            n.type::TEXT,
            n.content AS c,
            w.depth + 1,
            e.edge_type::TEXT
        FROM nodes n
        JOIN edges e ON e.target_id = n.id OR e.source_id = n.id
        JOIN walk w ON (e.source_id = w.id OR e.target_id = w.id) AND n.id != w.id
        WHERE w.depth < max_depth
          AND (
              e.edge_type IN ('CHILD_OF', 'FOLLOWS', 'PARENT', 'REFERS_TO')  -- Hard edges
              OR (e.edge_type = 'MENTIONS' AND e.weight > 0.5)               -- Strong mentions
          )
    )
    SELECT DISTINCT ON (id) 
        id as node_id,
        type as node_type,
        c as node_content,
        depth as distance,
        path_type as path
    FROM walk
    ORDER BY id, depth;
END;
$$ LANGUAGE plpgsql;
"""


# ============================================================================
# STEP 2: Full context with parent, flow, and concepts in ONE query
# ============================================================================
GET_FULL_CONTEXT_SQL = """
CREATE OR REPLACE FUNCTION get_full_context(
    start_node_id BIGINT,
    include_flow BOOLEAN DEFAULT TRUE,
    include_concepts BOOLEAN DEFAULT TRUE
)
RETURNS TABLE (
    chunk_id BIGINT,
    chunk_content TEXT,
    chunk_type VARCHAR(20),
    section_path TEXT,
    parent_context TEXT,
    parent_section_path TEXT,
    prev_chunk_text TEXT,
    next_chunk_text TEXT,
    related_concepts JSONB
) AS $$
BEGIN
    RETURN QUERY
    WITH target AS (
        SELECT 
            n.id AS node_id,
            n.content AS node_content,
            n.type AS node_type,
            n.section_path AS node_section_path,
            n.parent_id AS node_parent_id,
            n.prev_id AS node_prev_id,
            n.next_id AS node_next_id
        FROM nodes n
        WHERE n.id = start_node_id
    ),
    parent_node AS (
        SELECT 
            pn.content AS parent_content,
            pn.section_path AS parent_path
        FROM nodes pn
        WHERE pn.id = (SELECT node_parent_id FROM target)
    ),
    flow_nodes AS (
        SELECT 
            (SELECT n.content FROM nodes n WHERE n.id = t.node_prev_id) AS prev_text,
            (SELECT n.content FROM nodes n WHERE n.id = t.node_next_id) AS next_text
        FROM target t
        WHERE include_flow = TRUE
    ),
    concept_edges AS (
        SELECT 
            COALESCE(
                jsonb_agg(
                    jsonb_build_object(
                        'id', gc.id,
                        'name', gc.name,
                        'type', e.edge_type,
                        'weight', e.weight
                    )
                    ORDER BY e.weight DESC
                ),
                '[]'::jsonb
            ) AS concepts
        FROM edges e
        JOIN global_concepts gc ON e.target_id = gc.id
        WHERE e.source_id = start_node_id 
        AND e.edge_type IN ('MENTIONS', 'BELONGS_TO_DOMAIN')
        AND e.weight > 0.05  -- Include even weak domain links
        AND include_concepts = TRUE
    )
    SELECT 
        t.node_id AS chunk_id,
        t.node_content AS chunk_content,
        t.node_type AS chunk_type,
        t.node_section_path AS section_path,
        COALESCE(p.parent_content, '') AS parent_context,
        COALESCE(p.parent_path, '') AS parent_section_path,
        CASE WHEN include_flow THEN COALESCE(f.prev_text, '') ELSE '' END AS prev_chunk_text,
        CASE WHEN include_flow THEN COALESCE(f.next_text, '') ELSE '' END AS next_chunk_text,
        CASE WHEN include_concepts THEN COALESCE(c.concepts, '[]'::jsonb) ELSE '[]'::jsonb END AS related_concepts
    FROM target t
    LEFT JOIN parent_node p ON TRUE
    LEFT JOIN flow_nodes f ON TRUE
    LEFT JOIN concept_edges c ON TRUE;
END;
$$ LANGUAGE plpgsql;
"""

# ============================================================================
# STEP 3: Find related documents via shared concepts (Hub-Hop)
# ============================================================================
FIND_RELATED_DOCS_SQL = """
CREATE OR REPLACE FUNCTION find_related_documents(
    source_chunk_id BIGINT,
    min_shared_concepts INT DEFAULT 2,
    limit_count INT DEFAULT 5
)
RETURNS TABLE (
    related_chunk_id BIGINT,
    related_doc_url TEXT,
    shared_concept_count INT,
    shared_concepts JSONB
) AS $$
BEGIN
    RETURN QUERY
    WITH source_concepts AS (
        -- Get concepts from source chunk (MENTIONS only, strong edges)
        SELECT e.target_id AS concept_id
        FROM edges e
        WHERE e.source_id = source_chunk_id
        AND e.edge_type = 'MENTIONS'
        AND e.weight > 0.4
    ),
    related_chunks AS (
        SELECT 
            e.source_id AS chunk_id,
            n.doc_url,
            COUNT(DISTINCT e.target_id)::INT AS shared_count,
            jsonb_agg(DISTINCT gc.name) AS shared_names
        FROM edges e
        JOIN source_concepts sc ON e.target_id = sc.concept_id
        JOIN nodes n ON n.id = e.source_id
        JOIN global_concepts gc ON gc.id = e.target_id
        WHERE e.edge_type = 'MENTIONS'
        AND e.source_id != source_chunk_id
        AND e.weight > 0.4  -- Only count strong edges
        GROUP BY e.source_id, n.doc_url
        HAVING COUNT(DISTINCT e.target_id) >= min_shared_concepts
    )
    SELECT 
        rc.chunk_id AS related_chunk_id,
        rc.doc_url AS related_doc_url,
        rc.shared_count AS shared_concept_count,
        rc.shared_names AS shared_concepts
    FROM related_chunks rc
    ORDER BY rc.shared_count DESC
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;
"""

# ============================================================================
# STEP 4: Supernode Cleanup Query (run after ingestion)
# ============================================================================
CLEANUP_SUPERNODES_SQL = """
CREATE OR REPLACE FUNCTION cleanup_supernodes(
    top_percent FLOAT DEFAULT 0.05
)
RETURNS INT AS $$
DECLARE
    deleted_count INT;
BEGIN
    WITH noisy_concepts AS (
        SELECT gc.id as concept_id
        FROM global_concepts gc
        WHERE gc.doc_count > (
            SELECT PERCENTILE_CONT(1 - top_percent) WITHIN GROUP (ORDER BY doc_count)
            FROM global_concepts
        )
    )
    -- Instead of deleting, we now demote to BELONGS_TO_DOMAIN with low weight
    UPDATE edges 
    SET edge_type = 'BELONGS_TO_DOMAIN',
        weight = 0.05
    WHERE target_id IN (SELECT concept_id FROM noisy_concepts)
    AND edge_type = 'MENTIONS';
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;
"""

# ============================================================================
# STEP 5: Get concept frequency stats
# ============================================================================
GET_CONCEPT_STATS_SQL = """
CREATE OR REPLACE FUNCTION get_concept_stats()
RETURNS TABLE (
    total_concepts BIGINT,
    total_edges BIGINT,
    avg_doc_count FLOAT,
    max_doc_count INT,
    supernode_threshold INT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        (SELECT COUNT(*) FROM global_concepts)::BIGINT as total_concepts,
        (SELECT COUNT(*) FROM edges WHERE edge_type = 'MENTIONS')::BIGINT as total_edges,
        (SELECT AVG(doc_count) FROM global_concepts)::FLOAT as avg_doc_count,
        (SELECT MAX(doc_count) FROM global_concepts)::INT as max_doc_count,
        (SELECT PERCENTILE_CONT(0.90) WITHIN GROUP (ORDER BY doc_count)::INT FROM global_concepts) as supernode_threshold;
END;
$$ LANGUAGE plpgsql;
"""

# ============================================================================
# STEP 6: Find chunks by concept names
# ============================================================================
FIND_CHUNKS_BY_CONCEPTS_SQL = """
CREATE OR REPLACE FUNCTION find_chunks_by_concepts(
    concept_names JSONB,
    limit_count INT DEFAULT 10
)
RETURNS TABLE (
    chunk_id BIGINT,
    chunk_content TEXT,
    section_path TEXT,
    doc_url TEXT,
    match_count INT,
    total_weight FLOAT,
    matched_concepts TEXT,
    meta JSON
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        n.id as chunk_id,
        n.content as chunk_content,
        n.section_path,
        n.doc_url::TEXT,
        COUNT(DISTINCT gc.id)::INT as match_count,
        SUM(e.weight)::FLOAT as total_weight,
        string_agg(DISTINCT gc.name, ', ') as matched_concepts,
        n.meta
    FROM nodes n
    JOIN edges e ON e.source_id = n.id
    JOIN global_concepts gc ON e.target_id = gc.id
    WHERE gc.name IN (SELECT value FROM jsonb_array_elements_text(concept_names))
    AND e.edge_type = 'MENTIONS'
    GROUP BY n.id
    ORDER BY match_count DESC, total_weight DESC
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;
"""


ALL_RETRIEVAL_FUNCTIONS_SQL = f"""
{GET_GRAPH_CONTEXT_SQL}
{GET_FULL_CONTEXT_SQL}
{FIND_RELATED_DOCS_SQL}
{CLEANUP_SUPERNODES_SQL}
{GET_CONCEPT_STATS_SQL}
{FIND_CHUNKS_BY_CONCEPTS_SQL}
"""

async def create_retrieval_functions(pg_session) -> None:
    from sqlalchemy import text
    await pg_session.execute(text(GET_GRAPH_CONTEXT_SQL))
    await pg_session.execute(text(GET_FULL_CONTEXT_SQL))
    await pg_session.execute(text(FIND_RELATED_DOCS_SQL))
    await pg_session.execute(text(CLEANUP_SUPERNODES_SQL))
    await pg_session.execute(text(GET_CONCEPT_STATS_SQL))
    await pg_session.execute(text(FIND_CHUNKS_BY_CONCEPTS_SQL))
    await pg_session.commit()

def get_init_sql() -> str:
    return ALL_RETRIEVAL_FUNCTIONS_SQL
