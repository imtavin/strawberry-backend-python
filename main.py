from core.app import StrawberryAIApp
from utils.logger import log_system_info

"""
Ponto de entrada principal da aplicação Strawberry AI
"""
def main():
    """Função principal"""
    # Log informações do sistema
    log_system_info()
    
    try:
        # Cria e inicializa aplicação
        app = StrawberryAIApp()
        
        if app.initialize():
            app.run()
        else:
            print("Falha na inicialização da aplicação. Verifique os logs.")
    except KeyboardInterrupt:
        print("Aplicação interrompida pelo usuário")
    except Exception as e:
        print(f"Erro crítico: {e}")

if __name__ == "__main__":
    main()