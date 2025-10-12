import json
import time
import threading
import os
import platform
import numpy as np
import cv2
from pathlib import Path 
from wifi_manager import WiFiManager
import subprocess

# === Raiz do projeto e config ===
ROOT = Path(__file__).resolve().parents[1]            # ...\strawberry-ai
CONFIG_PATH = ROOT / "config.json"

from server_module import TCPServerHandler, UDPStreamer, CameraServer
from utils.logger import main_logger, camera_logger, server_logger, ml_logger, log_system_info

def _load_tflite_interpreter(model_path: str):
    import os

    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Modelo TFLite não encontrado: {model_path}")

    # Escolhe dinamicamente o backend correto do TFLite
    Interpreter = None
    last_err = None

    # 1) TensorFlow completo (caminho suportado nas versões recentes)
    try:
        from tensorflow.lite.python.interpreter import Interpreter as TFInterpreter  # type: ignore
        Interpreter = TFInterpreter
        ml_logger.info("Backend TFLite: tensorflow.lite.python.interpreter")
    except Exception as e_tf:
        last_err = e_tf
        # 2) Fallback para tflite-runtime (pode não existir no Windows)
        try:
            from tflite_runtime.interpreter import Interpreter as RTInterpreter  # type: ignore
            Interpreter = RTInterpreter
            ml_logger.info("Backend TFLite: tflite_runtime.interpreter (fallback)")
        except Exception as e_rt:
            raise ImportError(
                "Nenhum backend TFLite disponível. Instale TensorFlow (>=2.14) "
                "ou tflite-runtime compatível com seu SO/Python."
            ) from (last_err or e_rt)

    # Instancia e aloca tensores
    interpreter = Interpreter(model_path=model_path)
    interpreter.allocate_tensors()
    ml_logger.info(f"Modelo TFLite carregado: {model_path}")
    ml_logger.info(f"Interpreter módulo: {interpreter.__class__.__module__}")
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
    
    wifi_manager = WiFiManager()

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
    tflite_rel = ml_cfg.get("model_path", "backend/morganaAI/MorganaAI.tflite")
    tflite_path = str((ROOT / tflite_rel).resolve())
    print(f"Tentando carregar modelo em: {tflite_path}")

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

                elif cmd == "GET_INFO":
                    # Enviar informações da Raspberry
                    tcp_server._send_raspberry_info()
                    server_logger.info(" Solicitação de informações da Raspberry atendida")

                elif cmd.startswith("WIFI_CONNECT:"):
                    # Conectar a rede Wi-Fi
                    try:
                        _, ssid, password = cmd.split(":", 2)
                        server_logger.info(f"Tentando conectar ao Wi-Fi: {ssid}")
                        
                        result = wifi_manager.connect_to_wifi(ssid, password)
                        
                        if result["success"]:
                            tcp_server.send_text(f"WIFI:SUCCESS:{result['message']}")
                            server_logger.info(f" Wi-Fi conectado: {ssid}")
                        else:
                            tcp_server.send_text(f"WIFI:FAILED:{result['message']}")
                            server_logger.error(f" Falha Wi-Fi: {result['message']}")
                            
                    except Exception as e:
                        error_msg = f"Erro no comando Wi-Fi: {e}"
                        tcp_server.send_text(f"WIFI:ERROR:{error_msg}")
                        server_logger.error(error_msg)

                elif cmd == "RESTART_SERVICE":
                    # Reiniciar serviço
                    server_logger.info("Reiniciando serviço...")
                    try:
                        subprocess.run(["sudo", "systemctl", "restart", "strawberry-ai"], check=True)
                        tcp_server.send_text("SERVICE:RESTARTED")
                        server_logger.info(" Serviço reiniciado")
                    except Exception as e:
                        error_msg = f"Erro ao reiniciar serviço: {e}"
                        tcp_server.send_text(f"SERVICE:ERROR:{error_msg}")
                        server_logger.error(error_msg)

                elif cmd == "SHOW_LOGS":
                    # Mostrar logs
                    server_logger.info("Solicitação de logs recebida")
                    try:
                        # Enviar últimas linhas de log
                        result = subprocess.run(
                            ["tail", "-20", "/var/log/strawberry-ai.log"], 
                            capture_output=True, 
                            text=True
                        )
                        if result.returncode == 0:
                            tcp_server.send_text(f"LOGS:{result.stdout}")
                        else:
                            tcp_server.send_text("LOGS:Erro ao ler logs")
                    except Exception as e:
                        tcp_server.send_text(f"LOGS:Erro: {e}")

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