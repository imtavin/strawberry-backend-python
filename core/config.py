import json
from pathlib import Path
from typing import Dict, Any, Optional
from utils.logger import main_logger

class ConfigManager:
    _instance: Optional['ConfigManager'] = None
    _config: Dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._config:
            self.load_config()
    
    @property
    def root_dir(self) -> Path:
        """Retorna o diretório raiz do projeto de forma mais robusta"""
        # Tenta vários métodos para encontrar o diretório raiz
        possible_paths = [
            # Método 1: Do arquivo atual (para desenvolvimento)
            Path(__file__).resolve().parent.parent,
            # Método 2: Diretório de trabalho atual
            Path.cwd(),
            # Método 3: Subir um nível do diretório atual
            Path.cwd().parent,
        ]
        
        for path in possible_paths:
            config_test = path / "config.json"
            if config_test.exists():
                return path
        
        # Fallback: usa o diretório do script
        return Path(__file__).resolve().parent.parent
    
    def load_config(self) -> None:
        """Carrega configuração do arquivo JSON com fallbacks"""
        config_path = self.root_dir / "config.json"
        
        # Log para debug
        main_logger.info(f"Procurando config.json em: {config_path}")
        main_logger.info(f"Diretório atual: {Path.cwd()}")
        
        if not config_path.exists():
            # Tenta caminhos alternativos
            alt_paths = [
                Path.cwd() / "config.json",  # Diretório atual
                Path(__file__).parent / "config.json",  # Pasta core
                self.root_dir / "backend" / "config.json",  # Pasta backend
            ]
            
            for alt_path in alt_paths:
                if alt_path.exists():
                    config_path = alt_path
                    break
            else:
                # Se não encontrou em nenhum lugar, cria um padrão
                main_logger.warning("config.json não encontrado. Usando configuração padrão.")
                self._config = self._get_default_config()
                return
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self._config = json.load(f)
            main_logger.info(f"Configuração carregada com sucesso de: {config_path}")
        except Exception as e:
            main_logger.error(f"Erro ao carregar configuração: {e}")
            main_logger.info("Usando configuração padrão como fallback")
            self._config = self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Configuração padrão para fallback"""
        return {
            "camera": {
                "type": "opencv",
                "device_index": 0,
                "preview_size": [640, 480],
                "target_fps": 30,
                "jpeg_quality": 80
            },
            "server": {
                "enabled": True,
                "host": "127.0.0.1",
                "port": 5000
            },
            "udp": {
                "max_packet_size": 4096
            },
            "frame_tcp": {
                "enabled": True,
                "host": "127.0.0.1",
                "port": 5050
            },
            "video": {
                "transport": "tcp"
            },
            "ml": {
                "model_path": "backend/morganaAI/MorganaAI.tflite",
                "labels": [
                    "saudavel",
                    "acaro", 
                    "trips",
                    "mosca_branca",
                    "mancha_foliar",
                    "oidio",
                    "mofo_cinzento"
                ],
                "input_norm": "auto"
            }
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """Obtém valor da configuração usando dot notation"""
        keys = key.split('.')
        value = self._config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def get_camera_config(self) -> Dict[str, Any]:
        return self.get('camera', {})
    
    def get_ml_config(self) -> Dict[str, Any]:
        return self.get('ml', {})
    
    def get_network_config(self) -> Dict[str, Any]:
        return self.get('server', {})