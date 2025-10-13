from abc import ABC, abstractmethod
from typing import Tuple, Optional
import cv2
import datetime
import os
from utils.logger import camera_logger

class BaseCamera(ABC):
    def __init__(self, config: dict):
        self.config = config
        self.last_frame: Optional['np.ndarray'] = None
        self.frame_count = 0
        
    @abstractmethod
    def capture_frame(self) -> Tuple[Optional['np.ndarray'], Optional[bytes]]:
        """Captura frame da câmera"""
        pass
    
    @abstractmethod
    def release(self) -> None:
        """Libera recursos da câmera"""
        pass
    
    def save_photo(self, directory: str = ".") -> bool:
        """Salva foto atual em disco"""
        if self.last_frame is None:
            camera_logger.warning("Tentativa de salvar foto sem frame disponível")
            return False
            
        try:
            os.makedirs(directory, exist_ok=True)
            filename = datetime.datetime.now().strftime("foto_%Y%m%d_%H%M%S.jpg")
            full_path = os.path.join(directory, filename)
            
            success = cv2.imwrite(full_path, self.last_frame)
            if success:
                camera_logger.info(f"Foto salva: {full_path}")
                return True
            else:
                camera_logger.error(f"Falha ao salvar foto: {full_path}")
                return False
                
        except Exception as e:
            camera_logger.error(f"Erro ao salvar foto: {e}")
            return False
    
    def get_stats(self) -> dict:
        """Retorna estatísticas da câmera"""
        return {
            "frames_captured": self.frame_count,
            "has_last_frame": self.last_frame is not None
        }