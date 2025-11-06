import numpy as np
import cv2
import json
from typing import Dict, Any, Optional, Tuple
from utils.logger import ml_logger
from utils.type_helpers import convert_numpy_types, ensure_python_types
import os
from pathlib import Path

class MLService:
    def __init__(self, config_manager):
        self.config = config_manager
        self.interpreter = None
        self.input_details = None
        self.output_details = None
        self.labels = []
        self.translations = {}  # ✅ Traduções para português
        self.default_label = "Não identificado"  # ✅ Fallback
        self.confidence_threshold = 0.6  # ✅ Limiar padrão (60%)
        self._initialize_model()
        ensure_python_types = convert_numpy_types

    # =====================================================
    # =============== INICIALIZAÇÃO DO MODELO ==============
    # =====================================================
    def _initialize_model(self) -> None:
        """Inicializa o modelo TFLite de forma otimizada"""
        try:
            model_path = self._resolve_model_path()
            self.interpreter = self._load_interpreter(model_path)
            self.input_details = self.interpreter.get_input_details()
            self.output_details = self.interpreter.get_output_details()
            self.labels = self.config.get('ml.labels', [])
            self._load_label_translations()  # ✅ Carrega traduções e fallback

            # ✅ Lê threshold configurável do config.json (se existir)
            self.confidence_threshold = self.config.get("ml.confidence_threshold", 0.6)

            # Obtém o tamanho REAL do modelo
            input_shape = self.input_details[0]['shape']
            self.target_size = (input_shape[1], input_shape[2])  # (height, width)
            
            ml_logger.info(
                f"✅ Modelo carregado: shape={input_shape}, "
                f"tamanho_entrada={self.target_size}, "
                f"labels={len(self.labels)}"
            )
            
        except Exception as e:
            ml_logger.error(f"❌ Falha ao carregar modelo: {e}")
            self.interpreter = None

    # =====================================================
    # ================= TRADUÇÕES E CONFIG =================
    # =====================================================
    def _load_label_translations(self):
        """Carrega traduções e fallback do config.json"""
        try:
            self.translations = self.config.get("ml.translations", {})
            self.default_label = self.config.get("ml.default_label", "Não identificado")
            ml_logger.info(f"Traduções carregadas ({len(self.translations)} mapeamentos)")
        except Exception as e:
            ml_logger.error(f"Falha ao carregar traduções: {e}")
            self.translations = {}
            self.default_label = "Não identificado"

    # =====================================================
    # ==================== UTILITÁRIOS =====================
    # =====================================================
    def _resolve_model_path(self) -> str:
        """Resolve caminho absoluto do modelo dentro do backend"""
        # Caminho base do backend (subindo dois níveis a partir de services/)
        backend_root = Path(__file__).resolve().parent.parent
        model_rel_path = self.config.get('ml.model_path', 'morganaAI/MorganaAI.tflite')
        model_abs_path = backend_root / model_rel_path

        if not model_abs_path.exists():
            raise FileNotFoundError(f"Modelo não encontrado em: {model_abs_path}")

        return str(model_abs_path)


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
        x = x.astype(np.float64)
        x = x - np.max(x)  # Para estabilidade numérica
        exp_x = np.exp(x)
        return exp_x / np.sum(exp_x)

    def _aplicar_filtros_treinamento(self, img: np.ndarray) -> np.ndarray:
        """
        Aplica os MESMOS filtros usados no treinamento
        """
        try:
            # 1. CLAHE (igual ao seu código de treino)
            lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            l = clahe.apply(l)
            lab = cv2.merge((l, a, b))
            img = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
            
            # 2. Sharpen (igual ao seu código de treino)
            kernel = np.array([[0,-1,0], [-1,5,-1], [0,-1,0]])
            img = cv2.filter2D(img, -1, kernel)
            
        except Exception as e:
            ml_logger.warning(f"⚠️ Erro ao aplicar filtros: {e}")
        
        return img

    # =====================================================
    # ==================== PRÉ-PROCESSO ====================
    # =====================================================
    def preprocess_frame(self, frame: np.ndarray) -> np.ndarray:
        """Pré-processa frame para inferência de forma consistente com o treino"""
        if self.input_details is None:
            raise RuntimeError("❌ Modelo não inicializado")

        # Usa o tamanho REAL do modelo
        h, w = self.target_size

        # Redimensiona para o tamanho EXATO do treinamento
        resized = cv2.resize(frame, (w, h), interpolation=cv2.INTER_LINEAR)
        
        # Aplica os mesmos filtros do treinamento
        processed = self._aplicar_filtros_treinamento(resized)

        input_detail = self.input_details[0]
        
        if input_detail['dtype'] == np.uint8:
            tensor = cv2.cvtColor(processed, cv2.COLOR_BGR2RGB).astype(np.uint8)
        else:
            tensor = cv2.cvtColor(processed, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0

        return np.expand_dims(tensor, axis=0)

    # =====================================================
    # ==================== INFERÊNCIA ======================
    # =====================================================
    def infer(self, frame: np.ndarray) -> Optional[Dict[str, Any]]:
        """Executa inferência no frame"""
        if self.interpreter is None:
            ml_logger.error("Interpreter não inicializado")
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

            # Nome técnico da classe
            label = (
                self.labels[class_idx]
                if 0 <= class_idx < len(self.labels)
                else f"class_{class_idx}"
            )

            # ================== LIMIAR DE CONFIANÇA ==================
            # Se confiança for muito baixa, assume "Não identificado"
            if confidence < self.confidence_threshold:
                label = "unknown"
                translated_label = self.default_label
            else:
                translated_label = self.translations.get(label, self.default_label)

            # Resultado estruturado
            result = {
                "label": label,  # nome técnico (ex: gray_mold)
                "label_pt": translated_label,  # nome legível (ex: Mofo Cinzento)
                "confidence": round(confidence * 100.0, 2),
                "class_index": class_idx
            }
                
            # Conversão segura
            safe_result = ensure_python_types(result)

            ml_logger.info(f"Inferência concluída: {safe_result}")
            ml_logger.info(f"[DEBUG] Label retornada pelo modelo: '{label}'")
            ml_logger.info(f"[DEBUG] Tradução encontrada: '{self.translations.get(label)}'")

            return safe_result

        except Exception as e:
            ml_logger.error(f"Erro na inferência: {e}")
        return None

    # =====================================================
    # ==================== PÓS-PROCESSO ====================
    # =====================================================
    def _postprocess_output(self, output: np.ndarray) -> np.ndarray:
        """Aplica pós-processamento na saída do modelo"""
        try:
            output_sum = np.sum(output)
            
            # Se já está normalizado, retorna direto
            if 0.99 <= output_sum <= 1.01 and np.min(output) >= 0 and np.max(output) <= 1:
                return output
            
            # Caso contrário, aplica softmax
            return self._softmax(output)
            
        except Exception as e:
            ml_logger.error(f"❌ Erro no pós-processamento: {e}")
            return output

    # =====================================================
    # ================== CONVERSÃO PYTHON ==================
    # =====================================================
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
