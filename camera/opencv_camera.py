import cv2
import numpy as np
import datetime
import os
from typing import Tuple, Optional
from .camera_base import BaseCamera
from utils.logger import camera_logger

class OpenCVCamera(BaseCamera):
    def __init__(self, config: dict):
        super().__init__(config)
        self.cap: Optional[cv2.VideoCapture] = None
        self.jpeg_quality = config.get("jpeg_quality", 80)
        self.jpeg_params = [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
        self._initialize_camera()

    def _initialize_camera(self) -> None:
        """Inicializa câmera OpenCV"""
        cam_config = self.config
        device_index = cam_config.get("device_index", 0)
        preview_size = tuple(cam_config.get("preview_size", [640, 480]))
        
        camera_logger.info(f"Inicializando câmera OpenCV - Device: {device_index}")
        
        try:
            self.cap = cv2.VideoCapture(device_index)
            
            if not self.cap.isOpened():
                # Tenta outros índices de dispositivo
                for i in range(1, 5):
                    self.cap = cv2.VideoCapture(i)
                    if self.cap.isOpened():
                        device_index = i
                        camera_logger.info(f"Câmera encontrada no dispositivo: {i}")
                        break
                else:
                    raise RuntimeError("Não foi possível abrir câmera em nenhum dispositivo")
            
            # Configurações da câmera
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, preview_size[0])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, preview_size[1])
            
            # Configura FPS se especificado
            target_fps = cam_config.get("target_fps")
            if target_fps:
                self.cap.set(cv2.CAP_PROP_FPS, target_fps)
            
            # Obtém configurações reais
            actual_width = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            actual_height = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
            
            camera_logger.info(
                f"Câmera OpenCV inicializada | "
                f"Device: {device_index} | "
                f"Resolução: {actual_width}x{actual_height} | "
                f"FPS: {actual_fps:.1f} | "
                f"JPEG Quality: {self.jpeg_quality}"
            )
            
        except Exception as e:
            camera_logger.error(f" Erro na inicialização da câmera OpenCV: {e}")
            if self.cap:
                self.cap.release()
            raise

    def capture_frame(self) -> Tuple[Optional[np.ndarray], Optional[bytes]]:
        """Captura frame da câmera OpenCV"""
        if not self.cap:
            return None, None
            
        try:
            ret, frame = self.cap.read()
            if not ret or frame is None:
                camera_logger.warning(" Falha ao capturar frame da câmera")
                return None, None
            
            self.last_frame = frame.copy()
            self.frame_count += 1
            
            # Codifica para JPEG
            ret, buffer = cv2.imencode(".jpg", frame, self.jpeg_params)
            if not ret:
                camera_logger.warning(" Falha ao codificar frame JPEG")
                return frame, None
            
            frame_bytes = buffer.tobytes()
            
            # Log do primeiro frame e a cada 100 frames
            if self.frame_count == 1:
                camera_logger.info(f"🎥 Primeiro frame capturado: {len(frame_bytes)} bytes")
            elif self.frame_count % 100 == 0:
                camera_logger.debug(f"📊 Frames capturados: {self.frame_count}")
                
            return frame, frame_bytes
            
        except Exception as e:
            camera_logger.error(f" Erro na captura de frame: {e}")
            return None, None

    def save_photo(self, directory: str = ".") -> bool:
        """Salva foto atual"""
        if self.last_frame is not None:
            try:
                os.makedirs(directory, exist_ok=True)
                filename = datetime.datetime.now().strftime("foto_%Y%m%d_%H%M%S.jpg")
                full_path = os.path.join(directory, filename)
                
                success = cv2.imwrite(full_path, self.last_frame)
                if success:
                    camera_logger.info(f"📸 Foto salva: {full_path}")
                    return True
                else:
                    camera_logger.error(f" Falha ao salvar foto: {full_path}")
                    return False
                    
            except Exception as e:
                camera_logger.error(f" Erro ao salvar foto: {e}")
                return False
        else:
            camera_logger.warning(" Tentativa de salvar foto sem frame disponível")
            return False

    def release(self) -> None:
        """Libera recursos da câmera"""
        if self.cap:
            try:
                self.cap.release()
                camera_logger.info(" Câmera OpenCV liberada")
            except Exception as e:
                camera_logger.error(f" Erro ao liberar câmera: {e}")
            finally:
                self.cap = None
        
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass

    def get_stats(self) -> dict:
        """Retorna estatísticas da câmera"""
        return {
            "frames_captured": self.frame_count,
            "has_last_frame": self.last_frame is not None,
            "camera_open": self.cap is not None and self.cap.isOpened()
        }