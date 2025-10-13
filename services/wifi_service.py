import subprocess
import time
import threading
from typing import Dict, List, Optional
from utils.logger import system_logger

class WiFiService:
    def __init__(self):
        self.connected_ssid: Optional[str] = None
        self.is_connecting = False
        self._connection_lock = threading.Lock()
    
    def connect_to_wifi(self, ssid: str, password: str) -> Dict[str, any]:
        """Conecta a uma rede Wi-Fi de forma thread-safe"""
        with self._connection_lock:
            if self.is_connecting:
                return {"success": False, "message": "Já existe uma conexão em andamento"}
                
            self.is_connecting = True
        
        try:
            system_logger.info(f"Tentando conectar à rede Wi-Fi: {ssid}")
            
            # Método 1: Usando nmcli (NetworkManager) - mais moderno
            result = self._connect_with_nmcli(ssid, password)
            if result["success"]:
                return result
            
            # Método 2: Fallback usando wpa_supplicant
            system_logger.warning("Falha com nmcli, tentando wpa_supplicant...")
            return self._connect_using_wpa_supplicant(ssid, password)
                
        except subprocess.TimeoutExpired:
            error_msg = "Timeout ao conectar ao Wi-Fi"
            system_logger.error(error_msg)
            return {"success": False, "message": error_msg}
        except Exception as e:
            error_msg = f"Erro inesperado: {str(e)}"
            system_logger.error(error_msg)
            return {"success": False, "message": error_msg}
        finally:
            self.is_connecting = False

    def _connect_with_nmcli(self, ssid: str, password: str) -> Dict[str, any]:
        """Tenta conexão usando NetworkManager (nmcli)"""
        try:
            cmd = ['sudo', 'nmcli', 'dev', 'wifi', 'connect', ssid, 'password', password]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                self.connected_ssid = ssid
                system_logger.info(f"Conectado com sucesso à rede: {ssid}")
                return {"success": True, "message": f"Conectado à rede {ssid}"}
            else:
                system_logger.warning(f"Falha no nmcli: {result.stderr}")
                return {"success": False, "message": result.stderr}
                
        except subprocess.TimeoutExpired:
            raise
        except Exception as e:
            system_logger.error(f"Erro no nmcli: {e}")
            return {"success": False, "message": str(e)}

    def _connect_using_wpa_supplicant(self, ssid: str, password: str) -> Dict[str, any]:
        """Método alternativo usando wpa_supplicant"""
        try:
            # Criar configuração WPA
            wpa_config = f'''network={{
    ssid="{ssid}"
    psk="{password}"
}}'''
            
            # Salvar configuração temporária
            with open('/tmp/wpa_supplicant.conf', 'w') as f:
                f.write(wpa_config)
            
            # Comandos para aplicar configuração
            commands = [
                ['sudo', 'wpa_cli', '-i', 'wlan0', 'reconfigure'],
                ['sudo', 'dhclient', '-r', 'wlan0'],
                ['sudo', 'dhclient', 'wlan0']
            ]
            
            for cmd in commands:
                try:
                    subprocess.run(cmd, capture_output=True, timeout=10)
                except Exception as e:
                    system_logger.warning(f"Comando {cmd} falhou: {e}")
            
            # Verificar conexão
            time.sleep(8)  # Dar mais tempo para conexão
            if self._check_connection():
                self.connected_ssid = ssid
                return {"success": True, "message": f"Conectado à rede {ssid} (wpa_supplicant)"}
            else:
                return {"success": False, "message": "Falha na conexão via wpa_supplicant"}
                
        except Exception as e:
            system_logger.error(f"Erro no wpa_supplicant: {e}")
            return {"success": False, "message": f"Erro wpa_supplicant: {str(e)}"}

    def _check_connection(self) -> bool:
        """Verifica se há conexão Wi-Fi ativa"""
        try:
            result = subprocess.run(
                ['iwgetid', '-r'], 
                capture_output=True, 
                text=True, 
                timeout=5
            )
            is_connected = result.returncode == 0 and result.stdout.strip() != ""
            
            if is_connected:
                system_logger.info(f"Conectado à rede: {result.stdout.strip()}")
            else:
                system_logger.warning("Não conectado a nenhuma rede Wi-Fi")
                
            return is_connected
            
        except Exception as e:
            system_logger.error(f"Erro ao verificar conexão: {e}")
            return False

    def get_available_networks(self) -> List[str]:
        """Lista redes Wi-Fi disponíveis de forma otimizada"""
        try:
            result = subprocess.run(
                ['sudo', 'iwlist', 'wlan0', 'scan', '|', 'grep', 'ESSID', '|', 'cut', '-d:', '-f2', '|', 'sed', 's/\"//g'],
                shell=True,
                capture_output=True, 
                text=True,
                timeout=15
            )
            
            if result.returncode == 0:
                networks = [
                    ssid.strip() 
                    for ssid in result.stdout.split('\n') 
                    if ssid.strip()
                ]
                unique_networks = list(set(networks))
                system_logger.info(f"Encontradas {len(unique_networks)} redes Wi-Fi")
                return unique_networks
                
            return []
            
        except Exception as e:
            system_logger.error(f"Erro ao listar redes Wi-Fi: {e}")
            return []

    def get_current_network(self) -> str:
        """Obtém a rede Wi-Fi atual"""
        try:
            result = subprocess.run(
                ['iwgetid', '-r'], 
                capture_output=True, 
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                current_ssid = result.stdout.strip()
                self.connected_ssid = current_ssid
                return current_ssid
            return "Nenhuma"
        except Exception as e:
            system_logger.error(f"Erro ao obter rede atual: {e}")
            return "Erro"

    def disconnect(self) -> bool:
        """Desconecta da rede Wi-Fi atual"""
        try:
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
            else:
                system_logger.error(f"Falha ao desconectar: {result.stderr}")
                return False
                
        except Exception as e:
            system_logger.error(f"Erro ao desconectar: {e}")
            return False