import os
import asyncio
from dataclasses import dataclass
from typing import Optional, Dict, Any, List


@dataclass
class AppMinerSettings:
    """
    Configuration settings and data fetcher for AppMiner / Neo4j Graph Database.
    Connects to Neo4j database via Bolt protocol (neo4j+s:// or neo4j://).
    """
    neo4j_uri: Optional[str] = None
    neo4j_username: Optional[str] = None
    neo4j_password: Optional[str] = None
    neo4j_database: Optional[str] = "neo4j"

    @classmethod
    def from_env(cls) -> "AppMinerSettings":
        """Load AppMiner Neo4j settings from environment variables."""
        return cls(
            neo4j_uri=os.getenv("NEO4J_URI"),
            neo4j_username=os.getenv("NEO4J_USERNAME"),
            neo4j_password=os.getenv("NEO4J_PASSWORD"),
            neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
        )

    def is_configured(self) -> bool:
        """Check if minimum required credentials for Neo4j database are present."""
        return bool(self.neo4j_uri and self.neo4j_username and self.neo4j_password)

    def to_dict(self, mask_secrets: bool = True) -> Dict[str, Any]:
        """Return dictionary representation of Neo4j settings with password masked."""
        password = "********" if mask_secrets and self.neo4j_password else self.neo4j_password
        return {
            "neo4j_uri": self.neo4j_uri,
            "neo4j_username": self.neo4j_username,
            "neo4j_password": password,
            "neo4j_database": self.neo4j_database,
            "is_configured": self.is_configured(),
        }

    def _get_driver(self):
        """Internal helper to initialize Neo4j driver."""
        try:
            from neo4j import GraphDatabase  # type: ignore
        except ImportError:
            raise RuntimeError(
                "The 'neo4j' Python package is not installed. Please install it using 'pip install neo4j'."
            )
        
        return GraphDatabase.driver(
            self.neo4j_uri,
            auth=(self.neo4j_username, self.neo4j_password),
        )

    async def test_connection(self) -> Dict[str, Any]:
        """
        Test connection to Neo4j database by executing a verification Cypher query.
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "AppMiner / Neo4j is not configured. NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD are required.",
                "details": None,
            }

        def _run_test():
            driver = self._get_driver()
            try:
                with driver.session(database=self.neo4j_database or None) as session:
                    # 1. Verify basic connectivity
                    test_res = session.run("RETURN 1 AS ping").single()
                    
                    # 2. Fetch node count summary
                    count_res = session.run("MATCH (n) RETURN count(n) AS total_nodes").single()
                    total_nodes = count_res["total_nodes"] if count_res else 0
                    
                    # 3. Fetch node labels present in the DB
                    labels_res = session.run("CALL db.labels() YIELD label RETURN label LIMIT 20")
                    labels = [record["label"] for record in labels_res]

                    # 4. Fetch relationship types
                    rel_res = session.run("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType LIMIT 20")
                    rel_types = [record["relationshipType"] for record in rel_res]

                    return {
                        "success": True,
                        "message": "Successfully connected to Neo4j database.",
                        "database": self.neo4j_database,
                        "uri": self.neo4j_uri,
                        "total_nodes": total_nodes,
                        "node_labels": labels,
                        "relationship_types": rel_types,
                    }
            finally:
                driver.close()

        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, _run_test)
        except Exception as e:
            return {
                "success": False,
                "error": f"Neo4j connection test failed: {str(e)}",
                "uri": self.neo4j_uri,
                "database": self.neo4j_database,
            }

    async def fetch_data(self, query: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
        """
        Fetch data from Neo4j database. 
        If custom Cypher query is not provided, defaults to fetching graph nodes & relationships.
        """
        if not self.is_configured():
            return {
                "success": False,
                "error": "AppMiner / Neo4j is not configured.",
                "data": [],
            }

        cypher_query = query or f"MATCH (n) RETURN n LIMIT {int(limit)}"

        def _execute_fetch():
            driver = self._get_driver()
            try:
                with driver.session(database=self.neo4j_database or None) as session:
                    result = session.run(cypher_query)
                    records = []
                    for record in result:
                        record_dict = {}
                        for key, value in record.items():
                            # Format Neo4j Node objects into standard dicts
                            if hasattr(value, "labels") and hasattr(value, "items"):
                                record_dict[key] = {
                                    "id": getattr(value, "element_id", getattr(value, "id", None)),
                                    "labels": list(value.labels),
                                    "properties": dict(value.items()),
                                }
                            # Format Neo4j Relationship objects into standard dicts
                            elif hasattr(value, "type") and hasattr(value, "items"):
                                record_dict[key] = {
                                    "id": getattr(value, "element_id", getattr(value, "id", None)),
                                    "type": value.type,
                                    "start_node": getattr(value, "start_node", None),
                                    "end_node": getattr(value, "end_node", None),
                                    "properties": dict(value.items()),
                                }
                            else:
                                record_dict[key] = value
                        records.append(record_dict)

                    return {
                        "success": True,
                        "query": cypher_query,
                        "record_count": len(records),
                        "data": records,
                    }
            finally:
                driver.close()

        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, _execute_fetch)
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to fetch data from Neo4j: {str(e)}",
                "data": [],
            }
