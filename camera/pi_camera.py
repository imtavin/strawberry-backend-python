"""
Implementação unificada e estável para câmera CSI Raspberry Pi
Usa picamera2 (libcamera) - ÚNICA FORMA CONFIÁVEL NO RASPBERRY PI OS MODERNO
"""
import time
import threading
from typing import Tuple, Optional, Any
import numpy as np
import cv2

try:
    from picamera2 import Picamera2
    from libcamera import controls
    PICAMERA2_AVAILABLE = True
except ImportError:
    PICAMERA2_AVAILABLE = False
    print("⚠️  Picamera2 não disponível. Instale: sudo apt install python3-picamera2")

from .camera_base import BaseCamera
from utils.logger import camera_logger

class PiCameraUnified(BaseCamera):
    """
    Implementação unificada e robusta para câmera CSI Raspberry Pi
    Usa exclusivamente Picamera2 (libcamera) - método moderno e estável
    """
    
    def __init__(self, config: dict):
            
        super().__init__(config)
        self.picam2 = None
        self._initialized = False
        self._capture_lock = threading.Lock()
        
        # Configurações otimizadas
        self.preview_size = tuple(config.get("preview_size", [640, 480]))
        self.jpeg_quality = config.get("jpeg_quality", 80)
        self.fps = config.get("target_fps", 15)
        self.jpeg_params = [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
        
        self._initialize_camera()

    def _initialize_camera(self) -> None:
        """Inicialização robusta da câmera com Picamera2"""
        camera_logger.info("🚀 Inicializando câmera CSI com Picamera2 (libcamera)")
        
        max_retries = 3
        retry_delay = 2.0
        
        for attempt in range(max_retries):
            try:
                # Libera recursos anteriores
                if self.picam2:
                    try:
                        self.picam2.close()
                    except:
                        pass
                
                # Cria nova instância
                self.picam2 = Picamera2()
                
                # Configuração otimizada para baixa latência
                preview_config = self.picam2.create_preview_configuration(
                    main={
                        "size": self.preview_size,
                        "format": "RGB888"
                    },
                    controls={
                        "FrameRate": self.fps,
                        "AwbMode": controls.AwbModeEnum.Auto,
                        "AeEnable": True,
                        "ExposureTime": 10000,
                    }
                )
                
                self.picam2.configure(preview_config)
                self.picam2.start()
                
                # Aguarda aquecimento da câmera
                time.sleep(2.0)
                
                # Teste de captura
                test_frame = self.picam2.capture_array()
                if test_frame is not None and test_frame.size > 0:
                    self._initialized = True
                    camera_logger.info(f"✅ Câmera CSI inicializada com sucesso! Resolução: {test_frame.shape[1]}x{test_frame.shape[0]}")
                    return
                else:
                    raise RuntimeError("Frame de teste vazio")
                    
            except Exception as e:
                camera_logger.error(f"❌ Tentativa {attempt + 1}/{max_retries} falhou: {e}")
                if attempt < max_retries - 1:
                    camera_logger.info(f"🔄 Nova tentativa em {retry_delay}s...")
                    time.sleep(retry_delay)
                else:
                    raise RuntimeError(f"Falha após {max_retries} tentativas: {e}")

    def capture_frame(self) -> Tuple[Optional[np.ndarray], Optional[bytes]]:
        """Captura frame de forma thread-safe e otimizada"""
        if not self._initialized or not self.picam2:
            return None, None
            
        with self._capture_lock:
            try:
                # Captura direta do array numpy
                frame = self.picam2.capture_array()
                
                if frame is None or frame.size == 0:
                    camera_logger.warning("Frame vazio capturado")
                    return None, None
                
                # Garante que é RGB (Picamera2 retorna RGB888)
                if len(frame.shape) == 3 and frame.shape[2] == 3:
                    # Já está em RGB
                    pass
                else:
                    # Converte se necessário
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                self.last_frame = frame.copy()
                self.frame_count += 1
                
                # Codifica para JPEG
                success, jpeg_buffer = cv2.imencode(".jpg", frame, self.jpeg_params)
                
                if success:
                    jpeg_bytes = jpeg_buffer.tobytes()
                    
                    # Log periódico
                    if self.frame_count == 1:
                        camera_logger.info(f"📸 Primeiro frame capturado: {frame.shape[1]}x{frame.shape[0]} - {len(jpeg_bytes)} bytes")
                    elif self.frame_count % 100 == 0:
                        camera_logger.debug(f"📊 Frames capturados: {self.frame_count}")
                        
                    return frame, jpeg_bytes
                else:
                    camera_logger.warning("Falha ao codificar JPEG")
                    return frame, None
                    
            except Exception as e:
                camera_logger.error(f"❌ Erro na captura: {e}")
                return None, None

    def release(self) -> None:
        """Libera recursos de forma segura"""
        self._initialized = False
        
        if self.picam2:
            try:
                self.picam2.stop()
                self.picam2.close()
                camera_logger.info("✅ Câmera Picamera2 liberada com sucesso")
            except Exception as e:
                camera_logger.error(f"Erro ao liberar câmera: {e}")
            finally:
                self.picam2 = None

    def get_stats(self) -> dict:
        """Retorna estatísticas da câmera"""
        stats = super().get_stats()
        stats.update({
            "camera_type": "picamera2_unified",
            "initialized": self._initialized,
            "preview_size": self.preview_size,
            "fps": self.fps
        })
        return stats