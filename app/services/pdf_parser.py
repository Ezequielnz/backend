import re
import pdfplumber
from typing import List, Dict, Optional, Any
import logging

# Configure logging
logger = logging.getLogger(__name__)

def parse_pdf_catalog(file_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parses a PDF catalog file to extract product information.
    
    This function reads a PDF file from bytes, iterates through its pages,
    and attempts to extract product details such as code, description, and price
    using regular expressions and text analysis.
    
    The PDF is expected to have a layout where:
    - Product codes are prefixed with "COD:"
    - Prices are prefixed with "$"
    - Descriptions are located in the text blocks surrounding the code and price.
    
    Args:
        file_bytes (bytes): The raw bytes of the PDF file.
        
    Returns:
        List[Dict[str, Any]]: A list of dictionaries, where each dictionary represents a detected product.
            Each dictionary contains:
            - 'code' (str): The extracted product code.
            - 'description' (str): The extracted product description.
            - 'raw_price' (str): The price string as found in the PDF (e.g., "1.200,50").
            - 'price_value' (float): The numeric value of the price.
            - 'page' (int): The page number where the product was found.
            
    Raises:
        Exception: If there is an error opening or processing the PDF.
    """
    products = []
    
    try:
        # Open the PDF from bytes
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            logger.info(f"Processing PDF with {len(pdf.pages)} pages.")
            
            for page_num, page in enumerate(pdf.pages):
                text = page.extract_text()
                if not text:
                    continue
                
                # Split text into lines for processing
                lines = text.split('\n')
                
                # Buffer to hold potential description lines
                description_buffer = []
                
                for line in lines:
                    # Regex to find "COD: XXXXX"
                    # Looks for "COD:" followed by optional whitespace and digits
                    code_match = re.search(r'COD:\s*(\d+)', line)
                    
                    # Regex to find Price "$ X.XXX,XX"
                    # Looks for "$" followed by digits, dots, and commas
                    price_match = re.search(r'\$\s*([\d\.,]+)', line)
                    
                    if code_match:
                        code = code_match.group(1)
                        
                        # If price is on the same line
                        raw_price = None
                        if price_match:
                            raw_price = price_match.group(1)
                        
                        # If we have a code, we try to form a product
                        # The description is likely what was in the buffer before this line
                        # or the text on the same line before "COD:"
                        
                        # Clean up the line to get description part if on same line
                        line_content = line
                        if code_match:
                            line_content = line_content.replace(code_match.group(0), '')
                        if price_match:
                            line_content = line_content.replace(price_match.group(0), '')
                        
                        current_line_desc = line_content.strip()
                        
                        # Combine buffer and current line for full description
                        full_description = " ".join(description_buffer + [current_line_desc]).strip()
                        
                        # Reset buffer after finding a product
                        description_buffer = []
                        
                        product_data = {
                            "code": code,
                            "description": full_description,
                            "raw_price": raw_price,
                            "price_value": _parse_price(raw_price) if raw_price else 0.0,
                            "page": page_num + 1
                        }
                        products.append(product_data)
                        
                    elif price_match and not code_match:
                        # If we find a price but no code on this line, it might belong to the previous product
                        # OR it's a standalone price line.
                        # For this specific catalog, prices seem to be near codes.
                        # We'll add this line to description buffer for now, 
                        # but if we just found a product without a price, we might attach it there.
                        if products and products[-1]['raw_price'] is None:
                             raw_price = price_match.group(1)
                             products[-1]['raw_price'] = raw_price
                             products[-1]['price_value'] = _parse_price(raw_price)
                        else:
                             description_buffer.append(line.strip())
                    else:
                        # Just text, add to buffer
                        # Limit buffer size to avoid carrying over too much garbage
                        if len(description_buffer) > 5:
                            description_buffer.pop(0)
                        description_buffer.append(line.strip())
                        
    except Exception as e:
        logger.error(f"Error parsing PDF: {str(e)}")
        raise e
        
    return products

def _parse_price(price_str: str) -> float:
    """
    Converts a price string like "1.200,50" or "1,200.50" into a float.
    
    Args:
        price_str (str): The price string.
        
    Returns:
        float: The numeric value.
    """
    if not price_str:
        return 0.0
    
    clean_str = price_str.replace('$', '').strip()
    
    # Handle European/South American format: 1.200,50 (dot for thousands, comma for decimals)
    # vs US format: 1,200.50 (comma for thousands, dot for decimals)
    
    if ',' in clean_str and '.' in clean_str:
        if clean_str.find(',') > clean_str.find('.'):
             # 1.200,50 -> Remove dot, replace comma with dot
             clean_str = clean_str.replace('.', '').replace(',', '.')
        else:
             # 1,200.50 -> Remove comma
             clean_str = clean_str.replace(',', '')
    elif ',' in clean_str:
        # 1200,50 -> Replace comma with dot
        clean_str = clean_str.replace(',', '.')
    # If only dots, usually it's thousands separator in this context (e.g. 1.200) 
    # UNLESS it's a small number like 10.50. 
    # Given the catalog context (prices > 1000 often), we need to be careful.
    # But standardizing on "remove thousands separator, ensure decimal is dot" is best.
    
    try:
        return float(clean_str)
    except ValueError:
        return 0.0

import io
