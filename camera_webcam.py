import cv2
import datetime
import pickle 

class CameraHandler:
    def __init__(self, config):
        self.config = config["camera"]
        self.cap = cv2.VideoCapture(0)
        self.preview_size = tuple(self.config["preview_size"])
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.preview_size[0])
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.preview_size[1])
        if not self.cap.isOpened():
            raise RuntimeError("❌ Não foi possível abrir a câmera")
        self.last_frame = None

    def capture_frame(self):
        ret, frame = self.cap.read()
        if not ret:
            return None, None
        self.last_frame = frame.copy()
        ok, buffer = cv2.imencode(".jpg", frame)
        if not ok:
            return None, None
        return frame, buffer.tobytes()

    def save_photo(self):
        if self.last_frame is not None:
            filename = datetime.datetime.now().strftime("foto_%Y%m%d_%H%M%S.jpg")
            cv2.imwrite(filename, self.last_frame)
            print(f"💾 Foto salva: {filename}")

    def release(self):
        self.cap.release()
        cv2.destroyAllWindows()