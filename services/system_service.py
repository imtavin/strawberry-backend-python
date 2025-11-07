import subprocess
import time
import os
import logging
import glob
from typing import Dict, Optional, List
from utils.logger import system_logger
from utils.platform_detector import PlatformDetector

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
LOGS_DIR = os.path.join(BASE_DIR, "logs")

class ServiceManager:
    """Gerenciador de serviços do sistema multiplataforma"""
    
    def __init__(self, service_name: str = "strawberry-ai"):
        self.service_name = service_name
        self.platform = PlatformDetector()
        self.logs_base_path = LOGS_DIR
        
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

    def get_service_logs(self, lines: int = 50, log_type: str = "all") -> Dict[str, any]:
        """Obtém logs do serviço de forma multiplataforma
        
        Args:
            lines: Número de linhas a retornar
            log_type: Tipo de logs a retornar ('all', 'backend', 'frontend', 'kiosk', 'metrics')
        """
        try:
            system_logger.info(f"Obtendo logs ({lines} linhas) - Tipo: {log_type}")
            
            if self.platform.is_linux():
                return self._get_linux_logs(lines, log_type)
            else:
                return self._get_windows_logs(lines, log_type)
                
        except Exception as e:
            error_msg = f"Erro ao obter logs: {str(e)}"
            system_logger.error(error_msg)
            return {
                "success": False,
                "message": error_msg,
                "error_code": "LOGS_ERROR"
            }

    def _get_linux_logs(self, lines: int, log_type: str) -> Dict[str, any]:
        """Obtém logs no Linux/Raspberry Pi"""
        # Mapeamento de tipos de log para arquivos
        log_files_map = {
            "backend": ["backend.log", "backend-error.log"],
            "frontend": ["kiosk.log", "kiosk-error.log"],
            "kiosk": ["kiosk.log", "kiosk-error.log"],
            "metrics": ["metrics.log", "metrics-collector.log"],
            "all": ["backend.log", "backend-error.log", "kiosk.log", "kiosk-error.log", 
                   "metrics.log", "metrics-collector.log"]
        }
        
        selected_files = log_files_map.get(log_type, log_files_map["all"])
        log_paths = [os.path.join(self.logs_base_path, fname) for fname in selected_files]
        
        all_logs = []
        successful_sources = []
        
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
                        log_content = f"\n\n=== {os.path.basename(log_path)} ===\n{result.stdout}"
                        all_logs.append(log_content)
                        successful_sources.append(log_path)
                        system_logger.debug(f"Logs obtidos de: {log_path}")
                        
                except Exception as e:
                    system_logger.debug(f"Falha ao acessar {log_path}: {e}")
                    continue
        
        if all_logs:
            combined_logs = "\n".join(all_logs)
            return {
                "success": True,
                "logs": combined_logs,
                "source": successful_sources,
                "lines": len(combined_logs.splitlines()),
                "platform": "linux",
                "log_type": log_type
            }
        else:
            return {
                "success": False,
                "message": "Não foi possível acessar os logs no Linux",
                "error_code": "LOGS_UNAVAILABLE"
            }

    def _get_windows_logs(self, lines: int, log_type: str) -> Dict[str, any]:
        """Obtém logs no Windows"""
        try:
            # Verificar se o diretório de logs existe
            if not os.path.exists(self.logs_base_path):
                return {
                    "success": False,
                    "message": f"Diretório de logs não encontrado: {self.logs_base_path}",
                    "error_code": "LOG_DIR_NOT_FOUND"
                }
            
            # Mapeamento de tipos de log para padrões de arquivo
            file_patterns_map = {
                "backend": ["strawberry_ai_*.log"],
                "frontend": ["strawberry_frontend_*.log"],
                "kiosk": ["strawberry_frontend_*.log"],
                "metrics": ["strawberry_ai_*.log"],  # No Windows, métricas podem estar nos logs principais
                "all": ["strawberry_ai_*.log", "strawberry_frontend_*.log"]
            }
            
            selected_patterns = file_patterns_map.get(log_type, file_patterns_map["all"])
            
            # Encontrar todos os arquivos de log correspondentes
            log_files = []
            for pattern in selected_patterns:
                full_pattern = os.path.join(self.logs_base_path, pattern)
                log_files.extend(glob.glob(full_pattern))
            
            # Ordenar arquivos por data de modificação (mais recente primeiro)
            log_files.sort(key=os.path.getmtime, reverse=True)
            
            if not log_files:
                return {
                    "success": False,
                    "message": f"Nenhum arquivo de log encontrado para o padrão: {selected_patterns}",
                    "error_code": "NO_LOG_FILES"
                }
            
            # Coletar logs dos arquivos mais recentes
            all_logs = []
            successful_sources = []
            total_lines = 0
            
            for log_file in log_files:
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        file_lines = f.readlines()
                    
                    if file_lines:
                        # Pegar as últimas 'lines' linhas deste arquivo
                        recent_lines = file_lines[-lines:] if len(file_lines) > lines else file_lines
                        log_content = f"\n\n=== {os.path.basename(log_file)} (modificado: {time.ctime(os.path.getmtime(log_file))}) ===\n"
                        log_content += "".join(recent_lines)
                        
                        all_logs.append(log_content)
                        successful_sources.append(log_file)
                        total_lines += len(recent_lines)
                        
                        # Se já coletamos linhas suficientes, parar
                        if total_lines >= lines:
                            break
                            
                except Exception as e:
                    system_logger.warning(f"Erro ao ler arquivo {log_file}: {e}")
                    continue
            
            if all_logs:
                combined_logs = "\n".join(all_logs)
                return {
                    "success": True,
                    "logs": combined_logs,
                    "source": successful_sources,
                    "lines": total_lines,
                    "platform": "windows",
                    "log_type": log_type
                }
            else:
                return {
                    "success": False,
                    "message": "Não foi possível ler nenhum arquivo de log",
                    "error_code": "LOG_READ_ERROR"
                }
            
        except Exception as e:
            system_logger.error(f"Erro ao obter logs Windows: {e}")
            return {
                "success": False,
                "message": f"Erro ao obter logs no Windows: {str(e)}",
                "error_code": "WINDOWS_LOGS_ERROR"
            }

    def get_available_log_types(self) -> List[str]:
        """Retorna os tipos de logs disponíveis na plataforma atual"""
        if self.platform.is_windows():
            return ["all", "backend", "frontend", "kiosk", "metrics"]
        else:
            return ["all", "backend", "frontend", "kiosk", "metrics"]

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
        
    def shutdown_system(self) -> Dict[str, any]:
        """Desliga o sistema de forma multiplataforma"""
        try:
            import platform
            import subprocess
            
            system = platform.system().lower()
            system_logger.info(f"🔄 Iniciando shutdown do sistema: {system}")
            
            if system == "linux":
                # Linux/Raspberry Pi - usando sudo shutdown
                result = subprocess.run(
                    ["sudo", "shutdown", "-h", "now"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                command_used = "sudo shutdown -h now"
                
            elif system == "windows":
                # Windows
                result = subprocess.run(
                    ["echo", "teste"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                command_used = "echo teste"
            else:
                return {
                    "success": False,
                    "message": f"Sistema operacional não suportado: {system}",
                    "platform": system,
                    "error_code": "UNSUPPORTED_PLATFORM"
                }
            
            if result.returncode == 0:
                return {
                    "success": True,
                    "message": f"Sistema será desligado (comando: {command_used})",
                    "platform": system,
                    "command": command_used,
                    "shutdown_initiated": True
                }
            else:
                error_msg = result.stderr if result.stderr else "Comando de shutdown falhou"
                return {
                    "success": False,
                    "message": f"Falha no desligamento: {error_msg}",
                    "platform": system,
                    "command": command_used,
                    "error": error_msg,
                    "error_code": "SHUTDOWN_FAILED"
                }
                
        except subprocess.TimeoutExpired:
            # Timeout pode ser normal pois o sistema está desligando
            return {
                "success": True,
                "message": "Comando de shutdown executado (sistema desligando...)",
                "platform": system,
                "timeout": True,
                "shutdown_initiated": True
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Erro no procedimento de shutdown: {str(e)}",
                "platform": platform.system().lower() if 'platform' in locals() else "unknown",
                "error": str(e),
                "error_code": "SHUTDOWN_EXCEPTION"
            }