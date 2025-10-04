import cv2
import datetime
import os
from utils.logger import camera_logger

class CameraHandler:
    def __init__(self, config):
        try:
            camcfg = config["camera"]
            device_index = camcfg.get("device_index", 0)
            self.preview_size = tuple(camcfg.get("preview_size", [640, 480]))
            self.jpeg_quality = int(camcfg.get("jpeg_quality", 80))
            self.jpeg_params = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
            
            # Inicializar câmera
            self.cap = cv2.VideoCapture(device_index)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.preview_size[0])
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.preview_size[1])
            
            # Configurar FPS se especificado
            if "target_fps" in camcfg:
                try:
                    target_fps = float(camcfg["target_fps"])
                    self.cap.set(cv2.CAP_PROP_FPS, target_fps)
                    camera_logger.info(f"FPS configurado para: {target_fps}")
                except Exception as e:
                    camera_logger.warning(f"Não foi possível configurar FPS: {e}")
            
            # Verificar se câmera abriu
            if not self.cap.isOpened():
                error_msg = f"Não foi possível abrir a câmera (device_index: {device_index})"
                camera_logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            self.last_frame = None
            
            # Log das configurações
            actual_width = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            actual_height = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
            
            camera_logger.info(
                f"Webcam OpenCV inicializada | "
                f"Device: {device_index} | "
                f"Resolução: {actual_width}x{actual_height} | "
                f"FPS: {actual_fps:.1f} | "
                f"JPEG Quality: {self.jpeg_quality}"
            )
            
        except Exception as e:
            camera_logger.error(f"Erro na inicialização da webcam: {e}")
            raise

    def capture_frame(self):
        try:
            ok, frame = self.cap.read()
            if not ok or frame is None:
                camera_logger.warning("Falha ao capturar frame da webcam")
                return None, None
            
            self.last_frame = frame.copy()
            ok, buffer = cv2.imencode(".jpg", frame, self.jpeg_params)
            
            if not ok:
                camera_logger.warning("Falha ao codificar frame JPEG da webcam")
                return None, None
            
            return frame, buffer.tobytes()
            
        except Exception as e:
            camera_logger.error(f"Erro na captura de frame: {e}")
            return None, None

    def save_photo(self, path_dir="."):
        if self.last_frame is not None:
            try:
                os.makedirs(path_dir, exist_ok=True)
                filename = datetime.datetime.now().strftime("foto_%Y%m%d_%H%M%S.jpg")
                full_path = os.path.join(path_dir, filename)
                success = cv2.imwrite(full_path, self.last_frame)
                
                if success:
                    camera_logger.info(f"Foto salva: {full_path}")
                else:
                    camera_logger.error(f"Falha ao salvar foto: {full_path}")
                    
            except Exception as e:
                camera_logger.error(f"Erro ao salvar foto: {e}")
        else:
            camera_logger.warning("Tentativa de salvar foto sem frame disponível")

    def release(self):
        try:
            self.cap.release()
            camera_logger.info("Webcam OpenCV liberada")
        except Exception as e:
            camera_logger.error(f"Erro ao liberar webcam: {e}")
        finally:
            try:
                cv2.destroyAllWindows()
                camera_logger.debug("Janelas OpenCV fechadas")
            except Exception as e:
                camera_logger.debug(f"Erro ao fechar janelas: {e}")