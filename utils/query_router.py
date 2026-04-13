"""Route natural language queries to appropriate database systems."""

from typing import Dict, List, Tuple, Optional
from enum import Enum
import re

class DatabaseType(Enum):
    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"
    MONGODB = "mongodb"
    DUCKDB = "duckdb"

class QueryRouter:
    """
    Determine which database(s) to query based on intent and schema.
    
    Features:
    - Keyword-based routing
    - Schema-aware routing
    - Cross-database query splitting
    """
    
    # Keywords that suggest specific databases
    DB_KEYWORDS = {
        DatabaseType.POSTGRESQL: ['postgres', 'postgresql', 'pg_', 'transactions', 'sales'],
        DatabaseType.MONGODB: ['mongodb', 'mongo', 'document', 'review', 'comment', 'feedback', 'unstructured', 'json'],
        DatabaseType.DUCKDB: ['duckdb', 'analytics', 'aggregate', 'large', 'parquet', 'csv'],
        DatabaseType.SQLITE: ['sqlite', 'local', 'embedded', 'config', 'settings', 'customers']
    }
    
    def __init__(self, schema_introspector):
        self.schema = schema_introspector
    
    async def route(self, query: str) -> List[DatabaseType]:
        """
        Determine which databases to query for a given natural language query.
        
        Returns:
            List of database types, ordered by relevance
        """
        await self.schema.refresh()
        query_lower = query.lower()
        
        scores = {db: 0 for db in DatabaseType}
        
        # Keyword matching
        for db_type, keywords in self.DB_KEYWORDS.items():
            for keyword in keywords:
                if keyword in query_lower:
                    scores[db_type] += 2
        
        # Schema-based routing: check if query mentions specific tables
        relevant_tables = await self.schema.get_relevant_tables(query, top_k=3)
        for table in relevant_tables:
            db_type = DatabaseType(table.database)
            scores[db_type] += 3
        
        # Special routing for MongoDB (unstructured text extraction)
        if any(word in query_lower for word in ['extract', 'free text', 'note', 'comment', 'description']):
            scores[DatabaseType.MONGODB] += 5
        
        # Special routing for cross-database joins
        if any(word in query_lower for word in ['join', 'combine', 'merge', 'across', 'together']):
            # Return all databases that might be relevant
            return [db for db in DatabaseType if scores[db] > 0]
        
        # Filter and sort by score
        candidates = [(db, score) for db, score in scores.items() if score > 0]
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        return [db for db, _ in candidates[:2]] if candidates else [DatabaseType.POSTGRESQL]
    
    def needs_cross_db_join(self, query: str, routes: List[DatabaseType]) -> bool:
        """Check if query requires joining across multiple databases."""
        q = query.lower()
        return (
            len(routes) > 1
            or any(word in q for word in ['across', 'combine'])
            or bool(re.search(r'join.*different', q))
        )
    
    def split_query_for_cross_db(self, query: str, routes: List[DatabaseType]) -> Dict[DatabaseType, str]:
        """
        Split a cross-database query into sub-queries per database.
        
        Returns:
            Dictionary mapping database to sub-query
        """
        # This is a simplified version - in production, use LLM to split
        sub_queries = {}
        
        for db_type in routes:
            # Create database-specific sub-query
            if db_type == DatabaseType.MONGODB:
                sub_queries[db_type] = self._to_mongodb_query(query)
            else:
                sub_queries[db_type] = self._to_sql_query(query, db_type)
        
        return sub_queries
    
    def _to_sql_query(self, query: str, db_type: DatabaseType) -> str:
        """Convert natural language to approximate SQL query."""
        # Simplified - would use LLM in production
        return f"-- Query for {db_type.value}\nSELECT * FROM relevant_table"
    
    def _to_mongodb_query(self, query: str) -> str:
        """Convert natural language to MongoDB aggregation pipeline."""
        return 'db.collection.aggregate([{"$match": {}}])'