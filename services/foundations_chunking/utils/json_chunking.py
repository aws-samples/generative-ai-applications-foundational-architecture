import json
from typing import List, Dict
from langchain_text_splitters import RecursiveJsonSplitter

class JSONChunker:
    def __init__(self):
        self.splitter = RecursiveJsonSplitter(max_chunk_size=300)

    def chunk_json(self, content: str) -> List[Dict[str,str]]:
        try:
            pages = content.get('pages',[])
            json_content = json.loads(pages[0].get('page_text',''))
            chunks = []
            json_chunks = self.splitter.split_text(json_data=json_content)
            for chunk in json_chunks:
                chunks.append({"chunk":chunk})
            return chunks
        except Exception as e:
            print(e)

    def chunk_jsonl(self, content: str) -> List[Dict[str,str]]:
        pages = content.get('pages',[])
        json_content = str(pages[0].get('page_text',''))
        chunks = []
        for line in json_content.split("\n"):
            chunks.append({"chunk":line})
        return chunks