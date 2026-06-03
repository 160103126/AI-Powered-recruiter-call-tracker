import time
import os
import threading
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from services.utils import file_sha256
from services.transcriber import transcribe_file
from services.extractor import extract_from_transcript
from services.scorer import score_opportunity
from database.db import get_conn, file_processed, mark_file_processed, save_opportunity, save_transcript


class NewAudioHandler(FileSystemEventHandler):
    def __init__(self, db_path, recordings_dir):
        self.db_path = db_path
        self.recordings_dir = recordings_dir

    def on_created(self, event):
        if event.is_directory:
            return
        path = event.src_path
        if not path.lower().endswith(('.mp3', '.wav', '.m4a', '.aac')):
            return
        threading.Thread(target=self.process_file, args=(path,)).start()

    def wait_for_complete(self, path, timeout=30):
        prev_size = -1
        stable_for = 0
        start = time.time()
        while time.time() - start < timeout:
            try:
                size = os.path.getsize(path)
            except FileNotFoundError:
                return False
            if size == prev_size:
                stable_for += 1
                if stable_for >= 2:
                    return True
            else:
                stable_for = 0
            prev_size = size
            time.sleep(1)
        return False

    def process_file(self, path):
        if not self.wait_for_complete(path):
            print('File not stable or removed:', path)
            return
        h = file_sha256(path)
        conn = get_conn(self.db_path)
        if file_processed(conn, h):
            print('Already processed:', path)
            conn.close()
            return
        print('Transcribing', path)
        try:
            result = transcribe_file(path)
        except Exception as e:
            print('Transcription failed:', e)
            conn.close()
            return
        transcript = result.get('transcript')
        # store transcript temporarily
        # Extract structured data
        try:
            extracted = extract_from_transcript(transcript)
        except Exception as e:
            print('Extraction failed:', e)
            extracted = {'company': None, 'role': None}
        # Score
        try:
            score = score_opportunity(extracted)
            extracted['score'] = score.get('score')
        except Exception:
            extracted['score'] = None
        # Save opportunity and transcript
        opp_id = save_opportunity(conn, extracted)
        save_transcript(conn, opp_id, transcript, path)
        mark_file_processed(conn, h, os.path.basename(path))
        conn.close()
        print('Processed:', path)


def start_watcher(db_path, recordings_dir):
    event_handler = NewAudioHandler(db_path, recordings_dir)
    observer = Observer()
    observer.schedule(event_handler, recordings_dir, recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
