import cv2
import time
import datetime
import os
from picamera import PiCamera
from picamera.array import PiRGBArray
from utils.logger import camera_logger

class CameraHandler:
    def __init__(self, config):
        try:
            camcfg = config["camera"]
            self.preview_size = tuple(camcfg.get("preview_size", [640, 480]))
            self.resolution = tuple(camcfg.get("resolution", [2592, 1944]))
            self.jpeg_quality = int(camcfg.get("jpeg_quality", 80))
            self.jpeg_params = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
            self.target_fps = float(camcfg.get("target_fps", 0))

            # Inicializar PiCamera
            self.camera = PiCamera()
            self.camera.resolution = self.resolution
            
            # Configurar FPS
            if self.target_fps > 0:
                try:
                    self.camera.framerate = self.target_fps
                    camera_logger.info(f"FPS da PiCamera configurado para: {self.target_fps}")
                except Exception as e:
                    camera_logger.warning(f"Não foi possível configurar FPS: {e}")

            # Configurações da câmera
            config_settings = {
                'iso': camcfg.get("iso"),
                'exposure_mode': camcfg.get("exposure_mode"),
                'meter_mode': camcfg.get("meter_mode", "average"),
                'awb_mode': camcfg.get("awb_mode"),
                'rotation': int(camcfg.get("rotation", 0)),
                'hflip': bool(camcfg.get("hflip", False)),
                'vflip': bool(camcfg.get("vflip", False)),
                'video_stabilization': bool(camcfg.get("video_stabilization", False))
            }
            
            settings_applied = []
            for key, value in config_settings.items():
                if value is not None:
                    try:
                        setattr(self.camera, key, value)
                        settings_applied.append(f"{key}={value}")
                    except Exception as e:
                        camera_logger.warning(f"Erro ao configurar {key}: {e}")

            # Aguardar câmera estabilizar
            time.sleep(2)
            self.raw_capture = PiRGBArray(self.camera, size=self.preview_size)
            self.last_frame = None

            # Log das configurações
            camera_logger.info(
                f"PiCamera inicializada | "
                f"Resolução: {self.resolution[0]}x{self.resolution[1]} | "
                f"Preview: {self.preview_size[0]}x{self.preview_size[1]} | "
                f"JPEG Quality: {self.jpeg_quality} | "
                f"FPS: {self.target_fps if self.target_fps > 0 else 'auto'} | "
                f"Configs: {', '.join(settings_applied)}"
            )

        except Exception as e:
            camera_logger.error(f"Erro na inicialização da PiCamera: {e}")
            raise

    def capture_frame(self):
        try:
            self.raw_capture.truncate(0)
            self.camera.capture(
                self.raw_capture,
                format="bgr",
                use_video_port=True,
                resize=self.preview_size,
            )
            frame = self.raw_capture.array
            self.last_frame = frame.copy()
            ok, buffer = cv2.imencode(".jpg", frame, self.jpeg_params)
            
            if not ok:
                camera_logger.warning("Falha ao codificar frame JPEG da PiCamera")
                return None, None
                
            return frame, buffer.tobytes()
            
        except Exception as e:
            camera_logger.error(f"Erro na captura de frame da PiCamera: {e}")
            return None, None

    def save_photo(self, path_dir="."):
        if self.last_frame is not None:
            try:
                os.makedirs(path_dir, exist_ok=True)
                filename = datetime.datetime.now().strftime("foto_%Y%m%d_%H%M%S.jpg")
                fullpath = os.path.join(path_dir, filename)
                cv2.imwrite(fullpath, self.last_frame)
                camera_logger.info(f"Foto salva: {fullpath}")
            except Exception as e:
                camera_logger.error(f"Erro ao salvar foto: {e}")
        else:
            camera_logger.warning("Tentativa de salvar foto sem frame disponível")

    def release(self):
        try:
            cv2.destroyAllWindows()
            camera_logger.debug("Janelas OpenCV fechadas")
        except Exception as e:
            camera_logger.debug(f"Erro ao fechar janelas: {e}")
            
        try:
            self.camera.close()
            camera_logger.info("PiCamera fechada")
        except Exception as e:
            camera_logger.error(f"Erro ao fechar PiCamera: {e}")