import cv2
import time
import datetime
import pickle
import os
from picamera import PiCamera
from picamera.array import PiRGBArray


class CameraHandler:
    """
    Handler para Raspberry Pi Camera (picamera).
    - preview_size: tamanho do frame enviado ao frontend
    - jpeg_quality: qualidade do JPEG (60–95 típico; default 80)
    - target_fps: fps desejado (opcional; nem todos os modos suportam)
    - demais parâmetros vêm do config["camera"] (iso, awb_mode, etc.)
    """

    def __init__(self, config):
        camcfg = config["camera"]

        # Configs principais
        self.preview_size = tuple(camcfg.get("preview_size", [640, 480]))
        self.resolution = tuple(camcfg.get("resolution", [2592, 1944]))
        self.jpeg_quality = int(camcfg.get("jpeg_quality", 80))
        self.jpeg_params = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
        self.target_fps = float(camcfg.get("target_fps", 0))  # 0 = não força

        # Instancia câmera
        self.camera = PiCamera()
        self.camera.resolution = self.resolution

        # FPS (algumas combinações resolução/fps não são suportadas)
        if self.target_fps > 0:
            try:
                self.camera.framerate = self.target_fps
            except Exception:
                # Se não suportar, seguirá com o framerate padrão do modo selecionado
                pass

        # Demais parâmetros de imagem
        if "iso" in camcfg:
            self.camera.iso = camcfg["iso"]
        if "exposure_mode" in camcfg:
            self.camera.exposure_mode = camcfg["exposure_mode"]
        if "meter_mode" in camcfg:
            self.camera.meter_mode = camcfg.get("meter_mode", "average")
        if "awb_mode" in camcfg:
            self.camera.awb_mode = camcfg["awb_mode"]
        if "rotation" in camcfg:
            self.camera.rotation = int(camcfg["rotation"])
        if "hflip" in camcfg:
            self.camera.hflip = bool(camcfg["hflip"])
        if "vflip" in camcfg:
            self.camera.vflip = bool(camcfg["vflip"])
        if "video_stabilization" in camcfg:
            self.camera.video_stabilization = bool(camcfg["video_stabilization"])

        # AWB/AGC settle
        time.sleep(2)

        # Buffer para captura e último frame para save_photo()
        self.raw_capture = PiRGBArray(self.camera, size=self.preview_size)
        self.last_frame = None

        print(
            f"📷 PiCamera iniciada | res={self.resolution[0]}x{self.resolution[1]} | "
            f"preview={self.preview_size[0]}x{self.preview_size[1]} | "
            f"jpeg_quality={self.jpeg_quality}"
            + (f" | fps={self.target_fps}" if self.target_fps > 0 else "")
        )

    def capture_frame(self):
        """
        Captura um frame usando o video_port (rápido), redimensionado para preview_size,
        comprime em JPEG (qualidade configurável) e serializa (pickle) para envio.
        Retorna: (frame_bgr, bytes_serializados)
        """
        self.raw_capture.truncate(0)
        self.camera.capture(
            self.raw_capture,
            format="bgr",
            use_video_port=True,
            resize=self.preview_size,
        )
        frame = self.raw_capture.array
        self.last_frame = frame.copy()

        # Codifica JPEG com qualidade configurável
        ok, buffer = cv2.imencode(".jpg", frame, self.jpeg_params)
        if not ok:
            raise RuntimeError("❌ Falha ao codificar frame em JPEG")

        data = pickle.dumps(buffer)
        return frame, data

    def capture_preview_stream(self):
        """
        Gerador (opcional) para quem preferir um loop iterável.
        Rende (frame_bgr, bytes_serializados).
        """
        for frame_data in self.camera.capture_continuous(
            self.raw_capture,
            format="bgr",
            use_video_port=True,
            resize=self.preview_size,
        ):
            frame = frame_data.array
            self.last_frame = frame.copy()

            ok, buffer = cv2.imencode(".jpg", frame, self.jpeg_params)
            if not ok:
                self.raw_capture.truncate(0)
                continue

            ok, buffer = cv2.imencode(".jpg", frame, self.jpeg_params)
            if not ok:
                raise RuntimeError("❌ Falha ao codificar frame em JPEG")
            yield frame, buffer.tobytes()  

    def save_photo(self, path_dir="."):
        """Salva o último frame (BGR) em disco."""
        if self.last_frame is not None:
            os.makedirs(path_dir, exist_ok=True)
            filename = datetime.datetime.now().strftime("foto_%Y%m%d_%H%M%S.jpg")
            fullpath = os.path.join(path_dir, filename)
            cv2.imwrite(fullpath, self.last_frame)
            print(f"💾 Foto salva: {fullpath}")

    def release(self):
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        try:
            self.camera.close()
        except Exception:
            pass

