import json
import time
import threading
import os
import platform
import numpy as np
import cv2

from server_module import TCPServerHandler, UDPStreamer, CameraServer
from utils.logger import main_logger, camera_logger, server_logger, ml_logger, log_system_info

def _load_tflite_interpreter(model_path: str):
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Modelo TFLite não encontrado: {model_path}")
    try:
        from tflite_runtime.interpreter import Interpreter
        ml_logger.info("Usando tflite_runtime")
    except ImportError:
        from tensorflow.lite import Interpreter
        ml_logger.info("Usando tensorflow.lite (fallback)")
    
    interpreter = Interpreter(model_path=model_path)
    interpreter.allocate_tensors()
    ml_logger.info(f"Modelo TFLite carregado: {model_path}")
    return interpreter

def _softmax(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float32)
    x = x - np.max(x)
    e = np.exp(x)
    s = e / np.sum(e)
    return s

def _preprocess_for_tflite(img_bgr: np.ndarray, input_details, norm: str = "uint8"):
    h, w, c = input_details[0]['shape'][1], input_details[0]['shape'][2], input_details[0]['shape'][3]
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, (w, h), interpolation=cv2.INTER_LINEAR)

    if input_details[0]['dtype'] == np.uint8 and norm == "uint8":
        tensor = resized.astype(np.uint8)
    else:
        tensor = resized.astype(np.float32) / 255.0

    tensor = np.expand_dims(tensor, axis=0)
    ml_logger.debug(f"Imagem pré-processada: shape={tensor.shape}, dtype={tensor.dtype}")
    return tensor

def _load_camera_handler(CONFIG):
    cam_type = CONFIG.get("camera", {}).get("type")
    if cam_type is None:
        cam_type = "picamera" if "raspberrypi" in platform.platform().lower() else "opencv"
    
    camera_logger.info(f"Tipo de câmera detectado: {cam_type}")
    
    if cam_type.lower() == "picamera":
        from camera_module import CameraHandler
        camera_logger.info("Usando PiCamera (Raspberry Pi)")
    else:
        from camera_webcam import CameraHandler
        camera_logger.info("Usando OpenCV (Webcam)")
    return CameraHandler

def main():
    # Log informações do sistema
    log_system_info()
    
    # 1) Carrega config
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            CONFIG = json.load(f)
        main_logger.info("Configuração carregada com sucesso")
    except Exception as e:
        main_logger.error(f"Erro ao carregar config.json: {e}")
        return

    # Detecta transporte desejado para o VÍDEO do frontend
    video_cfg = CONFIG.get("video", {})
    transport = (video_cfg.get("transport") or "udp").lower()
    use_udp = (transport == "udp")
    main_logger.info(f"Transporte de vídeo: {transport.upper()}")

    # 2) Inicializa câmera e servidores
    try:
        CameraHandler = _load_camera_handler(CONFIG)
        camera = CameraHandler(CONFIG)
        camera_logger.info("Câmera inicializada com sucesso")
    except Exception as e:
        camera_logger.error(f"Erro ao inicializar câmera: {e}")
        return

    try:
        tcp_server = TCPServerHandler(CONFIG)
        server_logger.info("Servidor TCP inicializado")
    except Exception as e:
        server_logger.error(f"Erro ao inicializar servidor TCP: {e}")
        return

    # Só ligue o streamer UDP se o transporte for UDP
    udp_streamer = UDPStreamer(CONFIG) if use_udp else None
    if udp_streamer:
        server_logger.info("Streamer UDP inicializado")

    frame_tcp_cfg = CONFIG.get("frame_tcp", {"enabled": False, "host": "127.0.0.1", "port": 5050})
    jpeg_server = CameraServer(
        host=frame_tcp_cfg.get("host", "127.0.0.1"),
        port=int(frame_tcp_cfg.get("port", 5050)),
        enabled=bool(frame_tcp_cfg.get("enabled", False)),
    )
    jpeg_server.start()
    
    if frame_tcp_cfg.get('enabled', False):
        server_logger.info(f"Servidor TCP-JPEG ativo em {frame_tcp_cfg.get('host')}:{frame_tcp_cfg.get('port')}")

    # Configuração ML
    ml_cfg = CONFIG.get("ml", {})
    tflite_path = ml_cfg.get("model_path", "MorganaAI.tflite")
    labels = ml_cfg.get("labels", [])
    input_norm = ml_cfg.get("input_norm", "auto")

    interpreter = None
    input_details = output_details = None
    
    try:
        interpreter = _load_tflite_interpreter(tflite_path)
        input_details = interpreter.get_input_details()
        output_details = interpreter.get_output_details()
        
        ml_logger.info(f"Modelo carregado: {tflite_path}")
        ml_logger.info(f"Input: shape={input_details[0]['shape']}, dtype={input_details[0]['dtype']}")
        ml_logger.info(f"Output: shape={output_details[0]['shape']}, dtype={output_details[0]['dtype']}")
        ml_logger.info(f"Labels disponíveis: {len(labels)}")
        
    except Exception as e:
        ml_logger.error(f"Falha ao carregar modelo TFLite: {e}")
        ml_logger.warning("CAPTURE enviará apenas a foto salva (sem inferência)")

    # 3) Thread para capturar e enviar frames (vídeo)
    def stream_loop():
        target_fps = float(CONFIG["camera"].get("target_fps", 15))
        delay = 1.0 / max(1.0, target_fps)
        frame_count = 0
        
        while True:
            try:
                frame, frame_bytes = camera.capture_frame()
                if frame_bytes:
                    frame_count += 1
                    
                    # Log a cada 100 frames para não poluir
                    if frame_count % 100 == 0:
                        camera_logger.debug(f"Frames enviados: {frame_count}")
                    
                    jpeg_server.broadcast(frame_bytes)
                    if udp_streamer is not None:
                        udp_streamer.send_frame(frame_bytes)
                else:
                    camera_logger.warning("Frame vazio capturado")
                    
                time.sleep(delay)
                
            except Exception as e:
                camera_logger.error(f"Erro no envio de frame: {e}")
                time.sleep(0.05)

    threading.Thread(target=stream_loop, daemon=True, name="StreamLoop").start()
    main_logger.info(f"Sistema iniciado | TCP=Comandos | UDP={'Ativo' if use_udp else 'Inativo'} | TCP-JPEG={'Ativo' if frame_tcp_cfg.get('enabled') else 'Inativo'}")

    try:
        command_count = 0
        while True:
            # Aceita reconexões TCP
            if tcp_server.poll_accept():
                server_logger.info("Novo cliente TCP conectado")

            # Lê comandos do frontend/cliente
            cmd = tcp_server.receive_command()
            if cmd is not None:
                command_count += 1
                server_logger.info(f"Comando #{command_count} recebido: {cmd}")

                if cmd.startswith("REGISTER_UDP:"):
                    if udp_streamer is not None:
                        try:
                            udp_port = int(cmd.split(":")[1])
                            client_ip = tcp_server.addr[0]
                            udp_streamer.add_client((client_ip, udp_port))
                            server_logger.info(f"Cliente UDP registrado: {client_ip}:{udp_port}")
                        except Exception as e:
                            server_logger.error(f"Falha ao registrar cliente UDP: {e}")
                    else:
                        server_logger.warning("Comando REGISTER_UDP recebido, mas UDP está desativado")

                elif cmd in ("FOTO", "CAPTURE"):
                    camera_logger.info("Comando de captura recebido")
                    
                    # Salvar foto
                    try:
                        camera.save_photo(os.getcwd())
                        camera_logger.info("Foto salva com sucesso")
                    except Exception as e:
                        camera_logger.error(f"Erro ao salvar foto: {e}")

                    # Inferência ML
                    if interpreter is not None and hasattr(camera, "last_frame") and camera.last_frame is not None:
                        try:
                            ml_logger.info("Iniciando inferência ML")
                            
                            if input_norm == "auto":
                                norm_mode = "uint8" if input_details[0]['dtype'] == np.uint8 else "float32_0_1"
                            else:
                                norm_mode = input_norm
                                
                            ml_logger.debug(f"Normalização: {norm_mode}")

                            inp = _preprocess_for_tflite(camera.last_frame, input_details, norm=norm_mode)
                            interpreter.set_tensor(input_details[0]['index'], inp)
                            interpreter.invoke()
                            out = interpreter.get_tensor(output_details[0]['index'])
                            out = np.squeeze(out)

                            # Aplica softmax se necessário
                            if np.max(out) > 1.0 or np.min(out) < 0.0:
                                probs = _softmax(out)
                                ml_logger.debug("Softmax aplicado na saída")
                            else:
                                probs = out.astype(np.float32)
                                s = np.sum(probs)
                                if s > 0:
                                    probs = probs / s

                            cls_idx = int(np.argmax(probs))
                            conf = float(probs[cls_idx])

                            if labels and 0 <= cls_idx < len(labels):
                                label = labels[cls_idx]
                            else:
                                label = f"class_{cls_idx}"

                            result = {"label": label, "confidence": round(conf * 100.0, 2)}
                            ml_logger.info(f"Inferência concluída: {label} ({conf*100:.1f}%)")
                            
                            # Envia resultado
                            tcp_server.send_text(json.dumps(result))
                            server_logger.info(f"Resultado enviado: {result}")

                        except Exception as e:
                            ml_logger.error(f"Erro na inferência TFLite: {e}")
                            tcp_server.send_text(json.dumps({"label": "erro_inferencia", "confidence": 0.0}))
                    else:
                        ml_logger.warning("Inferência não realizada: modelo não carregado ou frame indisponível")
                        tcp_server.send_text(json.dumps({"label": "capturado", "confidence": 0.0}))

                else:
                    server_logger.debug(f"Comando não tratado: {cmd}")

            time.sleep(0.001)

    except KeyboardInterrupt:
        main_logger.info("Encerramento solicitado via Ctrl+C")
    except Exception as e:
        main_logger.critical(f"Erro crítico no loop principal: {e}")
    finally:
        main_logger.info("Iniciando cleanup...")
        try:
            camera.release()
            camera_logger.info("Câmera liberada")
        except Exception as e:
            camera_logger.error(f"Erro ao liberar câmera: {e}")
            
        try:
            tcp_server.close()
            server_logger.info("Servidor TCP fechado")
        except Exception as e:
            server_logger.error(f"Erro ao fechar servidor TCP: {e}")
            
        try:
            if udp_streamer is not None:
                udp_streamer.stop()
                server_logger.info("Streamer UDP parado")
        except Exception as e:
            server_logger.error(f"Erro ao parar streamer UDP: {e}")
            
        try:
            jpeg_server.stop()
            server_logger.info("Servidor JPEG parado")
        except Exception as e:
            server_logger.error(f"Erro ao parar servidor JPEG: {e}")
            
        main_logger.info("Strawberry AI finalizado")

if __name__ == "__main__":
    main()