from typing import List, Dict
from langchain_text_splitters.character import CharacterTextSplitter

class PagewiseChunker:

    def chunk(self, content: str) -> List[Dict[str,str]]:
        pages = content.get('pages',[])
        chunks = []
        for page in pages:
            page_text = page.get('page_text', '')
            chunks.append({"chunk":page_text})
        return chunks

