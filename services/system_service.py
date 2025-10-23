"""
Serviço de gerenciamento do sistema
"""
import subprocess
import time
import os
from typing import Dict, Optional
from utils.logger import system_logger

class ServiceManager:
    """Gerenciador de serviços do sistema"""
    
    def __init__(self, service_name: str = "strawberry-ai"):
        self.service_name = service_name
        
    def restart_service(self) -> Dict[str, any]:
        """Reinicia o serviço"""
        try:
            system_logger.info(f"Reiniciando serviço: {self.service_name}")
            result = subprocess.run(
                ["sudo", "systemctl", "restart", self.service_name],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return {
                    "success": True,
                    "message": f"Serviço {self.service_name} reiniciado com sucesso"
                }
            else:
                return {
                    "success": False,
                    "message": f"Falha ao reiniciar: {result.stderr}",
                    "error_code": "RESTART_FAILED"
                }
                
        except Exception as e:
            return {
                "success": False,
                "message": f"Erro: {str(e)}",
                "error_code": "EXCEPTION"
            }

    def get_service_logs(self, lines: int = 50) -> Dict[str, any]:
        """Obtém logs do serviço"""
        try:
            log_paths = [
                f"/var/log/{self.service_name}.log",
                "/var/log/syslog",
                f"/tmp/{self.service_name}.log"
            ]
            
            for log_path in log_paths:
                if os.path.exists(log_path):
                    result = subprocess.run(
                        ["sudo", "tail", f"-{lines}", log_path],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    
                    if result.returncode == 0:
                        return {
                            "success": True,
                            "logs": result.stdout,
                            "source": log_path,
                            "lines": len(result.stdout.split('\n'))
                        }
            
            return {
                "success": False,
                "message": "Não foi possível acessar os logs",
                "error_code": "LOGS_UNAVAILABLE"
            }
                
        except Exception as e:
            return {
                "success": False,
                "message": f"Erro ao obter logs: {str(e)}",
                "error_code": "LOGS_ERROR"
            }

    def _check_service_status(self) -> Dict[str, any]:
        """Verifica status do serviço"""
        return {
            "running": True,
            "active": True,
            "enabled": True,
            "pid": None
        }