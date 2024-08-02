from typing import List, Dict
from langchain_text_splitters import RecursiveCharacterTextSplitter

class RecursiveChunker:
    def __init__(self, chunk_size: int = 4000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        # self.seperator = seperator
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def chunk(self, content: str) -> List[Dict[str,str]]:
        pages = content.get('pages',[])
        chunks = []
        for page in pages:
            page_text = page.get('page_text', '')
            page_chunks = self.text_splitter.split_text(page_text)
            for chunk in page_chunks:
                chunks.append({"chunk":chunk})

        return chunks

