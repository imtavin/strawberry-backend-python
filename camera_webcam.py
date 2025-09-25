import cv2
import datetime

class CameraHandler:
    def __init__(self, config):
        camcfg = config["camera"]
        self.cap = cv2.VideoCapture(camcfg.get("device_index", 0))
        self.preview_size = tuple(camcfg.get("preview_size", [640, 480]))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.preview_size[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.preview_size[1])
        if "target_fps" in camcfg:
            try:
                self.cap.set(cv2.CAP_PROP_FPS, float(camcfg["target_fps"]))
            except Exception:
                pass
        if not self.cap.isOpened():
            raise RuntimeError("❌ Não foi possível abrir a câmera")
        self.last_frame = None
        self.jpeg_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(camcfg.get("jpeg_quality", 80))]

    def capture_frame(self):
        ok, frame = self.cap.read()
        if not ok or frame is None:
            return None, None
        self.last_frame = frame.copy()
        ok, buffer = cv2.imencode(".jpg", frame, self.jpeg_params)
        if not ok:
            return None, None
        return frame, buffer.tobytes()

    def save_photo(self, path_dir="."):
        if self.last_frame is not None:
            filename = datetime.datetime.now().strftime("foto_%Y%m%d_%H%M%S.jpg")
            full = f"{path_dir.rstrip('/')}/{filename}"
            cv2.imwrite(full, self.last_frame)
            print(f"💾 Foto salva: {full}")

    def release(self):
        try:
            self.cap.release()
        finally:
            try:
                cv2.destroyAllWindows()
            except Exception:
                pass
