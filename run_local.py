from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIServer, make_server

from app import application


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True


if __name__ == "__main__":
    with make_server("127.0.0.1", 8000, application, server_class=ThreadingWSGIServer) as httpd:
        print("Serving on http://127.0.0.1:8000", flush=True)
        httpd.serve_forever()
