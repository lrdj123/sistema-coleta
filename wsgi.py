import sys
sys.path.insert(0, '/home/seu-usuario/sistema-coleta')
from app import app as application

if __name__ == '__main__':
    application.run()
