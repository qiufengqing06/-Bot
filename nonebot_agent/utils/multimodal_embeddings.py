"""
Multimodal Embedding Module
Wrapper for DashScope MultiModalEmbedding API to support image vectorization.
"""
import os
from typing import List, Optional, Union
from pathlib import Path

import dashscope
from dashscope import MultiModalEmbedding
from nonebot.log import logger

from nonebot_agent.config import config
from nonebot_agent.utils.media_handler import image_to_base64


class MultimodalEmbeddings:
    """
    Multimodal embeddings using DashScope qwen2.5-vl-embedding model.
    
    Supports:
    - Text embeddings
    - Image embeddings (from URL or local file)
    - Combined text + image embeddings
    """
    
    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        """
        Initialize multimodal embeddings.
        
        Args:
            model: Model name (default from config)
            api_key: DashScope API key (default from config/env)
        """
        self.model = model or config.MULTIMODAL_EMBEDDING_MODEL
        self.api_key = api_key or config.QIANWEN_API_KEY
        
        # Set API key in environment for dashscope
        os.environ["DASHSCOPE_API_KEY"] = self.api_key
    
    def embed_image(self, image_path: str) -> Optional[List[float]]:
        """
        Generate embedding for a local image file.
        
        Args:
            image_path: Path to local image file
            
        Returns:
            Embedding vector or None if failed
        """
        try:
            # Convert local file to base64 data URI
            base64_uri = image_to_base64(image_path)
            if not base64_uri:
                logger.error(f"[MultimodalEmbed] Failed to convert image to base64: {image_path}")
                return None
            
            # Call DashScope API
            response = MultiModalEmbedding.call(
                api_key=self.api_key,
                model=self.model,
                input=[{"image": base64_uri}]
            )
            
            if response.status_code == 200:
                embedding = response.output.get("embeddings", [{}])[0].get("embedding")
                if embedding:
                    logger.info(f"[MultimodalEmbed] Generated image embedding, dim={len(embedding)}")
                    return embedding
            else:
                logger.error(f"[MultimodalEmbed] API error: {response.code} - {response.message}")
                return None
                
        except Exception as e:
            logger.error(f"[MultimodalEmbed] Error embedding image: {e}")
            return None
    
    def embed_image_url(self, image_url: str) -> Optional[List[float]]:
        """
        Generate embedding for an image URL.
        
        Args:
            image_url: Image URL
            
        Returns:
            Embedding vector or None if failed
        """
        try:
            response = MultiModalEmbedding.call(
                api_key=self.api_key,
                model=self.model,
                input=[{"image": image_url}]
            )
            
            if response.status_code == 200:
                embedding = response.output.get("embeddings", [{}])[0].get("embedding")
                if embedding:
                    logger.info(f"[MultimodalEmbed] Generated URL image embedding, dim={len(embedding)}")
                    return embedding
            else:
                logger.error(f"[MultimodalEmbed] API error: {response.code} - {response.message}")
                return None
                
        except Exception as e:
            logger.error(f"[MultimodalEmbed] Error embedding image URL: {e}")
            return None
    
    def embed_text(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for text (using text-embedding-v4 for text-only).
        
        Note: For text-only embeddings, we use the standard text embedding model
        as it's more efficient. For multimodal content, use embed_combined().
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector or None if failed
        """
        from langchain_community.embeddings import DashScopeEmbeddings
        
        try:
            embeddings = DashScopeEmbeddings(
                model=config.TEXT_EMBEDDING_MODEL,
                dashscope_api_key=self.api_key,
            )
            result = embeddings.embed_query(text)
            logger.info(f"[MultimodalEmbed] Generated text embedding, dim={len(result)}")
            return result
        except Exception as e:
            logger.error(f"[MultimodalEmbed] Error embedding text: {e}")
            return None
    
    def embed_combined(
        self, 
        text: Optional[str] = None, 
        image_path: Optional[str] = None,
        image_url: Optional[str] = None
    ) -> Optional[List[float]]:
        """
        Generate combined embedding for text and image.
        
        Args:
            text: Optional text
            image_path: Optional local image path
            image_url: Optional image URL
            
        Returns:
            Embedding vector or None if failed
        """
        try:
            input_parts = []
            
            # Add image if provided
            if image_path:
                base64_uri = image_to_base64(image_path)
                if base64_uri:
                    input_parts.append({"image": base64_uri})
            elif image_url:
                input_parts.append({"image": image_url})
            
            # Add text if provided
            if text:
                input_parts.append({"text": text})
            
            if not input_parts:
                logger.warning("[MultimodalEmbed] No input provided for combined embedding")
                return None
            
            response = MultiModalEmbedding.call(
                api_key=self.api_key,
                model=self.model,
                input=input_parts
            )
            
            if response.status_code == 200:
                embedding = response.output.get("embeddings", [{}])[0].get("embedding")
                if embedding:
                    logger.info(f"[MultimodalEmbed] Generated combined embedding, dim={len(embedding)}")
                    return embedding
            else:
                logger.error(f"[MultimodalEmbed] API error: {response.code} - {response.message}")
                return None
                
        except Exception as e:
            logger.error(f"[MultimodalEmbed] Error generating combined embedding: {e}")
            return None


# Global instance
_multimodal_embeddings = None


def get_multimodal_embeddings() -> MultimodalEmbeddings:
    """Get or create global multimodal embeddings instance."""
    global _multimodal_embeddings
    if _multimodal_embeddings is None:
        _multimodal_embeddings = MultimodalEmbeddings()
    return _multimodal_embeddings
