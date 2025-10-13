#!/usr/bin/env python3
"""
Teste específico para problemas de serialização JSON
"""

import sys
import os
import json
import numpy as np
from pathlib import Path

# Adiciona o diretório pai ao path
sys.path.insert(0, str(Path(__file__).parent))

def test_numpy_serialization():
    """Testa problemas comuns de serialização com numpy"""
    print("🧪 TESTE DE SERIALIZAÇÃO NUMPY -> JSON")
    print("=" * 50)
    
    # Casos de teste problemáticos
    test_cases = [
        {"label": "test", "confidence": np.float64(95.5), "class_index": np.int64(3)},
        {"array": np.array([1, 2, 3]), "scalar": np.int32(42)},
        {"nested": {"value": np.float32(1.5), "list": [np.int16(1), np.int16(2)]}},
    ]
    
    for i, case in enumerate(test_cases):
        print(f"\n📦 Caso {i+1}: {case}")
        
        try:
            # Tentativa direta (deve falhar)
            result = json.dumps(case)
            print("❌ ERRO: Serialização direta funcionou (não deveria)")
        except TypeError as e:
            print(f"✅ Comportamento esperado: {e}")
        
        # Tentativa com conversão
        try:
            def convert_types(obj):
                if hasattr(obj, 'item'):
                    return obj.item()
                elif isinstance(obj, (list, tuple)):
                    return [convert_types(i) for i in obj]
                elif isinstance(obj, dict):
                    return {k: convert_types(v) for k, v in obj.items()}
                else:
                    return obj
            
            safe_case = convert_types(case)
            result = json.dumps(safe_case)
            print(f"✅ Serialização segura: {result}")
            
        except Exception as e:
            print(f"❌ Falha na serialização segura: {e}")

def test_ml_service_inference():
    """Testa a inferência do MLService especificamente"""
    print("\n🎯 TESTE ESPECÍFICO DO ML SERVICE")
    print("=" * 50)
    
    try:
        from services.ml_service import MLService
        from core.config import ConfigManager
        
        config = ConfigManager()
        ml_service = MLService(config)
        
        # Cria um frame de teste (150x150x3)
        test_frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        
        print("🖼️  Frame de teste criado")
        
        # Executa inferência
        result = ml_service.infer(test_frame)
        
        if result:
            print(f"✅ Inferência bem-sucedida: {result}")
            
            # Testa serialização
            try:
                json_result = json.dumps(result)
                print(f"✅ Serialização JSON bem-sucedida: {json_result}")
            except Exception as e:
                print(f"❌ Falha na serialização: {e}")
        else:
            print("❌ Inferência falhou ou retornou None")
            
    except Exception as e:
        print(f"❌ Erro no teste do ML Service: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_numpy_serialization()
    test_ml_service_inference()
    print("\n🎉 TESTE DE SERIALIZAÇÃO CONCLUÍDO")