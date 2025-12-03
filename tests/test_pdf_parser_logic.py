import sys
import os
import pytest

# Add app to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.pdf_parser import limpiar_precio

def test_limpiar_precio_standard():
    assert limpiar_precio("$ 1.200,50") == 1200.50
    assert limpiar_precio("1.200,50") == 1200.50
    assert limpiar_precio("1200,50") == 1200.50

def test_limpiar_precio_with_text():
    assert limpiar_precio("$ 1.200,50 + iva") == 1200.50
    assert limpiar_precio("PRECIO: 1.200,50 mas impuestos") == 1200.50
    assert limpiar_precio("USD 1.200,50") == 1200.50

def test_limpiar_precio_us_format():
    assert limpiar_precio("1,200.50") == 1200.50
    assert limpiar_precio("$1,200.50") == 1200.50

def test_limpiar_precio_thousands_only():
    assert limpiar_precio("1.200") == 1200.0
    assert limpiar_precio("1.000.000") == 1000000.0
    
def test_limpiar_precio_decimal_only():
    # Ambiguous case, but logic defaults to decimal if comma present
    assert limpiar_precio("10,50") == 10.50
    
def test_limpiar_precio_empty_or_invalid():
    assert limpiar_precio("") == 0.0
    assert limpiar_precio("Consultar") == 0.0
    assert limpiar_precio("N/A") == 0.0
