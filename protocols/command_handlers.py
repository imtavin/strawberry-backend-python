# backend/protocols/command_handlers.py
import json
import subprocess
import threading
import time
from typing import Dict, Any, Optional, Tuple
from utils.logger import main_logger, tcp_logger

class SystemCommandHandler:
    """Handler para comandos de sistema"""
    
    def __init__(self, wifi_service, service_manager):
        self.wifi_service = wifi_service
        self.service_manager = service_manager
        self._command_handlers = {
            'WIFI_CONNECT': self._handle_wifi_connect,
            'RESTART_SERVICE': self._handle_restart_service,
            'SHOW_LOGS': self._handle_show_logs,
            'GET_SYSTEM_INFO': self._handle_system_info,
        }

    def handle_command(self, command: str, tcp_server) -> bool:
        """
        Processa comando e envia resposta
        Retorna True se o comando foi reconhecido
        """
        try:
            parts = command.split(':', 2)
            if len(parts) < 2:
                return False
                
            command_type = parts[0]
            command_id = parts[1]
            
            if command_type in self._command_handlers:
                # Executa handler em thread separada para não bloquear
                threading.Thread(
                    target=self._execute_handler,
                    args=(command_type, command_id, parts, tcp_server),
                    daemon=True
                ).start()
                return True
                
            return False
            
        except Exception as e:
            main_logger.error(f"Erro processando comando {command}: {e}")
            return False

    def _execute_handler(self, command_type: str, command_id: str, parts: list, tcp_server):
        """Executa handler em thread separada"""
        try:
            handler = self._command_handlers[command_type]
            success, message, data = handler(parts)
            
            # Envia resposta
            response = self._format_response(command_id, success, message, data)
            tcp_server.send_text(response)
            
        except Exception as e:
            error_msg = f"Erro executando {command_type}: {str(e)}"
            main_logger.error(error_msg)
            response = self._format_response(command_id, False, error_msg)
            tcp_server.send_text(response)

    def _format_response(self, command_id: str, success: bool, message: str, data: Any = None) -> str:
        """Formata resposta padronizada"""
        response = {
            'type': 'COMMAND_RESPONSE',
            'command_id': command_id,
            'success': success,
            'message': message,
            'data': data,
            'timestamp': time.time()
        }
        return json.dumps(response)

    def _handle_wifi_connect(self, parts: list) -> Tuple[bool, str, Optional[Dict]]:
        """Handler para conexão Wi-Fi"""
        try:
            if len(parts) < 4:
                return False, "Formato de comando inválido", None
                
            ssid = parts[2]
            password = parts[3]
            
            if not ssid or not password:
                return False, "SSID e senha são obrigatórios", None
            
            main_logger.info(f"Conectando ao Wi-Fi: {ssid}")
            result = self.wifi_service.connect_to_wifi(ssid, password)
            
            if result["success"]:
                return True, result["message"], {"ssid": ssid}
            else:
                return False, result["message"], {"error_code": result.get("error_code")}
                
        except Exception as e:
            error_msg = f"Erro na conexão Wi-Fi: {str(e)}"
            main_logger.error(error_msg)
            return False, error_msg, None

    def _handle_restart_service(self, parts: list) -> Tuple[bool, str, Optional[Dict]]:
        """Handler para reiniciar serviço"""
        try:
            main_logger.info("Reiniciando serviço...")
            result = self.service_manager.restart_service()
            
            if result["success"]:
                return True, result["message"], result.get("status", {})
            else:
                return False, result["message"], {"error_code": result.get("error_code")}
                
        except Exception as e:
            error_msg = f"Erro reiniciando serviço: {str(e)}"
            main_logger.error(error_msg)
            return False, error_msg, None

    def _handle_show_logs(self, parts: list) -> Tuple[bool, str, Optional[Dict]]:
        """Handler para visualizar logs"""
        try:
            lines = 50
            if len(parts) > 2:
                try:
                    lines = int(parts[2])
                except ValueError:
                    pass
            
            main_logger.info(f"Obtendo logs ({lines} linhas)...")
            result = self.service_manager.get_service_logs(lines)
            
            if result["success"]:
                return True, "Logs obtidos com sucesso", {
                    "logs": result["logs"],
                    "source": result.get("source"),
                    "lines": result.get("lines", 0),
                    "platform": result.get("platform", "unknown")
                }
            else:
                return False, result["message"], {
                    "error_code": result.get("error_code"),
                    "platform": result.get("platform", "unknown")
                }
                
        except Exception as e:
            error_msg = f"Erro obtendo logs: {str(e)}"
            main_logger.error(error_msg)
            return False, error_msg, None

    def _handle_system_info(self, parts: list) -> Tuple[bool, str, Optional[Dict]]:
        """Handler para informações do sistema"""
        try:
            # Coleta informações do sistema
            system_info = {
                "service_status": self.service_manager._check_service_status(),
                "wifi_connected": self.wifi_service.connected_ssid,
                "timestamp": time.time()
            }
            
            return True, "Informações do sistema obtidas", system_info
            
        except Exception as e:
            error_msg = f"Erro obtendo informações do sistema: {str(e)}"
            main_logger.error(error_msg)
            return False, error_msg, None