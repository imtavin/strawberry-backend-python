import cv2
import numpy as np
import threading
import time
from typing import Optional, Tuple, Callable
from utils.logger import camera_logger

class CameraService:
    def __init__(self, config_manager):
        self.config = config_manager
        self.camera_handler = None
        self.last_frame: Optional[np.ndarray] = None
        self.frame_lock = threading.Lock()
        self.is_streaming = False
        self.stream_callback: Optional[Callable] = None
        self._stream_thread: Optional[threading.Thread] = None
        
        self._initialize_camera()

    def _initialize_camera(self) -> None:
        """Inicializa a câmera baseada na configuração"""
        cam_config = self.config.get_camera_config()
        
        # Determina o tipo de câmera
        cam_type = cam_config.get('type', 'opencv')  # Default para opencv no Windows
        
        camera_logger.info(f"Inicializando câmera do tipo: {cam_type}")
        
        try:
            if cam_type.lower() == "picamera":
                # Para Raspberry Pi
                from camera.pi_camera import PiCamera
                self.camera_handler = PiCamera(cam_config)
            else:
                # Para Windows/OpenCV
                from camera.opencv_camera import OpenCVCamera
                self.camera_handler = OpenCVCamera(cam_config)
                
            camera_logger.info(f"Câmera {cam_type} inicializada com sucesso")
            
        except Exception as e:
            camera_logger.error(f"Erro ao inicializar câmera {cam_type}: {e}")
            # Fallback para OpenCV
            try:
                from camera.opencv_camera import OpenCVCamera
                self.camera_handler = OpenCVCamera(cam_config)
                camera_logger.info("Fallback para OpenCV bem-sucedido")
            except Exception as fallback_error:
                camera_logger.error(f"Fallback também falhou: {fallback_error}")
                raise

    def start_streaming(self, callback: Callable) -> None:
        """Inicia streaming em thread separada - CORRIGIDO"""
        if self.is_streaming:
            camera_logger.warning("Streaming já está em execução")
            return
        
        self.stream_callback = callback
        self.is_streaming = True
        
        # Configurações de performance
        target_fps = self.config.get('camera.target_fps', 15)
        frame_delay = 1.0 / max(1.0, target_fps)
        
        camera_logger.info(f"Iniciando streaming com {target_fps} FPS")
        
        def stream_loop():
            frame_count = 0
            consecutive_errors = 0
            max_consecutive_errors = 5
            
            while self.is_streaming:
                try:
                    # Captura frame
                    frame, frame_bytes = self.capture_frame()
                    
                    if frame is not None and frame_bytes is not None:
                        # Atualiza último frame de forma thread-safe
                        with self.frame_lock:
                            self.last_frame = frame.copy()
                        
                        # Chama callback com os dados do frame
                        if self.stream_callback:
                            self.stream_callback(frame_bytes)
                        
                        frame_count += 1
                        consecutive_errors = 0  # Reset error counter
                        
                        # Log a cada 30 frames para não poluir
                        if frame_count % 30 == 0:
                            camera_logger.debug(f"Frames processados: {frame_count}")
                    
                    else:
                        camera_logger.warning("Frame vazio capturado")
                        consecutive_errors += 1
                        
                    # Pequena pausa para controlar FPS
                    time.sleep(frame_delay)
                    
                    # Se muitos erros consecutivos, pausa mais longa
                    if consecutive_errors >= max_consecutive_errors:
                        camera_logger.error("Muitos erros consecutivos, pausando...")
                        time.sleep(1.0)
                        consecutive_errors = 0
                        
                except Exception as e:
                    consecutive_errors += 1
                    camera_logger.error(f"Erro no stream loop: {e}")
                    time.sleep(0.5)  # Pausa em caso de erro

        # Inicia thread de streaming
        self._stream_thread = threading.Thread(
            target=stream_loop, 
            daemon=True, 
            name="CameraStream"
        )
        self._stream_thread.start()
        
        camera_logger.info("Streaming de câmera iniciado")

    def capture_frame(self) -> Tuple[Optional[np.ndarray], Optional[bytes]]:
        """Captura frame de forma otimizada """
        if self.camera_handler is None:
            return None, None
        
        try:
            return self.camera_handler.capture_frame()
        except Exception as e:
            camera_logger.error(f"Erro ao capturar frame: {e}")
            return None, None

    def get_last_frame(self) -> Optional[np.ndarray]:
        """Obtém o último frame de forma thread-safe"""
        with self.frame_lock:
            return self.last_frame.copy() if self.last_frame is not None else None

    def save_photo(self, directory: str = ".") -> bool:
        """Salva foto atual"""
        try:
            if self.camera_handler:
                self.camera_handler.save_photo(directory)
                return True
            return False
        except Exception as e:
            camera_logger.error(f"Erro ao salvar foto: {e}")
            return False

    def stop(self) -> None:
        """Para o serviço de câmera"""
        self.is_streaming = False
        if self._stream_thread and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=2.0)
        
        if self.camera_handler:
            self.camera_handler.release()
        
        camera_logger.info("Serviço de câmera parado")