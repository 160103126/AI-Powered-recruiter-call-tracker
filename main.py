from services.watcher import start_watcher
from database.db import init_db
import os

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, 'database', 'app.db')

if __name__ == '__main__':
    os.makedirs(os.path.join(BASE_DIR, 'recordings'), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'transcripts'), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, 'database'), exist_ok=True)
    init_db(DB_PATH)
    print('Starting watcher — drop audio files into recordings/')
    start_watcher(DB_PATH, os.path.join(BASE_DIR, 'recordings'))
