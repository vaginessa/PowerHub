import logging
import os
import signal
import threading

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.serving import WSGIRequestHandler, _log
from flask_socketio import SocketIO

import powerhub.directories as ph_dir
from powerhub import __version__

log = logging.getLogger(__name__)


def start_thread(f, *args):
    threading.Thread(
        target=f,
        args=(*args,),
        daemon=True,
    ).start()


class MyRequestHandler(WSGIRequestHandler):
    def address_string(self):
        if 'x-forwarded-for' in dict(self.headers._headers):
            return dict(self.headers._headers)['x-forwarded-for']
        else:
            return self.client_address[0]

    def log(self, type, message, *largs):
        # don't log datetime again
        if " /socket.io/?" not in largs[0]:
            _log(type, '%s %s\n' % (self.address_string(), message % largs))


class PowerHubApp(object):
    """This is the main app class

    It holds all parameters, settings and "sub apps", such as the flask app,
    the reverse proxy, the database, etc.

    """
    def __init__(self, args):
        """
        You can pass arguments to PowerHub by putting them in argv. If
        empty, sys.argv will be used (i.e. the command line arguments).

        """

        self.args = args
        ph_dir.init_directories(workspace_dir=args.WORKSPACE_DIR,
                                create_missing=True)
        self.init_flask()
        self.init_db()
        self.init_clipboard()
        self.init_socketio()
        self.init_settings()
        from powerhub.modules import set_up_watchdog
        set_up_watchdog()

        self.set_flask_app_attributes()

        if not (self.args.AUTH or self.args.NOAUTH):
            from powerhub.tools import generate_random_key
            log.info("You specified neither '--no-auth' nor '--auth <user>:<pass>'. "
                     "A password will be generated for your protection.")
            self.args.AUTH = "powerhub:" + generate_random_key(10)
            log.info("The credentials for basic authentication are '%s' "
                     "(without quotes)." % self.args.AUTH)

    def init_socketio(self):
        self.socketio = SocketIO(
            self.flask_app,
            async_mode="threading",
            cors_allowed_origins=[
                "http://%s:%d" % (
                    self.args.URI_HOST,
                    self.args.LPORT,
                ),
                "https://%s:%d" % (
                    self.args.URI_HOST,
                    self.args.SSL_PORT,
                ),
            ],
        )

    def init_flask(self):
        from powerhub.flask import app as flask_blueprint
        self.flask_app = Flask(__name__, static_url_path='/invalid')
        self.flask_app.register_blueprint(flask_blueprint)
        self.flask_app.wsgi_app = ProxyFix(
            self.flask_app.wsgi_app,
            x_proto=1,
            x_host=1,
            x_port=1
        )
        self.flask_app.config.update(
            DEBUG=self.args.DEBUG,
            SECRET_KEY=os.urandom(16),
            SQLALCHEMY_DATABASE_URI='sqlite:///' + ph_dir.directories.DB_FILENAME,
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )

        self.flask_app.jinja_env.globals['AUTH'] = self.args.AUTH
        self.flask_app.jinja_env.globals['VERSION'] = __version__

    def set_flask_app_attributes(self):
        """Set some global vars for the flask apps"""
        from powerhub.hiddenapp import hidden_app
        from powerhub.flask import app as flask_app
        for app in [flask_app, hidden_app]:
            setattr(app, 'key', self.key)
            setattr(app, 'clipboard', self.clipboard)
            setattr(app, 'args', self.args)
            setattr(app, 'callback_urls', self.callback_urls())
            setattr(app, 'webdav_url', self.webdav_url())

    def init_db(self):
        from flask_sqlalchemy import SQLAlchemy
        from powerhub.sql import init_db
        db = SQLAlchemy(self.flask_app)
        with self.flask_app.app_context():
            init_db(db)
        self.db = db

    def init_clipboard(self):
        from powerhub.sql import get_clipboard
        with self.flask_app.app_context():
            self.clipboard = get_clipboard()

    def init_settings(self):
        from powerhub.tools import get_secret_key
        with self.flask_app.app_context():
            self.key = get_secret_key()

    def callback_urls(self):
        return {
            'http': 'http://%s:%d/%s' % (
                self.args.URI_HOST,
                self.args.URI_PORT if self.args.URI_PORT else self.args.LPORT,
                self.args.URI_PATH+'/' if self.args.URI_PATH else '',
            ),
            'https': 'https://%s:%d/%s' % (
                self.args.URI_HOST,
                self.args.URI_PORT if self.args.URI_PORT else self.args.SSL_PORT,
                self.args.URI_PATH+'/' if self.args.URI_PATH else '',
            ),
        }

    def webdav_url(self):
        # TODO consider https
        return 'http://%s:%d/webdav' % (
            self.args.URI_HOST,
            self.args.LPORT,
        )

    def run_flask_app(self):
        self.socketio.run(
            self.flask_app,
            port=self.args.FLASK_PORT,
            host='127.0.0.1',
            use_reloader=False,
            request_handler=MyRequestHandler,
        )

    def signal_handler(self, sig, frame):
        log.info("CTRL-C caught, exiting...")
        self.stop()

    def run(self, background=False):
        from powerhub.reverseproxy import run_proxy
        signal.signal(signal.SIGINT, self.signal_handler)

        from powerhub.webdav import run_webdav
        start_thread(lambda: run_webdav(self.args.WEBDAV_PORT))
        start_thread(self.run_flask_app)

        if background:
            start_thread(lambda: run_proxy(self.args))
        else:
            run_proxy(self.args)

    def stop(self):
        from powerhub import reverseproxy
        if not reverseproxy.reactor._stopped:
            reverseproxy.reactor.stop()
