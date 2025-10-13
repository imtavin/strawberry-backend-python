"""
Utilitários para conversão segura de tipos numpy para Python
"""

import numpy as np
from typing import Any, Dict, List, Union

def convert_numpy_types(obj: Any) -> Any:
    """
    Converte recursivamente tipos numpy para tipos Python nativos
    """
    if obj is None:
        return None
    
    # Tipos numpy escalares
    if isinstance(obj, (np.integer)):
        return int(obj)
    elif isinstance(obj, (np.floating)):
        return float(obj)
    elif isinstance(obj, (np.bool_)):
        return bool(obj)
    elif isinstance(obj, (np.str_)):
        return str(obj)
    
    # Arrays numpy
    elif isinstance(obj, np.ndarray):
        return obj.tolist()  # Converte array para lista
    
    # Estruturas de dados
    elif isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_numpy_types(item) for item in obj)
    
    # Tipos Python nativos - retorna como estão
    else:
        return obj

def safe_json_serialize(obj: Any) -> str:
    """
    Serializa objeto para JSON de forma segura, convertendo tipos numpy
    """
    import json
    safe_obj = convert_numpy_types(obj)
    return json.dumps(safe_obj)

def ensure_python_types(obj: Any) -> Any:
    """
    Garante que todos os valores em uma estrutura são tipos Python nativos
    """
    return convert_numpy_types(obj)