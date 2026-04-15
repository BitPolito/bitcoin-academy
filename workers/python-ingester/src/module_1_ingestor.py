import os
import gc
import logging
from typing import Callable, Any, List
import pdfplumber

# Configure strict logging for telemetry
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - INGESTOR - %(message)s'
)
logger = logging.getLogger(__name__)

class RamSafeIngestor:
    """
    Module 1: The RAM-Safe Batching Engine.
    Enforces a strict memory cap by parsing PDFs in rolling page slices,
    preventing ONNX and RAM-exhaustion hard crashes on consumer hardware.
    """
    
    def __init__(self, file_path: str, chunk_size: int = 100):
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Target PDF not found at {file_path}")
            
        self.file_path = file_path
        self.chunk_size = chunk_size
        self.total_pages = self._get_total_pages()

    def _get_total_pages(self) -> int:
        """
        Briefly opens the PDF to extract the total page count.
        """
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
        """
        Yields safe, 100-page slices of the document to the provided callback function.
        Forces garbage collection after every slice.
        
        :param extraction_callback: A function representing Module 2 (Structural Parser).
                                    It must accept a list of pdfplumber.Page objects.
        """
        for start_page in range(0, self.total_pages, self.chunk_size):
            end_page = min(start_page + self.chunk_size, self.total_pages)
            
            # pdfplumber 'pages' argument requires a 1-indexed list of specific page numbers
            page_numbers = list(range(start_page + 1, end_page + 1))
            
            logger.info(f"Opening memory-safe slice: Pages {start_page + 1} to {end_page}...")
            
            try:
                # Context manager guarantees file is closed automatically
                with pdfplumber.open(self.file_path, pages=page_numbers) as pdf:
                    # Pass the safely loaded pages to Module 2
                    extraction_callback(pdf.pages)
            
            except Exception as e:
                # Wrap in a fault-tolerant Try/Except to prevent total pipeline death
                logger.error(f"Catastrophic failure on batch {start_page + 1}-{end_page}: {e}")
                logger.info("Logging failure and attempting to continue to next slice...")
                continue
                
            finally:
                # The Ironclad Defense: Force Python's C-bindings to release memory
                collected = gc.collect()
                logger.debug(f"Garbage collector freed {collected} objects.")

# --- Manual Test Execution (For local verification before moving to Module 2) ---
if __name__ == "__main__":
    import sys
    
    # Simple dummy callback to prove the memory lifecycle works
    def dummy_module_2(pages):
        for page in pages:
            # We just print the page number to prove it loaded without extracting heavy text
            print(f"Successfully loaded Page {page.page_number} into RAM.")

    if len(sys.argv) > 1:
        test_file = sys.argv[1]
        ingestor = RamSafeIngestor(file_path=test_file, chunk_size=100)
        ingestor.process_in_batches(extraction_callback=dummy_module_2)
    else:
        print("Provide a path to a test PDF. Usage: python module_1_ingestor.py path/to/test.pdf")