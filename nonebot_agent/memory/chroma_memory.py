"""
Chroma Memory Module
Long-term semantic memory storage using Chroma vector database.
Enhanced with mode-based memory separation.
"""
import os
from typing import List, Optional, Dict, Any
from datetime import datetime

from langchain_chroma import Chroma
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_core.documents import Document
from nonebot.log import logger

from nonebot_agent.config import config


def build_chroma_filter(conditions: Dict[str, Any]) -> Dict:
    """
    Build Chroma-compatible filter from conditions dict.
    Chroma requires $and operator for multiple conditions.
    
    Args:
        conditions: Dict of field -> value conditions
        
    Returns:
        Chroma-compatible filter dict
    """
    if len(conditions) == 0:
        return {}
    elif len(conditions) == 1:
        # Single condition: use directly
        return conditions
    else:
        # Multiple conditions: use $and operator
        return {
            "$and": [
                {key: value} for key, value in conditions.items()
            ]
        }


class ChromaMemory:
    """Chroma-based long-term memory storage with semantic search capability.
    
    Enhanced with:
    - Mode-based memory separation (chat vs professional)
    - Group context memory support
    """
    
    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: Optional[str] = None
    ):
        """
        Initialize Chroma memory storage.
        
        Args:
            persist_directory: Directory to persist Chroma data
            collection_name: Name of the Chroma collection
        """
        self.persist_directory = persist_directory or config.CHROMA_PERSIST_DIR
        self.collection_name = collection_name or config.CHROMA_COLLECTION_NAME
        
        # Ensure persist directory exists
        os.makedirs(self.persist_directory, exist_ok=True)
        
        # Initialize embeddings using DashScope (Qianwen/Aliyun)
        api_key = config.QIANWEN_API_KEY
        if api_key is not None:
            os.environ["DASHSCOPE_API_KEY"] = api_key
        self.embeddings = DashScopeEmbeddings(
            model="text-embedding-v4",
        )
        
        # Initialize Chroma vector store
        self.vector_store = Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
            persist_directory=self.persist_directory,
        )
    
    def add_memory(
        self,
        user_id: str,
        content: str,
        mode: str = "professional",
        group_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None,
    ) -> str:
        """
        Add a memory entry to the vector store.
        
        Args:
            user_id: The user's ID
            content: The content to store
            mode: Agent mode ('chat' or 'professional')
            group_id: Optional group ID for group context
            metadata: Additional metadata
            
        Returns:
            The ID of the stored document
        """
        if metadata is None:
            metadata = {}
        
        # Add user_id, mode, and timestamp to metadata
        metadata.update({
            "user_id": user_id,
            "mode": mode,
            "timestamp": datetime.utcnow().isoformat(),
        })
        
        # Add group_id if provided
        if group_id:
            metadata["group_id"] = group_id
        
        # Create document and add to vector store
        doc = Document(page_content=content, metadata=metadata)
        ids = self.vector_store.add_documents([doc], ids=[doc_id] if doc_id else None)
        
        return ids[0] if ids else ""
    
    def search_memory(
        self,
        user_id: str,
        query: str,
        mode: Optional[str] = None,
        group_id: Optional[str] = None,
        k: int = 5,
        extra_filters: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        """
        Search for relevant memories using semantic similarity.
        
        Args:
            user_id: The user's ID to filter memories
            query: The search query
            mode: Optional mode filter ('chat' or 'professional')
            group_id: Optional group ID filter
            k: Number of results to return
            
        Returns:
            List of relevant documents
        """
        # Build filter conditions
        conditions = {"user_id": user_id}
        
        if mode:
            conditions["mode"] = mode
        
        if group_id:
            conditions["group_id"] = group_id

        if extra_filters:
            conditions.update(extra_filters)
        
        # Build Chroma-compatible filter
        filter_dict = build_chroma_filter(conditions)
        
        # Search with filters
        try:
            results = self.vector_store.similarity_search(
                query,
                k=k,
                filter=filter_dict
            )
        except Exception as e:
            # If filter fails, try without mode filter
            logger.warning(f"Chroma search error: {e}, retrying without mode filter")
            results = self.vector_store.similarity_search(
                query,
                k=k,
                filter={"user_id": user_id}
            )
        
        return results
    
    def search_group_memory(
        self,
        group_id: str,
        query: str,
        mode: Optional[str] = None,
        k: int = 5,
        extra_filters: Optional[Dict[str, Any]] = None,
    ) -> List[Document]:
        """
        Search for relevant memories from a specific group using semantic similarity.
        
        Args:
            group_id: The group's ID to filter memories
            query: The search query
            mode: Optional mode filter ('chat' or 'professional')
            k: Number of results to return
            
        Returns:
            List of relevant documents
        """
        # Build filter conditions - search by group_id instead of user_id
        conditions = {"group_id": group_id}
        
        if mode:
            conditions["mode"] = mode

        if extra_filters:
            conditions.update(extra_filters)
        
        # Build Chroma-compatible filter
        filter_dict = build_chroma_filter(conditions)
        
        # Search with filters
        try:
            results = self.vector_store.similarity_search(
                query,
                k=k,
                filter=filter_dict
            )
        except Exception as e:
            # If filter fails, try without mode filter
            logger.warning(f"Chroma search error: {e}, retrying without mode filter")
            results = self.vector_store.similarity_search(
                query,
                k=k,
                filter={"group_id": group_id}
            )
        
        return results
    
    def search_memory_multi_user(
        self,
        user_ids: List[str],
        query: str,
        mode: Optional[str] = None,
        k: int = 5
    ) -> List[Document]:
        """
        Search for relevant memories from multiple users.
        Useful for group chat context.
        
        Args:
            user_ids: List of user IDs to search
            query: The search query
            mode: Optional mode filter
            k: Number of results per user
            
        Returns:
            List of relevant documents from all users
        """
        all_results = []
        
        for user_id in user_ids:
            results = self.search_memory(user_id, query, mode=mode, k=k)
            all_results.extend(results)
        
        # Sort by timestamp (most recent first) and limit
        all_results.sort(
            key=lambda x: x.metadata.get("timestamp", ""),
            reverse=True
        )
        
        return all_results[:k * 2]  # Return more results for group context
    
    def get_user_memories(
        self,
        user_id: str,
        mode: Optional[str] = None,
        limit: int = 10
    ) -> List[Document]:
        """
        Get recent memories for a specific user.
        
        Args:
            user_id: The user's ID
            mode: Optional mode filter
            limit: Maximum number of memories to return
            
        Returns:
            List of user's memories
        """
        conditions = {"user_id": user_id}
        if mode:
            conditions["mode"] = mode
        
        filter_dict = build_chroma_filter(conditions)
        
        # Use a general query to get user's memories
        try:
            results = self.vector_store.similarity_search(
                query="",  # Empty query
                k=limit,
                filter=filter_dict
            )
        except Exception:
            results = self.vector_store.similarity_search(
                query="",
                k=limit,
                filter={"user_id": user_id}
            )
        
        return results
    
    def delete_user_memories(self, user_id: str, mode: Optional[str] = None) -> bool:
        """
        Delete memories for a specific user, optionally filtered by mode.
        
        Args:
            user_id: The user's ID
            mode: Optional mode filter
            
        Returns:
            True if successful
        """
        try:
            # Build filter
            conditions = {"user_id": user_id}
            if mode:
                conditions["mode"] = mode
            
            where_filter = build_chroma_filter(conditions)
            
            # Get collection and delete by filter
            collection = self.vector_store._collection
            collection.delete(where=where_filter)
            return True
        except Exception as e:
            logger.error(f"Error deleting memories: {e}")
            return False

    def delete_memory(self, memory_id: str) -> bool:
        """Delete a specific Chroma memory by document id."""
        try:
            self.vector_store.delete(ids=[memory_id])
            return True
        except Exception as e:
            logger.warning(f"Error deleting memory {memory_id}: {e}")
            return False
