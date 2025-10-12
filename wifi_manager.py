import subprocess
import time
import threading
from utils.logger import system_logger

class WiFiManager:
    def __init__(self):
        self.connected_ssid = None
        self.is_connecting = False
        
    def connect_to_wifi(self, ssid: str, password: str) -> dict:
        """Conecta a uma rede Wi-Fi"""
        if self.is_connecting:
            return {"success": False, "message": "Já existe uma conexão em andamento"}
            
        self.is_connecting = True
        
        try:
            system_logger.info(f"Tentando conectar à rede Wi-Fi: {ssid}")
            
            # Método 1: Usando nmcli (NetworkManager) - mais moderno
            cmd = f'sudo nmcli dev wifi connect "{ssid}" password "{password}"'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                system_logger.info(f" Conectado com sucesso à rede: {ssid}")
                self.connected_ssid = ssid
                return {"success": True, "message": f"Conectado à rede {ssid}"}
            else:
                system_logger.error(f" Falha ao conectar (nmcli): {result.stderr}")
                
                # Método 2: Fallback usando wpa_supplicant
                return self._connect_using_wpa_supplicant(ssid, password)
                
        except subprocess.TimeoutExpired:
            system_logger.error("Timeout ao conectar ao Wi-Fi")
            return {"success": False, "message": "Timeout na conexão"}
        except Exception as e:
            system_logger.error(f"Erro ao conectar Wi-Fi: {e}")
            return {"success": False, "message": f"Erro: {str(e)}"}
        finally:
            self.is_connecting = False

    def _connect_using_wpa_supplicant(self, ssid: str, password: str) -> dict:
        """Método alternativo usando wpa_supplicant"""
        try:
            system_logger.info("Tentando conexão via wpa_supplicant...")
            
            # Criar configuração WPA
            wpa_config = f'''
network={{
    ssid="{ssid}"
    psk="{password}"
}}
'''
            # Salvar configuração temporária
            with open('/tmp/wpa_supplicant.conf', 'w') as f:
                f.write(wpa_config)
            
            # Reiniciar interface de rede
            commands = [
                'sudo wpa_cli -i wlan0 reconfigure',
                'sudo dhclient -r wlan0',
                'sudo dhclient wlan0'
            ]
            
            for cmd in commands:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
                if result.returncode != 0:
                    system_logger.warning(f"Comando falhou: {cmd}")
            
            # Verificar conexão
            time.sleep(5)
            if self._check_connection():
                self.connected_ssid = ssid
                return {"success": True, "message": f"Conectado à rede {ssid} (wpa_supplicant)"}
            else:
                return {"success": False, "message": "Falha na conexão via wpa_supplicant"}
                
        except Exception as e:
            system_logger.error(f"Erro no wpa_supplicant: {e}")
            return {"success": False, "message": f"Erro wpa_supplicant: {str(e)}"}

    def _check_connection(self) -> bool:
        """Verifica se há conexão com a internet"""
        try:
            # Verificar se o Wi-Fi está conectado
            cmd = "iwgetid -r"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            return result.returncode == 0 and result.stdout.strip() != ""
        except Exception as e:
            system_logger.error(f"Erro ao verificar conexão: {e}")
            return False

    def get_available_networks(self) -> list:
        """Lista redes Wi-Fi disponíveis"""
        try:
            cmd = "sudo iwlist wlan0 scan | grep 'ESSID' | cut -d':' -f2 | sed 's/\"//g'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                networks = [ssid.strip() for ssid in result.stdout.split('\n') if ssid.strip()]
                return list(set(networks))  # Remove duplicatas
            return []
        except Exception as e:
            system_logger.error(f"Erro ao listar redes Wi-Fi: {e}")
            return []

    def get_current_network(self) -> str:
        """Obtém a rede Wi-Fi atual"""
        try:
            cmd = "iwgetid -r"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
            return "Nenhuma"
        except Exception as e:
            system_logger.error(f"Erro ao obter rede atual: {e}")
            return "Erro"