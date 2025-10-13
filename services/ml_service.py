import numpy as np
import cv2
from typing import Dict, Any, Optional, Tuple
from utils.logger import ml_logger
from utils.type_helpers import convert_numpy_types, ensure_python_types

class MLService:
    def __init__(self, config_manager):
        self.config = config_manager
        self.interpreter = None
        self.input_details = None
        self.output_details = None
        self.labels = []
        self._initialize_model()
        ensure_python_types = convert_numpy_types
    
    def _initialize_model(self) -> None:
        """Inicializa o modelo TFLite de forma otimizada"""
        try:
            model_path = self._resolve_model_path()
            self.interpreter = self._load_interpreter(model_path)
            self.input_details = self.interpreter.get_input_details()
            self.output_details = self.interpreter.get_output_details()
            self.labels = self.config.get('ml.labels', [])
            
            ml_logger.info(
                f"Modelo carregado: shape={self.input_details[0]['shape']}, "
                f"labels={len(self.labels)}"
            )
        except Exception as e:
            ml_logger.error(f"Falha ao carregar modelo: {e}")
            self.interpreter = None
    
    def _resolve_model_path(self) -> str:
        """Resolve o caminho absoluto do modelo"""
        model_rel_path = self.config.get('ml.model_path', 'backend/morganaAI/MorganaAI.tflite')
        return str((self.config.root_dir / model_rel_path).resolve())
    
    def _load_interpreter(self, model_path: str):
        """Carrega interpreter TFLite com fallback otimizado"""
        try:
            from tensorflow.lite.python.interpreter import Interpreter
            ml_logger.info("Usando backend TensorFlow Lite")
            interpreter = Interpreter(model_path=model_path)
        except ImportError:
            try:
                from tflite_runtime.interpreter import Interpreter
                ml_logger.info("Usando backend tflite-runtime (fallback)")
                interpreter = Interpreter(model_path=model_path)
            except ImportError as e:
                raise ImportError(
                    "Nenhum backend TFLite disponível. Instale TensorFlow ou tflite-runtime"
                ) from e
        
        interpreter.allocate_tensors()
        return interpreter
    
    def _softmax(self, x: np.ndarray) -> np.ndarray:
        """Calcula softmax numericamente estável"""
        x = x.astype(np.float32)
        x = x - np.max(x)  # Para estabilidade numérica
        exp_x = np.exp(x)
        return exp_x / np.sum(exp_x)
    
    def preprocess_frame(self, frame: np.ndarray) -> np.ndarray:
        """Pré-processa frame para inferência de forma otimizada"""
        if self.input_details is None:
            raise RuntimeError("Modelo não inicializado")
        
        input_detail = self.input_details[0]
        h, w = input_detail['shape'][1:3]
        
        # Redimensiona e converte cor em uma única operação
        resized = cv2.resize(frame, (w, h), interpolation=cv2.INTER_LINEAR)
        
        if input_detail['dtype'] == np.uint8:
            tensor = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.uint8)
        else:
            tensor = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        
        return np.expand_dims(tensor, axis=0)
    
    def infer(self, frame: np.ndarray) -> Optional[Dict[str, Any]]:
        """Executa inferência no frame"""
        if self.interpreter is None:
            return None
        
        try:
            # Pré-processamento
            input_tensor = self.preprocess_frame(frame)
            
            # Inferência
            self.interpreter.set_tensor(self.input_details[0]['index'], input_tensor)
            self.interpreter.invoke()
            output = self.interpreter.get_tensor(self.output_details[0]['index'])
            
            # Pós-processamento
            probabilities = self._postprocess_output(np.squeeze(output))
            class_idx = np.argmax(probabilities)
            confidence = float(probabilities[class_idx])
            
            # Resultado com conversão segura de tipos
            label = (
                self.labels[class_idx] 
                if 0 <= class_idx < len(self.labels) 
                else f"class_{class_idx}"
            )
            
            # Estrutura do resultado
            result = {
                "label": label,
                "confidence": round(confidence * 100.0, 2),
                "class_index": class_idx
            }
            
            # CONVERSÃO SEGURA PARA TIPOS PYTHON
            safe_result = ensure_python_types(result)
            
            ml_logger.info(f" Inferência concluída: {safe_result}")
            return safe_result
            
        except Exception as e:
            ml_logger.error(f" Erro na inferência: {e}")
        return None
    
    def _postprocess_output(self, output: np.ndarray) -> np.ndarray:
        """Aplica pós-processamento na saída do modelo"""
        if np.max(output) > 1.0 or np.min(output) < 0.0:
            return self._softmax(output)
        else:
            # Normaliza se já estiver em [0,1]
            sum_output = np.sum(output)
            return output / sum_output if sum_output > 0 else output

    def _ensure_python_types(self, obj: Any) -> Any:
        """Garante que todos os valores são tipos Python nativos - MÉTODO AUXILIAR"""
        if isinstance(obj, (np.integer)):
            return int(obj)
        elif isinstance(obj, (np.floating)):
            return float(obj)
        elif isinstance(obj, (np.ndarray)):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {k: self._ensure_python_types(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._ensure_python_types(item) for item in obj]
        else:
            return obj