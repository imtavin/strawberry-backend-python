import json
import time
import os
import numpy as np
import cv2
from contextlib import contextmanager
from typing import Optional, Dict, Any

# Cache para configurações e recursos
_CONFIG_CACHE: Optional[Dict[str, Any]] = None
_INTERPRETER_CACHE: Optional[Any] = None

class PerformanceOptimizer:
    """Otimizador de performance com reutilização de buffers"""
    
    def __init__(self):
        self._frame_buffer = None
        self._tensor_buffer = None
        self._softmax_buffer = None
        
    def get_frame_buffer(self, shape, dtype=np.uint8):
        """Reutiliza ou cria buffer para frames"""
        if self._frame_buffer is None or self._frame_buffer.shape != shape:
            self._frame_buffer = np.empty(shape, dtype=dtype)
        return self._frame_buffer
    
    def get_tensor_buffer(self, shape, dtype=np.float32):
        """Reutiliza buffer para tensores"""
        if self._tensor_buffer is None or self._tensor_buffer.shape != shape:
            self._tensor_buffer = np.empty(shape, dtype=dtype)
        return self._tensor_buffer

# Instância global do otimizador
_PERF_OPTIMIZER = PerformanceOptimizer()

@contextmanager
def timer_context(description: str, logger, threshold: float = 0.1):
    """Context manager para medição de performance"""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        if elapsed > threshold:
            logger.warning(f"{description} levou {elapsed:.3f}s")

def cached_load_config():
    """Carrega configuração com cache"""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        with open("config.json", "r", encoding="utf-8") as f:
            _CONFIG_CACHE = json.load(f)
    return _CONFIG_CACHE

def _load_tflite_interpreter(model_path: str):
    """Versão otimizada com cache e lazy loading"""
    global _INTERPRETER_CACHE
    
    if _INTERPRETER_CACHE is not None:
        return _INTERPRETER_CACHE
        
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Modelo TFLite não encontrado: {model_path}")

    # Tentativa otimizada de importação
    try:
        from tensorflow.lite.python.interpreter import Interpreter
    except ImportError:
        try:
            from tflite_runtime.interpreter import Interpreter
        except ImportError:
            raise ImportError("Nenhum backend TFLite disponível")

    with timer_context("Carregamento do modelo TFLite", ml_logger):
        interpreter = Interpreter(model_path=model_path)
        interpreter.allocate_tensors()
        _INTERPRETER_CACHE = interpreter
        
    return interpreter

def _optimized_softmax(x: np.ndarray) -> np.ndarray:
    """Softmax otimizado com operações in-place"""
    x = x.astype(np.float32, copy=False)
    x -= np.max(x)
    np.exp(x, out=x)
    x /= np.sum(x)
    return x

def _preprocess_for_tflite_optimized(img_bgr: np.ndarray, input_details, norm: str = "uint8"):
    """Pré-processamento otimizado com reutilização de buffers"""
    h, w = input_details[0]['shape'][1:3]
    
    # Redimensionamento direto sem conversão RGB se possível
    if input_details[0]['dtype'] == np.uint8 and norm == "uint8":
        # Otimização: redimensionar direto se o modelo aceitar BGR
        resized = cv2.resize(img_bgr, (w, h), interpolation=cv2.INTER_LINEAR)
        tensor = resized.astype(np.uint8, copy=False)
    else:
        # Apenas converter se necessário
        rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        resized = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_LINEAR)
        tensor = resized.astype(np.float32) / 255.0

    return np.expand_dims(tensor, axis=0)