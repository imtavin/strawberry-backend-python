import time
import threading
import json
from typing import Dict, Any, Optional
from utils.logger import main_logger

from core.config import ConfigManager
from services.camera_service import CameraService
from services.ml_service import MLService
from services.wifi_service import WiFiService
from protocols.tcp_server import TCPServerHandler
from protocols.udp_streamer import UDPStreamer
from protocols.frame_server import CameraServer

class StrawberryAIApp:
    def __init__(self):
        self.config = ConfigManager()
        self.is_running = False
        
        # Serviços
        self.camera_service: Optional[CameraService] = None
        self.ml_service: Optional[MLService] = None
        self.wifi_service: Optional[WiFiService] = None
        
        # Protocolos
        self.tcp_server: Optional[TCPServerHandler] = None
        self.udp_streamer: Optional[UDPStreamer] = None
        self.frame_server: Optional[CameraServer] = None
        
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
            
            # Inicializa protocolos de rede
            self._initialize_network_services()
            
            # Configura callbacks - AGORA FUNCIONANDO
            self._setup_callbacks()
            
            main_logger.info(" Aplicação inicializada com sucesso")
            return True
            
        except Exception as e:
            main_logger.error(f" Falha na inicialização: {e}")
            import traceback
            main_logger.error(traceback.format_exc())
            return False

    def _initialize_network_services(self) -> None:
        """Inicializa serviços de rede"""
        main_logger.info("Inicializando serviços de rede...")
        
        # TCP Server para comandos
        try:
            self.tcp_server = TCPServerHandler(self.config)
            main_logger.info(" Servidor TCP inicializado")
        except Exception as e:
            main_logger.error(f" Erro no servidor TCP: {e}")
            raise
        
        # UDP Streamer (condicional)
        use_udp = self.config.get('video.transport', 'tcp').lower() == 'udp'
        if use_udp:
            try:
                self.udp_streamer = UDPStreamer(self.config)
                main_logger.info(" Streamer UDP inicializado")
            except Exception as e:
                main_logger.error(f" Erro no streamer UDP: {e}")
        else:
            main_logger.info("Streamer UDP desativado (usando TCP)")
        
        # Frame Server TCP para vídeo
        try:
            frame_tcp_cfg = self.config.get('frame_tcp', {'enabled': False})
            self.frame_server = CameraServer(
                host=frame_tcp_cfg.get('host', '127.0.0.1'),
                port=frame_tcp_cfg.get('port', 5050),
                enabled=frame_tcp_cfg.get('enabled', False)
            )
            self.frame_server.start()
            main_logger.info(" Servidor de frames TCP inicializado")
        except Exception as e:
            main_logger.error(f" Erro no servidor de frames: {e}")
            raise

    def _setup_callbacks(self) -> None:
        """Configura callbacks entre componentes"""
        main_logger.info("Configurando callbacks...")
        
        if self.camera_service:
            # IMPORTANTE: Inicia o streaming com o callback
            self.camera_service.start_streaming(self._handle_frame_callback)
            main_logger.info(" Callback de frames configurado")
        else:
            main_logger.error(" Serviço de câmera não disponível para callback")

    def _safe_json_dumps(self, obj: Any) -> Optional[str]:
            """Serializa objeto para JSON de forma segura"""
            try:
                # Função auxiliar para converter tipos numpy
                def convert_types(item):
                    if hasattr(item, 'item'):  # Para tipos numpy
                        return item.item()
                    elif isinstance(item, (list, tuple)):
                        return [convert_types(i) for i in item]
                    elif isinstance(item, dict):
                        return {k: convert_types(v) for k, v in item.items()}
                    else:
                        return item
                
                # Aplica conversão
                safe_obj = convert_types(obj)
                return json.dumps(safe_obj)
                
            except Exception as e:
                main_logger.error(f"Erro na serialização JSON: {e}")
                # Fallback seguro
                fallback = {"label": "erro_serializacao", "confidence": 0.0}
                return json.dumps(fallback)

    def _handle_frame_callback(self, frame_bytes: bytes) -> None:
        """Callback para frames capturados"""
        if not frame_bytes:
            main_logger.debug("Frame vazio recebido no callback")
            return
            
        # Atualiza estatísticas UMA VEZ (removida duplicação)
        self.stats['frames_streamed'] += 1
        
        # Log informativo
        if self.stats['frames_streamed'] == 1:
            main_logger.info(f"🎥 Primeiro frame no callback: {len(frame_bytes)} bytes")
        elif self.stats['frames_streamed'] % 30 == 0:
            main_logger.debug(f"Frames no callback: {self.stats['frames_streamed']}")
        
        # Envia para servidor de frames (TCP) - PRINCIPAL
        if self.frame_server:
            try:
                self.frame_server.broadcast(frame_bytes)
                main_logger.debug(f"Frame {self.stats['frames_streamed']} enviado para frame_server")
            except Exception as e:
                main_logger.error(f"Erro no broadcast para frame_server: {e}")
        
        # Envia via UDP se disponível (SECUNDÁRIO)
        if self.udp_streamer:
            try:
                self.udp_streamer.send_frame(frame_bytes)
                main_logger.debug(f"Frame {self.stats['frames_streamed']} enviado para udp_streamer")
            except Exception as e:
                main_logger.error(f"Erro no envio UDP: {e}")
    
    def _handle_command(self, command: str, client_addr: tuple) -> None:
        """Processa comandos recebidos de forma otimizada"""
        self.stats['commands_processed'] += 1
        
        command_handlers = {
            'REGISTER_UDP': self._handle_register_udp,
            'FOTO': self._handle_capture,
            'CAPTURE': self._handle_capture,
            'GET_INFO': self._handle_get_info,
            'WIFI_CONNECT': self._handle_wifi_connect,
            'RESTART_SERVICE': self._handle_restart_service,
            'SHOW_LOGS': self._handle_show_logs,
        }
        
        # Encontra o handler apropriado
        for cmd_prefix, handler in command_handlers.items():
            if command.startswith(cmd_prefix):
                handler(command, client_addr)
                return
        
        main_logger.debug(f"Comando não reconhecido: {command}")
    
    def _handle_capture(self, command: str, client_addr: tuple) -> None:
        """Handler otimizado para captura + inferência"""
        main_logger.info("Processando comando de captura...")
        
        # Salva foto em thread separada para não bloquear
        def save_photo_async():
            try:
                if self.camera_service:
                    success = self.camera_service.save_photo()
                    if success:
                        main_logger.info(" Foto salva com sucesso")
                    else:
                        main_logger.error(" Falha ao salvar foto")
            except Exception as e:
                main_logger.error(f" Erro ao salvar foto: {e}")
        
        threading.Thread(target=save_photo_async, daemon=True).start()
        
        # Executa inferência se disponível
        inference_result = None
        if self.ml_service and self.camera_service:
            try:
                frame = self.camera_service.get_last_frame()
                if frame is not None:
                    main_logger.info("Executando inferência ML...")
                    inference_result = self.ml_service.infer(frame)
                    if inference_result:
                        self.stats['inferences'] += 1
                        main_logger.info(f"Inferência concluída: {inference_result}")
                    else:
                        main_logger.warning("  Inferência retornou resultado vazio")
                else:
                    main_logger.warning(" Frame não disponível para inferência")
            except Exception as e:
                main_logger.error(f" Erro na inferência: {e}")
                inference_result = {"label": "erro_inferencia", "confidence": 0.0}
        
        #Serialização segura
        try:
            if inference_result:
                # Usa o método seguro de serialização
                result_json = self._safe_json_dumps(inference_result)
                main_logger.info(f" Enviando resultado da inferência: {inference_result}")
            else:
                result_json = json.dumps({"label": "capturado", "confidence": 0.0})
                main_logger.warning("  Enviando resultado fallback (sem inferência)")
            
            if self.tcp_server and result_json:
                success = self.tcp_server.send_text(result_json)
                if success:
                    main_logger.info(" Resultado enviado para cliente TCP")
                else:
                    main_logger.error(" Falha ao enviar resultado para cliente TCP")
            else:
                main_logger.error(" Servidor TCP não disponível para enviar resultado")
                
        except Exception as e:
            main_logger.error(f" Erro crítico no envio do resultado: {e}")
            # Fallback de emergência
            try:
                emergency_result = json.dumps({"label": "erro_sistema", "confidence": 0.0})
                if self.tcp_server:
                    self.tcp_server.send_text(emergency_result)
            except Exception as emergency_error:
                main_logger.critical(f"Falha até no fallback de emergência: {emergency_error}")

    def run(self) -> None:
        """Executa a aplicação principal"""
        self.is_running = True
        main_logger.info(" Aplicação Strawberry AI em execução")
        
        try:
            while self.is_running:
                # Aceita novas conexões TCP
                if self.tcp_server and self.tcp_server.poll_accept():
                    main_logger.info(" Novo cliente TCP conectado")
                
                # Processa comandos com tratamento robusto de erros
                if self.tcp_server:
                    try:
                        command = self.tcp_server.receive_command()
                        if command:
                            self._handle_command(command, self.tcp_server.addr)
                    except Exception as e:
                        main_logger.error(f"❌ Erro no processamento de comando: {e}")
                        # Não quebra o loop principal
                
                # Pequena pausa para não consumir CPU desnecessariamente
                time.sleep(0.001)
                
        except KeyboardInterrupt:
            main_logger.info("Encerramento solicitado via Ctrl+C")
        except Exception as e:
            main_logger.critical(f" Erro crítico no loop principal: {e}")
            import traceback
            main_logger.critical(traceback.format_exc())
        finally:
            self.shutdown()



    def _handle_register_udp(self, command: str, client_addr: tuple) -> None:
        """Handler para registro UDP"""
        if self.udp_streamer:
            try:
                udp_port = int(command.split(":")[1])
                self.udp_streamer.add_client((client_addr[0], udp_port))
            except (ValueError, IndexError) as e:
                main_logger.error(f"Porta UDP inválida: {e}")
    
    def _handle_get_info(self, command: str, client_addr: tuple) -> None:
        """Handler para informações do sistema"""
        if self.tcp_server:
            self.tcp_server._send_raspberry_info()
    
    def _handle_wifi_connect(self, command: str, client_addr: tuple) -> None:
        """Handler para conexão Wi-Fi"""
        if self.wifi_service:
            try:
                _, ssid, password = command.split(":", 2)
                result = self.wifi_service.connect_to_wifi(ssid, password)
                
                response = (
                    f"WIFI:SUCCESS:{result['message']}" 
                    if result['success'] 
                    else f"WIFI:FAILED:{result['message']}"
                )
                self.tcp_server.send_text(response)
                
            except ValueError as e:
                self.tcp_server.send_text(f"WIFI:ERROR:Formato de comando inválido {e}")
    
    def _handle_restart_service(self, command: str, client_addr: tuple) -> None:
        """Handler para reiniciar serviço"""
        try:
            import subprocess
            subprocess.run(["sudo", "systemctl", "restart", "strawberry-ai"], check=True)
            self.tcp_server.send_text("SERVICE:RESTARTED")
        except Exception as e:
            self.tcp_server.send_text(f"SERVICE:ERROR:{e}")
    
    def _handle_show_logs(self, command: str, client_addr: tuple) -> None:
        """Handler para mostrar logs"""
        try:
            import subprocess
            result = subprocess.run(
                ["tail", "-20", "/var/log/strawberry-ai.log"], 
                capture_output=True, text=True
            )
            logs = result.stdout if result.returncode == 0 else "Erro ao ler logs"
            self.tcp_server.send_text(f"LOGS:{logs}")
        except Exception as e:
            self.tcp_server.send_text(f"LOGS:Erro: {e}")
    
    def run(self) -> None:
        """Executa a aplicação principal"""
        self.is_running = True
        main_logger.info(" Aplicação Strawberry AI em execução")
        
        try:
            while self.is_running:
                # Aceita novas conexões TCP
                if self.tcp_server and self.tcp_server.poll_accept():
                    main_logger.info("🔗 Novo cliente TCP conectado")
                
                # Processa comandos
                if self.tcp_server:
                    command = self.tcp_server.receive_command()
                    if command:
                        self._handle_command(command, self.tcp_server.addr)
                
                # Pequena pausa para não consumir CPU desnecessariamente
                time.sleep(0.001)
                
        except KeyboardInterrupt:
            main_logger.info(" Encerramento solicitado via Ctrl+C")
        except Exception as e:
            main_logger.critical(f" Erro crítico: {e}")
            import traceback
            main_logger.critical(traceback.format_exc())
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
        
        main_logger.info(f"Shutdown completo. Estatísticas: {self.stats}")