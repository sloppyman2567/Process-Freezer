"""Application bootstrap: one instance, the theme, the window."""

import os
import sys

from PyQt6.QtGui import QFont
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication

from .core import APPLICATION, ORGANIZATION, Config
from .ui import ProcessFreezerWindow, apply_theme

SINGLE_INSTANCE_SOCKET = f"process-freezer-{os.getuid()}"


def main():
    app = QApplication(sys.argv)
    app.setOrganizationName(ORGANIZATION)
    app.setApplicationName(APPLICATION)
    app.setDesktopFileName("process-freezer")
    # A fixed base style keeps the themes identical on every desktop instead of
    # inheriting whatever the vendor style happens to draw.
    app.setStyle("Fusion")
    app.setFont(QFont("Noto Sans", 10))

    config = Config()
    apply_theme(app, config.theme)

    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(SINGLE_INSTANCE_SOCKET):
        client = QLocalSocket()
        client.connectToServer(SINGLE_INSTANCE_SOCKET)
        if client.waitForConnected(500):
            client.write(b"show")
            client.flush()
            client.waitForBytesWritten(500)
            return 0
        QLocalServer.removeServer(SINGLE_INSTANCE_SOCKET)
        if not server.listen(SINGLE_INSTANCE_SOCKET):
            raise RuntimeError("Could not start Process Freezer's single-instance listener.")

    window = ProcessFreezerWindow(config)

    def accept_connection():
        connection = server.nextPendingConnection()
        if connection is None:
            return
        connection.waitForReadyRead(100)
        if bytes(connection.readAll()) == b"freeze-saved":
            window.freeze_saved_target()
        else:
            window.showNormal()
            window.raise_()
            window.activateWindow()
        connection.disconnectFromServer()

    server.newConnection.connect(accept_connection)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
