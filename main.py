import os
import socket
import urllib.parse
import mimetypes
from datetime import datetime
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from multiprocessing import Process
from pymongo import MongoClient

# Конфігурація
HTTP_PORT = 3000
SOCKET_PORT = 5000
SOCKET_HOST = '0.0.0.0'

# Перевірка MONGO_URI: якщо ми в Docker, то mongo сервіс зазвичай монтується за назвою 'mongodb'
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://mongodb:27017/')
DB_NAME = 'message_db'
COLLECTION_NAME = 'messages'


class HTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        pr = urllib.parse.urlparse(self.path)
        path = pr.path

        if path in ['/', '/index.html']:
            self.send_html_file('index.html')
        elif path in ['/message', '/message.html']:
            self.send_html_file('message.html')
        else:
            clean_path = path.lstrip('/')
            file_path = Path('.') / clean_path
            static_file_path = Path('static') / clean_path

            if file_path.exists() and file_path.is_file():
                self.send_static(file_path)
            elif static_file_path.exists() and static_file_path.is_file():
                self.send_static(static_file_path)
            else:
                self.send_html_file('error.html', status=404)

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)

        # Пересилка байт-рядка на Socket-сервер
        send_to_socket_server(post_data)

        # Редирект назад на /message
        self.send_response(302)
        self.send_header('Location', '/message')
        self.end_headers()

    def send_html_file(self, filename, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        try:
            with open(filename, 'rb') as fd:
                self.wfile.write(fd.read())
        except FileNotFoundError:
            if filename != 'error.html':
                self.send_html_file('error.html', status=404)

    def send_static(self, file_path):
        self.send_response(200)
        mt, _ = mimetypes.guess_type(file_path)
        if mt:
            self.send_header('Content-type', mt)
        else:
            self.send_header('Content-type', 'text/plain')
        self.end_headers()
        with open(file_path, 'rb') as fd:
            self.wfile.write(fd.read())


def send_to_socket_server(data):
    """Надсилає дані з HTTP-сервера на Socket-сервер через UDP."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(data, ('127.0.0.1', SOCKET_PORT))


def run_http_server():
    server_address = ('', HTTP_PORT)
    httpd = HTTPServer(server_address, HTTPHandler)
    print(f"HTTP Server started on port {HTTP_PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()


def run_socket_server():
    """UDP Socket-сервер, який приймає дані та зберігає їх у MongoDB."""
    # Приєднуємось до MongoDB
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        collection = db[COLLECTION_NAME]
    except Exception as e:
        print(f"MongoDB Connection Error: {e}")

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((SOCKET_HOST, SOCKET_PORT))
        print(f"Socket Server listening on {SOCKET_HOST}:{SOCKET_PORT}")

        while True:
            data, _ = sock.recvfrom(1024)
            if not data:
                continue

            try:
                # Парсинг URL-encoded рядка від форми (username=...&message=...)
                data_parse = urllib.parse.unquote_plus(data.decode('utf-8'))
                data_dict = dict(item.split('=') for item in data_parse.split('&') if '=' in item)

                document = {
                    "date": str(datetime.now()),
                    "username": data_dict.get('username', ''),
                    "message": data_dict.get('message', '')
                }

                collection.insert_one(document)
                print(f"Saved document to MongoDB: {document}")
            except Exception as e:
                print(f"Error processing message: {e}")


if __name__ == '__main__':
    http_process = Process(target=run_http_server)
    socket_process = Process(target=run_socket_server)

    http_process.start()
    socket_process.start()

    http_process.join()
    socket_process.join()