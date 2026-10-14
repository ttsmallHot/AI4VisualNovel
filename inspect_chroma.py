import os
import chromadb
import json

# 指向我们真实的 ChromaDB 存储路径
# 请注意将其替换为你想要检查的项目的实际路径
# 例如："data/your_game_name/chroma"
CHROMA_DIR = os.path.join(os.path.dirname(__file__), "data", "your_game_name", "chroma")

def inspect_chroma():
    if not os.path.exists(CHROMA_DIR):
        print(f"❌ 找不到 ChromaDB 目录: {CHROMA_DIR}")
        return

    print(f"📂 正在连接 ChromaDB: {CHROMA_DIR}")
    client = chromadb.PersistentClient(path=CHROMA_DIR)

    collections = client.list_collections()
    if not collections:
        print("⚠️ ChromaDB 中没有任何 Collection (没有数据)。")
        return

    print(f"✅ 找到 {len(collections)} 个 Collection(s)。\n")

    for col_info in collections:
        # col_info.name 是集合的名称
        col_name = col_info.name
        col = client.get_collection(col_name)

        print(f"{'='*60}")
        print(f"📦 Collection: {col_name}")
        print(f"{'='*60}")

        # 获取集合里的所有数据
        data = col.get()
        ids = data.get("ids", [])
        docs = data.get("documents", [])
        metas = data.get("metadatas", [])

        if not ids:
            print("  (该集合为空)")
            continue

        print(f"共找到 {len(ids)} 条记忆记录：\n")

        for i in range(len(ids)):
            print(f"--- 📝 记录 {i+1} | ID: {ids[i]} ---")
            print(f"【元数据 Metadata】: {json.dumps(metas[i], ensure_ascii=False)}")
            print("【记忆内容 Document】:")
            print(docs[i])
            print("\n" + "-"*40 + "\n")

if __name__ == "__main__":
    inspect_chroma()
