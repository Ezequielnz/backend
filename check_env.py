import os
import sys

print(f"Python Executable: {sys.executable}")
print(f"POPPLER env var: {os.getenv('POPPLER')}")
print(f"PATH: {os.getenv('PATH')}")

try:
    from pdf2image import convert_from_bytes
    print("pdf2image imported successfully")
except ImportError:
    print("pdf2image not installed")
