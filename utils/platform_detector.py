import platform
import os

class PlatformDetector:
    """Detector de plataforma para compatibilidade multiplataforma"""
    
    @staticmethod
    def is_raspberry_pi() -> bool:
        """Verifica se está executando em Raspberry Pi"""
        try:
            with open('/proc/device-tree/model', 'r') as f:
                return 'raspberry pi' in f.read().lower()
        except:
            return False
    
    @staticmethod
    def is_linux() -> bool:
        """Verifica se é Linux (incluindo Raspberry Pi)"""
        return platform.system().lower() == "linux"
    
    @staticmethod
    def is_windows() -> bool:
        """Verifica se é Windows"""
        return platform.system().lower() == "windows"
    
    @staticmethod
    def get_platform_info() -> dict:
        """Retorna informações detalhadas da plataforma"""
        return {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "is_raspberry_pi": PlatformDetector.is_raspberry_pi(),
            "is_linux": PlatformDetector.is_linux(),
            "is_windows": PlatformDetector.is_windows()
        }