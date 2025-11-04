import time
import threading
import json
from typing import Dict, Any, Optional

import cv2
from utils.logger import main_logger

from core.config import ConfigManager
from services.camera_service import CameraService
from services.ml_service import MLService
from services.wifi_service import WiFiService
from protocols.command_handlers import SystemCommandHandler
from services.system_service import ServiceManager
from protocols.tcp_server import TCPServerHandler
from protocols.udp_streamer import UDPStreamer
from protocols.frame_server import CameraServer
from utils.photo_manager import PhotoManager

class StrawberryAIApp:
    def __init__(self):
        self.config = ConfigManager()
        self.is_running = False
        
        # Serviços
        self.camera_service: Optional[CameraService] = None
        self.ml_service: Optional[MLService] = None
        self.wifi_service: Optional[WiFiService] = None
        self.service_manager: Optional[ServiceManager] = None
        
        # Protocolos
        self.tcp_server: Optional[TCPServerHandler] = None
        self.udp_streamer: Optional[UDPStreamer] = None
        self.frame_server: Optional[CameraServer] = None
        self.command_handler: Optional[SystemCommandHandler] = None

        self.photo_manager = PhotoManager()
        
        # Estatísticas
        self.stats = {
            'commands_processed': 0,
            'frames_streamed': 0,
            'inferences': 0
        }

    def initialize(self) -> bool:
        """Inicializa todos os componentes"""
        try:
            main_logger.info("Inicializando serviços...")
            
            # Inicializa serviços na ordem correta
            self.camera_service = CameraService(self.config)
            self.ml_service = MLService(self.config)
            self.wifi_service = WiFiService()
            self.service_manager = ServiceManager("strawberry-ai")
            
            # Inicializa command handler
            self.command_handler = SystemCommandHandler(
                self.wifi_service, 
                self.service_manager
            )
            
            # Inicializa protocolos de rede
            self._initialize_network_services()
            
            # Configura callbacks
            self._setup_callbacks()
            
            main_logger.info("Aplicação inicializada com sucesso")
            return True
            
        except Exception as e:
            main_logger.error(f"Falha na inicialização: {e}")
            import traceback
            main_logger.error(traceback.format_exc())
            return False

    def _initialize_network_services(self) -> None:
        """Inicializa serviços de rede"""
        main_logger.info("Inicializando serviços de rede...")
        
        # TCP Server para comandos
        try:
            self.tcp_server = TCPServerHandler(self.config)
            self.tcp_server.set_command_handler(self._handle_command)
            main_logger.info("Servidor TCP inicializado")
        except Exception as e:
            main_logger.error(f"Erro no servidor TCP: {e}")
            raise
        
        # UDP Streamer (condicional)
        use_udp = self.config.get('video.transport', 'tcp').lower() == 'udp'
        if use_udp:
            try:
                self.udp_streamer = UDPStreamer(self.config)
                main_logger.info("Streamer UDP inicializado")
            except Exception as e:
                main_logger.error(f"Erro no streamer UDP: {e}")
        else:
            main_logger.info("📡 Streamer UDP desativado (usando TCP)")
        
        # Frame Server TCP para vídeo 
        try:
            use_tcp = self.config.get('video.transport', 'tcp').lower() == 'tcp'
            self.frame_server = CameraServer(
                host='127.0.0.1',
                port=5050,
                enabled=use_tcp  
            )
            if use_tcp:
                self.frame_server.start()
                main_logger.info("Servidor de frames TCP inicializado")
            else:
                main_logger.info("Servidor de frames TCP desativado (usando UDP)")
        except Exception as e:
            main_logger.error(f"Erro no servidor de frames: {e}")
            if use_tcp:  # Só levanta exceção se era para estar habilitado
                raise

    def _setup_callbacks(self) -> None:
        """Configura callbacks entre componentes"""
        main_logger.info("Configurando callbacks...")
        
        if self.camera_service:
            # Configura callback para frames
            self.camera_service.set_frame_callback(self._handle_frame_callback)

            # Inicia o streaming com FPS configurado
            fps = self.config.get('camera.target_fps', 15)
            self.camera_service.start_streaming(fps)

            main_logger.info("Callback de frames configurado")
        else:
            main_logger.error("Serviço de câmera não disponível para callback")

    def _handle_frame_callback(self, frame_bytes: bytes) -> None:
        """Callback para frames capturados"""
        if not frame_bytes:
            return
            
        # Atualiza estatísticas
        self.stats['frames_streamed'] += 1
        
        # Log informativo do primeiro frame
        if self.stats['frames_streamed'] == 1:
            main_logger.info(f"🎥 Primeiro frame capturado: {len(frame_bytes)} bytes")
        
        # Envia para servidor de frames (TCP)
        if self.frame_server and self.frame_server.enabled:
            try:
                self.frame_server.broadcast(frame_bytes)  
                if self.stats['frames_streamed'] == 1:
                    main_logger.info("🎥 Primeiro frame enviado para broadcast")
            except Exception as e:
                main_logger.error(f"Erro no broadcast para frame_server: {e}")
        
        # Envia via UDP se disponível
        if self.udp_streamer:
            try:
                self.udp_streamer.send_frame(frame_bytes)
            except Exception as e:
                main_logger.debug(f"Erro no envio UDP: {e}")

    def _handle_command(self, command: str, client_addr: tuple) -> None:
        """Processa comandos recebidos"""
        self.stats['commands_processed'] += 1
        
        main_logger.debug(f"📨 Comando recebido: {command[:100]}...")
        
        # Tenta processar com system command handler primeiro
        if self.command_handler and self.command_handler.handle_command(command, self.tcp_server):
            return
        
        # Comandos legados
        command_handlers = {
            'REGISTER_UDP': self._handle_register_udp,
            'FOTO': self._handle_capture,
            'CAPTURE': self._handle_capture,
            'GET_INFO': self._handle_get_info,
            'WIFI_CONNECT': self._handle_wifi_connect,
            'RESTART_SERVICE': self._handle_restart_service,
            'SHOW_LOGS': self._handle_show_logs,
            'UPDATE_CAMERA_CONFIG': self._handle_update_camera_config,
        }
        
        # Encontra o handler apropriado
        for cmd_prefix, handler in command_handlers.items():
            if command.startswith(cmd_prefix):
                handler(command, client_addr)
                return
        
        main_logger.warning(f"Comando não reconhecido: {command}")

    def _handle_capture(self, command: str, client_addr: tuple) -> None:
        """Handler otimizado para captura + inferência assíncrona"""
        main_logger.info("🔄 Processando comando de captura...")
        
        # Obtém frame atual
        current_frame = None
        if self.camera_service:
            current_frame = self.camera_service.get_last_frame()
        
        if current_frame is None:
            main_logger.warning("❌ Nenhum frame disponível para captura")
            fallback_result = json.dumps({"label": "sem_frame", "confidence": 0.0})
            if self.tcp_server:
                self.tcp_server.send_text(fallback_result)
            return
        
        # Cria cópia para processamento assíncrono
        frame_copy = current_frame.copy()
        
        def async_capture_worker():
            try:
                # Executa inferência
                inference_result = self._perform_inference(frame_copy)
                
                # Salva foto com nome formatado (assíncrono)
                if inference_result:
                    save_success = self.photo_manager.save_photo_with_inference(
                        frame_copy, inference_result
                    )
                    if save_success:
                        main_logger.info("✅ Foto salva com sucesso")
                    else:
                        main_logger.error("❌ Falha ao salvar foto")
                
                # Envia resultado para frontend
                self._send_inference_result(inference_result)
                
            except Exception as e:
                main_logger.error(f"❌ Erro no worker assíncrono: {e}")
                self._send_error_result()

        # Inicia processamento em background
        threading.Thread(target=async_capture_worker, daemon=True).start()
        
        # Resposta imediata para não travar frontend
        immediate_response = json.dumps({
            "status": "processando", 
            "message": "Analisando imagem..."
        })
        if self.tcp_server:
            self.tcp_server.send_text(immediate_response)
        
        main_logger.info("✅ Captura assíncrona iniciada")

    def _perform_inference(self, frame) -> dict:
        """Executa inferência ML de forma isolada"""
        try:
            if self.ml_service:
                main_logger.info("🧠 Executando inferência ML...")
                inference_result = self.ml_service.infer(frame)
                
                if inference_result:
                    self.stats['inferences'] += 1
                    label = inference_result.get("label", "indeterminado")
                    confidence = inference_result.get("confidence", 0.0)
                    main_logger.info(f"✅ Inferência concluída: {label} ({confidence:.2%})")
                    return inference_result
                else:
                    main_logger.warning("⚠️ Inferência retornou resultado vazio")
                    return {"label": "indeterminado", "confidence": 0.0}
            else:
                main_logger.warning("⚠️ Serviço ML não disponível")
                return {"label": "sem_ia", "confidence": 0.0}
                
        except Exception as e:
            main_logger.error(f"❌ Erro na inferência: {e}")
            return {"label": "erro_inferencia", "confidence": 0.0}

    def _send_inference_result(self, inference_result: dict):
        """Envia resultado para frontend"""
        try:
            result_json = json.dumps(inference_result)
            main_logger.info(f"📤 Enviando resultado: {inference_result}")
            
            if self.tcp_server and result_json:
                success = self.tcp_server.send_text(result_json)
                if success:
                    main_logger.info("✅ Resultado enviado para frontend")
                else:
                    main_logger.error("❌ Falha ao enviar resultado")
            else:
                main_logger.error("❌ Servidor TCP não disponível")
                
        except Exception as e:
            main_logger.error(f"❌ Erro no envio do resultado: {e}")

    def _send_error_result(self):
        """Envia resultado de erro"""
        try:
            error_result = json.dumps({"label": "erro_processamento", "confidence": 0.0})
            if self.tcp_server:
                self.tcp_server.send_text(error_result)
        except Exception as e:
            main_logger.error(f"❌ Erro ao enviar resultado de erro: {e}")

    def _handle_register_udp(self, command: str, client_addr: tuple) -> None:
        """Handler para registro UDP"""
        if self.udp_streamer:
            try:
                udp_port = int(command.split(":")[1])
                self.udp_streamer.add_client((client_addr[0], udp_port))
                main_logger.info(f"Cliente UDP registrado: {client_addr[0]}:{udp_port}")
            except (ValueError, IndexError) as e:
                main_logger.error(f"Porta UDP inválida: {e}")

    def _handle_get_info(self, command: str, client_addr: tuple) -> None:
        """Handler para informações do sistema"""
        if self.tcp_server:
            self.tcp_server._send_raspberry_info()
            main_logger.info("Informações da Raspberry enviadas")

    def _handle_wifi_connect(self, command: str, client_addr: tuple) -> None:
        """Handler para conexão Wi-Fi"""
        if self.wifi_service:
            try:
                _, ssid, password = command.split(":", 2)
                main_logger.info(f"📡 Tentando conectar ao Wi-Fi: {ssid}")
                
                result = self.wifi_service.connect_to_wifi(ssid, password)
                
                response = (
                    f"WIFI:SUCCESS:{result['message']}" 
                    if result['success'] 
                    else f"WIFI:FAILED:{result['message']}"
                )
                self.tcp_server.send_text(response)
                main_logger.info(f"Resposta Wi-Fi enviada: {result['success']}")
                
            except ValueError as e:
                error_msg = f"WIFI:ERROR:Formato de comando inválido {e}"
                self.tcp_server.send_text(error_msg)
                main_logger.error(f"{error_msg}")

    def _handle_restart_service(self, command: str, client_addr: tuple) -> None:
        """Handler para reiniciar serviço"""
        try:
            main_logger.info("🔄 Reiniciando serviço...")
            import subprocess
            result = subprocess.run(
                ["sudo", "systemctl", "restart", "strawberry-ai"], 
                capture_output=True, 
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                self.tcp_server.send_text("SERVICE:RESTARTED:Sucesso")
                main_logger.info("Serviço reiniciado com sucesso")
            else:
                error_msg = f"SERVICE:ERROR:{result.stderr}"
                self.tcp_server.send_text(error_msg)
                main_logger.error(f"Erro ao reiniciar serviço: {result.stderr}")
                
        except Exception as e:
            error_msg = f"SERVICE:ERROR:{e}"
            self.tcp_server.send_text(error_msg)
            main_logger.error(f"Erro ao reiniciar serviço: {e}")

    def _handle_update_camera_config(self, command: str, client_addr: tuple) -> None:
        """Handler para atualizar configuração da câmera via frontend"""
        try:
            main_logger.info("🎛️  Recebendo comando para atualizar configuração da câmera")
            
            # Extrai JSON da configuração
            config_str = command.split(':', 1)[1]
            camera_updates = json.loads(config_str)
            
            main_logger.info(f"📋 Configurações recebidas: {list(camera_updates.keys())}")
            
            # Valida configurações
            valid_settings = [
                'preview_size', 'target_fps', 'jpeg_quality', 'rotation',
                'brightness', 'contrast', 'saturation', 'sharpness',
                'exposure_mode', 'awb_mode', 'meter_mode'
            ]
            
            filtered_updates = {}
            for key, value in camera_updates.items():
                if key in valid_settings:
                    filtered_updates[key] = value
                else:
                    main_logger.warning(f"Configuração inválida ignorada: {key}")
            
            if not filtered_updates:
                error_msg = "Nenhuma configuração válida fornecida"
                main_logger.error(error_msg)
                if self.tcp_server:
                    self.tcp_server.send_text(json.dumps({
                        "status": "error", 
                        "message": error_msg
                    }))
                return
            
            # Atualiza configuração global
            success = self.config.update_camera_config(filtered_updates)
            
            if success:
                # Aplica configuração na câmera em tempo real
                if self.camera_service:
                    camera_success = self.camera_service.update_camera_config(filtered_updates)
                    
                    if camera_success:
                        response = json.dumps({
                            "status": "success", 
                            "message": "Configuração da câmera atualizada com sucesso",
                            "applied_settings": list(filtered_updates.keys())
                        })
                        main_logger.info("✅ Configuração da câmera aplicada com sucesso")
                    else:
                        response = json.dumps({
                            "status": "warning", 
                            "message": "Configuração salva mas não aplicada na câmera"
                        })
                else:
                    response = json.dumps({
                        "status": "success", 
                        "message": "Configuração salva, será aplicada na próxima inicialização"
                    })
            else:
                response = json.dumps({
                    "status": "error", 
                    "message": "Falha ao salvar configuração"
                })
        
            # Envia resposta
            if self.tcp_server:
                self.tcp_server.send_text(response)
                
        except json.JSONDecodeError as e:
            error_msg = f"JSON inválido: {e}"
            main_logger.error(error_msg)
            if self.tcp_server:
                self.tcp_server.send_text(json.dumps({
                    "status": "error", 
                    "message": error_msg
                }))
        except Exception as e:
            error_msg = f"Erro ao processar configuração: {e}"
            main_logger.error(error_msg)
            if self.tcp_server:
                self.tcp_server.send_text(json.dumps({
                    "status": "error", 
                    "message": error_msg
                }))

    def _handle_show_logs(self, command: str, client_addr: tuple) -> None:
        """Handler para mostrar logs"""
        try:
            main_logger.info("Solicitando logs do sistema...")
            import subprocess
            
            # Tenta vários arquivos de log
            log_files = [
                "/var/log/strawberry-ai.log",
                "/tmp/strawberry-ai.log",
                "logs/app.log"
            ]
            
            logs = ""
            for log_file in log_files:
                try:
                    result = subprocess.run(
                        ["sudo", "tail", "-50", log_file], 
                        capture_output=True, 
                        text=True,
                        timeout=10
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        logs = result.stdout
                        break
                except:
                    continue
            
            if not logs:
                logs = "Nenhum log encontrado nos locais habituais"
                
            self.tcp_server.send_text(f"LOGS:{logs}")
            main_logger.info("Logs enviados para o cliente")
            
        except Exception as e:
            error_msg = f"LOGS:Erro: {e}"
            self.tcp_server.send_text(error_msg)
            main_logger.error(f"Erro ao obter logs: {e}")

    def run(self) -> None:
        """Executa a aplicação principal"""
        self.is_running = True
        main_logger.info("🚀 Aplicação Strawberry AI em execução")
        
        try:
            while self.is_running:
                # Processa comandos TCP
                if self.tcp_server:
                    try:
                        command = self.tcp_server.receive_command()
                        if command:
                            self._handle_command(command, self.tcp_server.addr)
                    except Exception as e:
                        main_logger.error(f"Erro no processamento de comando: {e}")
                
                # Pequena pausa para não consumir CPU
                time.sleep(0.001)
                
        except KeyboardInterrupt:
            main_logger.info("Encerramento solicitado")
        except Exception as e:
            main_logger.critical(f"Erro crítico: {e}")
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Desliga a aplicação de forma limpa"""
        self.is_running = False
        main_logger.info("Iniciando shutdown...")
        
        # Para serviços na ordem correta
        services_to_stop = [
            (self.camera_service, "Serviço de câmera"),
            (self.udp_streamer, "Streamer UDP"),
            (self.frame_server, "Servidor de frames"),
            (self.tcp_server, "Servidor TCP"),
        ]
        
        for service, name in services_to_stop:
            if service:
                try:
                    if hasattr(service, 'stop'):
                        service.stop()
                    elif hasattr(service, 'close'):
                        service.close()
                    main_logger.info(f"{name} parado")
                except Exception as e:
                    main_logger.error(f"Erro ao parar {name}: {e}")
        
        main_logger.info(f"📊 Shutdown completo. Estatísticas: {self.stats}")