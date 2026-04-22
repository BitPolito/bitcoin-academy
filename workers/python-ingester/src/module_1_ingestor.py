import os
import gc
import logging
from typing import Callable, Any, List
import pdfplumber

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - INGESTOR - %(message)s')
logger = logging.getLogger(__name__)

class RamSafeIngestor:
    def __init__(self, file_path: str, chunk_size: int = 100):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Target PDF not found at {file_path}")
        self.file_path = file_path
        self.chunk_size = chunk_size
        self.total_pages = self._get_total_pages()

    def _get_total_pages(self) -> int:
        logger.info(f"Calculating total pages for: {os.path.basename(self.file_path)}")
        try:
            with pdfplumber.open(self.file_path) as pdf:
                total = len(pdf.pages)
            logger.info(f"Target locked: {total} pages detected.")
            return total
        except Exception as e:
            logger.error(f"Failed to read PDF structure: {e}")
            raise

    def process_in_batches(self, extraction_callback: Callable[[List[Any]], None]):
        for start_page in range(0, self.total_pages, self.chunk_size):
            end_page = min(start_page + self.chunk_size, self.total_pages)
            page_numbers = list(range(start_page + 1, end_page + 1))
            
            logger.info(f"Opening memory-safe slice: Pages {start_page + 1} to {end_page}...")
            try:
                with pdfplumber.open(self.file_path, pages=page_numbers) as pdf:
                    extraction_callback(pdf.pages)
            except Exception as e:
                logger.error(f"Catastrophic failure on batch {start_page + 1}-{end_page}: {e}")
                continue
            finally:
                collected = gc.collect()
                logger.debug(f"Garbage collector freed {collected} objects.")