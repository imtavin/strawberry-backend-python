import cv2
import time
import datetime
import os
from picamera import PiCamera
from picamera.array import PiRGBArray

class CameraHandler:
    def __init__(self, config):
        camcfg = config["camera"]
        self.preview_size = tuple(camcfg.get("preview_size", [640, 480]))
        self.resolution = tuple(camcfg.get("resolution", [2592, 1944]))
        self.jpeg_quality = int(camcfg.get("jpeg_quality", 80))
        self.jpeg_params = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
        self.target_fps = float(camcfg.get("target_fps", 0))

        self.camera = PiCamera()
        self.camera.resolution = self.resolution
        if self.target_fps > 0:
            try:
                self.camera.framerate = self.target_fps
            except Exception:
                pass
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

        time.sleep(2)  # settle
        self.raw_capture = PiRGBArray(self.camera, size=self.preview_size)
        self.last_frame = None

        print(
            f"📷 PiCamera | res={self.resolution[0]}x{self.resolution[1]} | "
            f"preview={self.preview_size[0]}x{self.preview_size[1]} | "
            f"jpeg_quality={self.jpeg_quality}" + (f" | fps={self.target_fps}" if self.target_fps > 0 else "")
        )

    def capture_frame(self):
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
            return None, None
        return frame, buffer.tobytes()

    def save_photo(self, path_dir="."):
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
