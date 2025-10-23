"""
Serviço de Wi-Fi refatorado com melhor tratamento de erros
"""
import subprocess
import time
import threading
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from utils.logger import system_logger

@dataclass
class WiFiNetwork:
    ssid: str
    signal: int
    security: str
    connected: bool = False

class WiFiService:  
    """Gerenciador robusto de conexões Wi-Fi"""
    
    def __init__(self):
        self.connected_ssid: Optional[str] = None
        self.is_connecting = False
        self._connection_lock = threading.Lock()
        self._available_tools = self._detect_available_tools()
        
    def _detect_available_tools(self) -> List[str]:
        """Detecta ferramentas de rede disponíveis"""
        available = []
        tools = [
            ("nmcli", ["nmcli", "--version"]),
            ("wpa_supplicant", ["wpa_supplicant", "-v"]),
            ("iwlist", ["iwlist", "--version"]),
            ("iw", ["iw", "help"])
        ]
        
        for tool_name, check_cmd in tools:
            try:
                result = subprocess.run(
                    check_cmd,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    available.append(tool_name)
                    system_logger.info(f"Ferramenta de rede detectada: {tool_name}")
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
                
        if not available:
            system_logger.warning("Nenhuma ferramenta de rede detectada")
            
        return available

    def connect_to_wifi(self, ssid: str, password: str) -> Dict[str, any]:
        """Conecta a uma rede Wi-Fi"""
        if self.is_connecting:
            return {
                "success": False, 
                "message": "Conexão já em andamento",
                "error_code": "ALREADY_CONNECTING"
            }
            
        with self._connection_lock:
            self.is_connecting = True
            
        try:
            ssid = ssid.strip()
            if not ssid:
                return {
                    "success": False,
                    "message": "SSID não pode estar vazio",
                    "error_code": "INVALID_SSID"
                }
            
            system_logger.info(f"Tentando conectar à rede: {ssid}")
            
            # PRIMEIRO: Tenta com nmcli (mais moderno)
            if "nmcli" in self._available_tools:
                result = self._connect_with_nmcli(ssid, password)
                if result["success"]:
                    return result
            
            # SEGUNDO: Tenta com wpa_supplicant (fallback)
            if "wpa_supplicant" in self._available_tools:
                result = self._connect_with_wpa_supplicant(ssid, password)
                if result["success"]:
                    return result
            
            # SE NADA FUNCIONOU
            return {
                "success": False,
                "message": "Nenhum método de conexão disponível",
                "error_code": "NO_METHODS"
            }
                
        except Exception as e:
            error_msg = f"Erro inesperado: {str(e)}"
            system_logger.error(error_msg)
            return {
                "success": False, 
                "message": error_msg,
                "error_code": "UNEXPECTED_ERROR"
            }
        finally:
            self.is_connecting = False

    def _connect_with_nmcli(self, ssid: str, password: str) -> Dict[str, any]:
        """Conexão usando NetworkManager (nmcli)"""
        if "nmcli" not in self._available_tools:
            return {
                "success": False,
                "message": "nmcli não disponível",
                "error_code": "TOOL_UNAVAILABLE"
            }
            
        try:
            # Escapa caracteres especiais no SSID e senha
            escaped_ssid = self._escape_shell_arg(ssid)
            escaped_password = self._escape_shell_arg(password)
            
            cmd = [
                'sudo', 'nmcli', 'dev', 'wifi', 'connect', 
                escaped_ssid, 'password', escaped_password
            ]
            
            system_logger.debug(f"Executando: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=45  # Timeout aumentado
            )
            
            if result.returncode == 0:
                # Verifica se realmente conectou
                time.sleep(3)
                if self._verify_connection(ssid):
                    return {
                        "success": True, 
                        "message": f"Conectado à rede {ssid}"
                    }
                else:
                    return {
                        "success": False,
                        "message": "Conexão aparentemente bem-sucedida, mas verificação falhou",
                        "error_code": "VERIFICATION_FAILED"
                    }
            else:
                error_msg = result.stderr.strip() if result.stderr else "Erro desconhecido"
                system_logger.error(f"nmcli falhou: {error_msg}")
                return {
                    "success": False, 
                    "message": f"Falha na conexão: {error_msg}",
                    "error_code": "NMCLI_ERROR"
                }
                
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "message": "Timeout na conexão via nmcli",
                "error_code": "TIMEOUT"
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Erro no nmcli: {str(e)}",
                "error_code": "NMCLI_EXCEPTION"
            }

    def _connect_with_wpa_supplicant(self, ssid: str, password: str) -> Dict[str, any]:
        """Método fallback usando wpa_supplicant"""
        if "wpa_supplicant" not in self._available_tools:
            return {
                "success": False,
                "message": "wpa_supplicant não disponível",
                "error_code": "TOOL_UNAVAILABLE"
            }
            
        try:
            # Gera configuração WPA
            wpa_config = self._generate_wpa_config(ssid, password)
            
            # Salva configuração temporária
            config_path = "/tmp/wpa_supplicant_temp.conf"
            with open(config_path, 'w') as f:
                f.write(wpa_config)
            
            # Comandos para aplicar configuração
            commands = [
                ['sudo', 'cp', config_path, '/etc/wpa_supplicant/wpa_supplicant.conf'],
                ['sudo', 'wpa_cli', '-i', 'wlan0', 'reconfigure'],
                ['sudo', 'systemctl', 'restart', 'wpa_supplicant'],
                ['sudo', 'dhclient', '-r', 'wlan0'],
                ['sudo', 'dhclient', 'wlan0']
            ]
            
            for cmd in commands:
                try:
                    subprocess.run(cmd, capture_output=True, timeout=10, check=False)
                    time.sleep(2)
                except Exception as e:
                    system_logger.warning(f"Comando {cmd} falhou: {e}")
            
            # Verificação mais longa para wpa_supplicant
            time.sleep(10)
            if self._verify_connection(ssid):
                return {
                    "success": True, 
                    "message": f"Conectado à rede {ssid} (wpa_supplicant)"
                }
            else:
                return {
                    "success": False,
                    "message": "Falha na conexão via wpa_supplicant",
                    "error_code": "WPA_FAILED"
                }
                
        except Exception as e:
            return {
                "success": False, 
                "message": f"Erro wpa_supplicant: {str(e)}",
                "error_code": "WPA_EXCEPTION"
            }

    def _generate_wpa_config(self, ssid: str, password: str) -> str:
        """Gera configuração WPA segura"""
        return f'''
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1
country=BR

network={{
    ssid="{ssid}"
    psk="{password}"
    scan_ssid=1
    key_mgmt=WPA-PSK
}}
'''

    def _escape_shell_arg(self, arg: str) -> str:
        """Escapa argumentos para shell de forma segura"""
        return "'" + arg.replace("'", "'\\''") + "'"

    def _verify_connection(self, expected_ssid: str = None) -> bool:
        """Verifica se há conexão Wi-Fi ativa e válida"""
        try:
            # Método 1: Usando iwgetid
            result = subprocess.run(
                ['iwgetid', '-r'], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            
            if result.returncode == 0:
                current_ssid = result.stdout.strip()
                if current_ssid:
                    system_logger.info(f"Conectado à rede: {current_ssid}")
                    
                    if expected_ssid and current_ssid != expected_ssid:
                        system_logger.warning(f"Conectado à rede diferente: esperado {expected_ssid}, obtido {current_ssid}")
                        return False
                    
                    # Verifica se tem IP
                    time.sleep(2)
                    if self._has_ip_address():
                        return True
            
            # Método 2: Fallback com nmcli
            if "nmcli" in self._available_tools:
                result = subprocess.run(
                    ['nmcli', '-t', '-f', 'ACTIVE,SSID', 'dev', 'wifi'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if line.startswith('yes:'):
                            connected_ssid = line.split(':', 1)[1]
                            system_logger.info(f"nmcli reporta conexão com: {connected_ssid}")
                            return True
                            
            return False
            
        except Exception as e:
            system_logger.error(f"Erro ao verificar conexão: {e}")
            return False

    def _has_ip_address(self) -> bool:
        """Verifica se a interface tem endereço IP"""
        try:
            result = subprocess.run(
                ['ip', 'addr', 'show', 'wlan0'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and 'inet ' in result.stdout:
                return True
            return False
        except Exception:
            return False

    def get_available_networks(self) -> List[WiFiNetwork]:
        """Lista redes Wi-Fi disponíveis"""
        networks = []
        
        try:
            if "nmcli" in self._available_tools:
                result = subprocess.run(
                    [
                        'nmcli', '-t', '-f',
                        'SSID,SIGNAL,SECURITY', 
                        'dev', 'wifi', 'list', '--rescan', 'yes'
                    ],
                    capture_output=True,
                    text=True,
                    timeout=15
                )
                
                if result.returncode == 0:
                    for line in result.stdout.strip().split('\n'):
                        if line:
                            parts = line.split(':')
                            if len(parts) >= 3:
                                networks.append(WiFiNetwork(
                                    ssid=parts[0],
                                    signal=int(parts[1]),
                                    security=parts[2]
                                ))
            
            system_logger.info(f"Encontradas {len(networks)} redes Wi-Fi")
            
        except Exception as e:
            system_logger.error(f"Erro ao listar redes: {e}")
            
        return networks

    def disconnect(self) -> bool:
        """Desconecta da rede Wi-Fi atual"""
        try:
            if "nmcli" in self._available_tools:
                result = subprocess.run(
                    ['sudo', 'nmcli', 'dev', 'disconnect', 'wlan0'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode == 0:
                    self.connected_ssid = None
                    system_logger.info("Desconectado da rede Wi-Fi")
                    return True
            
            return False
                
        except Exception as e:
            system_logger.error(f"Erro ao desconectar: {e}")
            return False