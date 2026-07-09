"""
Chroma Collections Test
Test data/chroma directory collections and their contents
"""
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
import dotenv

dotenv.load_dotenv(project_root / ".env")

# Chroma database path
CHROMA_DIR = project_root / "data" / "chroma"


def get_embedding():
    """Get embedding function"""
    return OpenAIEmbeddings(
        model="text-embedding-v4",
        api_key=os.getenv("QIANWEN_API_KEY"),
        base_url=os.getenv("QIANWEN_API_URL"),
        check_embedding_ctx_length=False
    )


def list_chroma_folders():
    """List folders in chroma directory"""
    print("=" * 60)
    print("data/chroma Directory Structure")
    print("=" * 60)
    
    for item in CHROMA_DIR.iterdir():
        if item.is_dir():
            print(f"[DIR]  {item.name}/")
        else:
            size_kb = item.stat().st_size / 1024
            print(f"[FILE] {item.name} ({size_kb:.1f} KB)")
    print()


def query_sqlite_collections():
    """Query SQLite database for collection mappings"""
    import sqlite3
    
    print("=" * 60)
    print("SQLite Database - Collection Mappings")
    print("=" * 60)
    
    db_path = CHROMA_DIR / "chroma.sqlite3"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Query collections table
    try:
        cursor.execute("SELECT id, name FROM collections")
        collections = cursor.fetchall()
        
        print("\nCollection ID to Name Mapping:")
        print("-" * 50)
        for coll_id, name in collections:
            print(f"  {coll_id}  ->  {name}")
        
        # Query segments table to find folder mapping
        cursor.execute("""
            SELECT s.id, s.collection, s.scope, c.name 
            FROM segments s 
            JOIN collections c ON s.collection = c.id
        """)
        segments = cursor.fetchall()
        
        print("\nSegment (Folder) to Collection Mapping:")
        print("-" * 50)
        for seg_id, coll_id, scope, name in segments:
            print(f"  Folder: {seg_id}")
            print(f"          -> Collection: {name} (scope: {scope})")
            
    except Exception as e:
        print(f"Error querying SQLite: {e}")
    finally:
        conn.close()
    
    print()


def analyze_memory_collection():
    """Analyze chat memory collection"""
    print("=" * 60)
    print("Chat Memory Collection (nonebot_agent_memory)")
    print("=" * 60)
    
    try:
        db = Chroma(
            collection_name="nonebot_agent_memory",
            embedding_function=get_embedding(),
            persist_directory=str(CHROMA_DIR)
        )
        
        # Get collection info
        collection = db._collection
        count = collection.count()
        print(f"Collection Name: nonebot_agent_memory")
        print(f"Collection ID (Folder): {collection.id}")
        print(f"Total Records: {count}")
        
        if count > 0:
            # Get sample data
            sample = collection.peek(limit=5)
            
            # Analyze metadata
            users = set()
            modes = {}
            groups = set()
            
            for metadata in sample.get('metadatas', []):
                if metadata:
                    if 'user_id' in metadata:
                        users.add(metadata['user_id'])
                    if 'mode' in metadata:
                        modes[metadata['mode']] = modes.get(metadata['mode'], 0) + 1
                    if 'group_id' in metadata:
                        groups.add(metadata['group_id'])
            
            print(f"\nSample Statistics (from {len(sample.get('ids', []))} samples):")
            print(f"  - Users found: {list(users)}")
            print(f"  - Modes: {modes}")
            print(f"  - Groups: {list(groups) if groups else 'None'}")
            
            print(f"\nSample Records:")
            for i, (doc_id, document, metadata) in enumerate(zip(
                sample.get('ids', []),
                sample.get('documents', []),
                sample.get('metadatas', [])
            ), 1):
                print(f"\n  [{i}] ID: {doc_id[:30]}...")
                if document:
                    preview = document[:100].replace('\n', ' ').replace('\r', '')
                    print(f"      Content: {preview}...")
                if metadata:
                    print(f"      Metadata: {metadata}")
                    
    except Exception as e:
        print(f"Error accessing nonebot_agent_memory: {e}")
    
    print()


def analyze_sticker_collection():
    """Analyze sticker description collection"""
    print("=" * 60)
    print("Sticker Collection (images_description)")
    print("=" * 60)
    
    try:
        db = Chroma(
            collection_name="images_description",
            embedding_function=get_embedding(),
            persist_directory=str(CHROMA_DIR)
        )
        
        collection = db._collection
        count = collection.count()
        print(f"Collection Name: images_description")
        print(f"Collection ID (Folder): {collection.id}")
        print(f"Total Stickers: {count}")
        
        if count > 0:
            sample = collection.peek(limit=5)
            print(f"\nSample Stickers:")
            
            for i, (doc_id, document, metadata) in enumerate(zip(
                sample.get('ids', []),
                sample.get('documents', []),
                sample.get('metadatas', [])
            ), 1):
                filename = metadata.get('url', 'N/A') if metadata else 'N/A'
                print(f"\n  [{i}] File: {filename}")
                if document:
                    preview = document[:120].replace('\n', ' ').replace('\r', '')
                    print(f"      Description: {preview}...")
                    
    except Exception as e:
        print(f"Error accessing images_description: {e}")
    
    print()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Chroma Database Test Script")
    print("=" * 60 + "\n")
    
    # 1. Show directory structure
    list_chroma_folders()
    
    # 2. Query SQLite for folder mappings
    query_sqlite_collections()
    
    # 3. Analyze chat memory
    analyze_memory_collection()
    
    # 4. Analyze stickers
    analyze_sticker_collection()
    
    print("=" * 60)
    print("Test Complete!")
    print("=" * 60)
