from typing import List, Dict
from langchain_text_splitters.character import CharacterTextSplitter

class FixedSizeChunker:
    def __init__(self, chunk_size: int = 4000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        # self.seperator = seperator
        self.text_splitter = CharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def chunk(self, content: str) -> List[Dict[str,str]]:
        pages = content.get('pages',[])
        chunks = []
        for page in pages:
            page_text = page.get('page_text', '')
            page_chunks = self.text_splitter.split_text(page_text)
            for chunk in page_chunks:
                chunks.append({"chunk":chunk})

        return chunks
    # def __init__(self, chunk_size: int = 4000, chunk_overlap: int = 200, seperator: str = '\n\n'):
    #     self.chunk_size = chunk_size
    #     self.chunk_overlap = chunk_overlap
    #     self.seperator = seperator
    #     self.text_splitter = CharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap, seperator=seperator)

