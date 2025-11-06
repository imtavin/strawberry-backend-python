import subprocess
import time
import os
import logging
from typing import Dict, Optional, List
from utils.logger import system_logger
from utils.platform_detector import PlatformDetector

class ServiceManager:
    """Gerenciador de serviços do sistema multiplataforma"""
    
    def __init__(self, service_name: str = "strawberry-ai"):
        self.service_name = service_name
        self.platform = PlatformDetector()
        
    def restart_service(self) -> Dict[str, any]:
        """Reinicia o serviço de forma multiplataforma"""
        try:
            system_logger.info(f"Reiniciando serviço: {self.service_name}")
            
            if self.platform.is_linux():
                # Linux/Raspberry Pi
                result = subprocess.run(
                    ["sudo", "systemctl", "restart", self.service_name],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
            else:
                # Windows - simula reinício (para desenvolvimento)
                system_logger.warning("Reinício de serviço simulado no Windows")
                return {
                    "success": True,
                    "message": f"Serviço {self.service_name} reiniciado (simulado no Windows)"
                }
            
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
        """Obtém logs do serviço de forma multiplataforma"""
        try:
            system_logger.info(f"Obtendo logs ({lines} linhas)...")
            
            if self.platform.is_linux():
                return self._get_linux_logs(lines)
            else:
                return self._get_windows_logs(lines)
                
        except Exception as e:
            error_msg = f"Erro ao obter logs: {str(e)}"
            system_logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg,
                "error_code": "LOGS_ERROR"
            }

    def _get_linux_logs(self, lines: int) -> Dict[str, any]:
        """Obtém logs no Linux/Raspberry Pi"""
        log_paths = [
            f"/var/log/{self.service_name}.log",
            "/var/log/syslog",
            f"/tmp/{self.service_name}.log",
            "/opt/strawberry-ai/logs/backend.log",
            "/opt/strawberry-ai/logs/backend-error.log",
            "/opt/strawberry-ai/logs/kioski.log",
            "/opt/strawberry-ai/logs/kioski-error.log"
        ]
        
        for log_path in log_paths:
            if os.path.exists(log_path):
                try:
                    result = subprocess.run(
                        ["sudo", "tail", f"-{lines}", log_path],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    
                    if result.returncode == 0 and result.stdout.strip():
                        return {
                            "success": True,
                            "logs": result.stdout,
                            "source": log_path,
                            "lines": len(result.stdout.splitlines()),
                            "platform": "linux"
                        }
                except Exception as e:
                    system_logger.debug(f"Falha ao acessar {log_path}: {e}")
                    continue
        
        return {
            "success": False,
            "message": "Não foi possível acessar os logs no Linux",
            "error_code": "LOGS_UNAVAILABLE"
        }

    def _get_windows_logs(self, lines: int) -> Dict[str, any]:
        """Obtém logs no Windows"""
        try:
            # Tenta vários métodos para obter logs no Windows
            log_sources = []
            
            # 1. Tenta obter logs do próprio sistema
            import io
            import sys
            from datetime import datetime
            
            log_buffer = io.StringIO()
            
            # Captura logs recentes da aplicação
            log_entries = []
            try:
                # Tenta ler de arquivos de log comuns no Windows
                possible_paths = [
                    "logs/app.log",
                    "backend/logs/app.log", 
                    f"{self.service_name}.log",
                    "log.txt"
                ]
                
                for log_path in possible_paths:
                    if os.path.exists(log_path):
                        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                            all_lines = f.readlines()
                            log_entries.extend(all_lines[-lines:])
                            system_logger.info(f"Logs lidos de: {log_path}")
                            break
                
                # Se não encontrou arquivos, gera logs do sistema
                if not log_entries:
                    log_entries = [
                        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - SYSTEM - Aplicação Strawberry AI em execução\n",
                        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - SYSTEM - Modo: {'Raspberry Pi' if self.platform.is_raspberry_pi() else 'Windows'}\n",
                        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - SYSTEM - Logs simulados para ambiente Windows\n",
                        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - SYSTEM - Use Linux/Raspberry Pi para logs completos do sistema\n"
                    ]
                    
            except Exception as e:
                system_logger.error(f"Erro ao ler logs: {e}")
                log_entries = [f"Erro ao carregar logs: {str(e)}\n"]
            
            logs_content = "".join(log_entries[-lines:])
            
            return {
                "success": True,
                "logs": logs_content,
                "source": "windows_system",
                "lines": len(logs_content.splitlines()),
                "platform": "windows"
            }
            
        except Exception as e:
            system_logger.error(f"Erro crítico ao obter logs Windows: {e}")
            return {
                "success": False,
                "message": f"Erro ao obter logs no Windows: {str(e)}",
                "error_code": "WINDOWS_LOGS_ERROR"
            }

    def _check_service_status(self) -> Dict[str, any]:
        """Verifica status do serviço de forma multiplataforma"""
        try:
            if self.platform.is_linux():
                # Verifica status real no Linux
                result = subprocess.run(
                    ["sudo", "systemctl", "is-active", self.service_name],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                is_active = result.returncode == 0
                
                result = subprocess.run(
                    ["sudo", "systemctl", "is-enabled", self.service_name],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                is_enabled = result.returncode == 0
                
                # Obtém PID
                result = subprocess.run(
                    ["sudo", "systemctl", "show", self.service_name, "--property=MainPID"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                pid = None
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        if line.startswith("MainPID="):
                            pid_str = line.split("=")[1]
                            if pid_str.isdigit() and int(pid_str) > 0:
                                pid = int(pid_str)
                
                return {
                    "running": is_active,
                    "active": is_active,
                    "enabled": is_enabled,
                    "pid": pid
                }
            else:
                # Windows - status simulado
                return {
                    "running": True,
                    "active": True,
                    "enabled": True,
                    "pid": None,
                    "simulated": True
                }
                
        except Exception as e:
            system_logger.error(f"Erro ao verificar status: {e}")
            return {
                "running": False,
                "active": False,
                "enabled": False,
                "pid": None,
                "error": str(e)
            }