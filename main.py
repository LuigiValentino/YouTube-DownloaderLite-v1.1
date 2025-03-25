import sys
import os
import logging
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QFileDialog, QLabel, QMessageBox, QTableWidget,
    QTableWidgetItem, QProgressBar, QRadioButton, QButtonGroup, QGroupBox
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QFile, QTextStream
from PyQt5.QtGui import QIcon
from pytubefix import YouTube, Playlist 

logging.basicConfig(filename="download.log", level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")

def load_stylesheet(app, path="style.qss"):
    file = QFile(path)
    if file.open(QFile.ReadOnly | QFile.Text):
        stream = QTextStream(file)
        stylesheet = stream.readAll()
        app.setStyleSheet(stylesheet)
    else:
        print(f"No se pudo cargar el archivo de estilos: {path}")

class DownloadThread(QThread):
    progress_msg = pyqtSignal(str, int)
    progress_value = pyqtSignal(int, int)
    finished_download = pyqtSignal(int)

    def __init__(self, url, path, row, fmt):
        super().__init__()
        self.url = url
        self.path = path
        self.row = row
        self.fmt = fmt  

    def on_progress(self, stream, chunk, bytes_remaining):
        try:
            total = stream.filesize
            progress_percent = int((total - bytes_remaining) / total * 100)
            self.progress_value.emit(progress_percent, self.row)
        except Exception as e:
            logging.error(f"Error en on_progress: {e}")

    def run(self):
        try:
            yt = YouTube(self.url, on_progress_callback=self.on_progress)
            title = yt.title
            logging.info(f"Iniciando descarga: {title}")
            self.progress_msg.emit(f"Iniciando: {title}", self.row)
            if self.fmt == 'mp4':
                stream = yt.streams.filter(progressive=True, file_extension='mp4').first()
                if stream is None:
                    raise Exception("No se encontró stream MP4 disponible")
                stream.download(output_path=self.path)
            elif self.fmt == 'mp3':
                stream = yt.streams.filter(only_audio=True).first()
                if stream is None:
                    raise Exception("No se encontró stream de audio")
                out_file = stream.download(output_path=self.path)
                base, _ = os.path.splitext(out_file)
                new_file = base + ".mp3"
                os.rename(out_file, new_file)
            self.progress_msg.emit(f"Completado: {title}", self.row)
            logging.info(f"Descarga completada: {title}")
        except Exception as e:
            self.progress_msg.emit(f"Error: {str(e)}", self.row)
            logging.error(f"Error en descarga {self.url}: {e}")
            QMessageBox.critical(None, "Error en descarga", f"Error con la URL:\n{self.url}\n{str(e)}")
        finally:
            self.finished_download.emit(self.row)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("// YouTube DownloaderLite v1.1")
        self.setWindowIcon(QIcon('./source/icon_img.png'))
        self.resize(950, 750)
        self.download_path = ""
        self.download_queue = []  
        self.total_downloads = 0
        self.completed_downloads = 0
        self.active_threads = {}
        self.max_concurrent = 3
        self.init_ui()

        self.statusBar().showMessage("Programa hecho por Luigi Adducci")

    def init_ui(self):
        top_group = QGroupBox("Ingresar URL y formato")
        top_layout = QHBoxLayout()

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Ingresa la URL del video o playlist")
        self.add_button = QPushButton("+")
        self.add_button.setToolTip("Agregar URL a la lista")

        self.mp4_radio = QRadioButton("MP4")
        self.mp3_radio = QRadioButton("MP3")
        self.mp4_radio.setChecked(True)
        self.format_group = QButtonGroup()
        self.format_group.addButton(self.mp4_radio)
        self.format_group.addButton(self.mp3_radio)

        top_layout.addWidget(self.url_input)
        top_layout.addWidget(self.add_button)
        top_layout.addWidget(self.mp4_radio)
        top_layout.addWidget(self.mp3_radio)
        top_group.setLayout(top_layout)

        mid_group = QGroupBox("Acciones")
        mid_layout = QHBoxLayout()
        self.select_path_button = QPushButton("Seleccionar Ruta")
        self.start_button = QPushButton("Iniciar Descargas")
        self.cancel_all_button = QPushButton("Cancelar Descargas")
        self.clear_list_button = QPushButton("Limpiar Lista")
        mid_layout.addWidget(self.select_path_button)
        mid_layout.addWidget(self.start_button)
        mid_layout.addWidget(self.cancel_all_button)
        mid_layout.addWidget(self.clear_list_button)
        mid_group.setLayout(mid_layout)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Título", "URL", "Estado", "Progreso"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 300)
        self.table.setColumnWidth(1, 300)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(3, 100)

        self.info_label = QLabel("Estado: Listo para iniciar")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.global_progress = QProgressBar()
        self.global_progress.setValue(0)
        self.global_progress.setAlignment(Qt.AlignCenter)

        main_layout = QVBoxLayout()
        main_layout.addWidget(top_group)
        main_layout.addWidget(self.table)
        main_layout.addWidget(mid_group)
        main_layout.addWidget(self.info_label)
        main_layout.addWidget(self.global_progress)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

        self.add_button.clicked.connect(self.add_url)
        self.select_path_button.clicked.connect(self.select_path)
        self.start_button.clicked.connect(self.start_downloads)
        self.cancel_all_button.clicked.connect(self.cancel_all_downloads)
        self.clear_list_button.clicked.connect(self.clear_table)

    def add_url(self):
        url = self.url_input.text().strip()
        if not url:
            return

        if "playlist" in url.lower():
            try:
                pl = Playlist(url)
                count = 0
                for video_url in pl.video_urls:
                    self._add_video(video_url)
                    count += 1
                logging.info(f"Se agregaron {count} videos de la playlist: {url}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo cargar la playlist: {e}")
                logging.error(f"Error al cargar playlist {url}: {e}")
        else:
            self._add_video(url)
        self.url_input.clear()

    def _add_video(self, url):
        try:
            yt = YouTube(url)
            title = yt.title
        except Exception:
            title = "Título no disponible"
        row_position = self.table.rowCount()
        self.table.insertRow(row_position)
        self.table.setItem(row_position, 0, QTableWidgetItem(title))
        self.table.setItem(row_position, 1, QTableWidgetItem(url))
        self.table.setItem(row_position, 2, QTableWidgetItem("Pendiente"))
        progress_bar = QProgressBar()
        progress_bar.setValue(0)
        self.table.setCellWidget(row_position, 3, progress_bar)
        self.download_queue.append((url, row_position))

    def select_path(self):
        path = QFileDialog.getExistingDirectory(self, "Selecciona la ruta de descarga")
        if path:
            self.download_path = path
            QMessageBox.information(self, "Ruta Seleccionada", f"Archivos se guardarán en:\n{path}")
            self.info_label.setText(f"Ruta seleccionada: {path}")

    def start_downloads(self):
        if not self.download_queue:
            QMessageBox.warning(self, "Sin URLs", "Agrega al menos una URL.")
            return
        if not self.download_path:
            QMessageBox.warning(self, "Sin Ruta", "Selecciona una ruta de descarga.")
            return
        self.total_downloads = len(self.download_queue)
        self.completed_downloads = 0
        self.info_label.setText(f"Iniciando descarga: 0 de {self.total_downloads}")
        self.start_button.setEnabled(False)
        for _ in range(min(self.max_concurrent, len(self.download_queue))):
            self.process_next_download()

    def process_next_download(self):
        if self.download_queue:
            if len(self.active_threads) >= self.max_concurrent:
                return
            url, row = self.download_queue.pop(0)
            self.table.setItem(row, 2, QTableWidgetItem("Iniciado"))
            fmt = 'mp4' if self.mp4_radio.isChecked() else 'mp3'
            thread = DownloadThread(url, self.download_path, row, fmt)
            self.active_threads[row] = thread
            thread.progress_msg.connect(self.update_status)
            thread.progress_value.connect(self.update_progress_bar)
            thread.finished_download.connect(self.download_finished)
            thread.start()
        else:
            if not self.active_threads:
                self.info_label.setText("Todas las descargas han finalizado.")
                self.global_progress.setValue(100)
                self.show_completion_dialog()

    def update_status(self, message, row):
        self.table.setItem(row, 2, QTableWidgetItem(message))

    def update_progress_bar(self, value, row):
        widget = self.table.cellWidget(row, 3)
        if isinstance(widget, QProgressBar):
            widget.setValue(value)
        total_progress = sum(
            self.table.cellWidget(i, 3).value() for i in range(self.table.rowCount())
            if isinstance(self.table.cellWidget(i, 3), QProgressBar)
        )
        global_percent = int(total_progress / (self.table.rowCount() or 1))
        self.global_progress.setValue(global_percent)

    def download_finished(self, row):
        self.completed_downloads += 1
        self.info_label.setText(f"Descargando {self.completed_downloads} de {self.total_downloads}")
        if row in self.active_threads:
            del self.active_threads[row]
        self.process_next_download()

    def cancel_all_downloads(self):
        if self.active_threads:
            reply = QMessageBox.question(self, "Cancelar Descargas",
                                         "¿Cancelar todas las descargas en curso?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                for row, thread in list(self.active_threads.items()):
                    thread.terminate()
                    thread.wait()
                    logging.info(f"Descarga cancelada: {thread.url}")
                    self.table.setItem(row, 2, QTableWidgetItem("Cancelado"))
                self.active_threads.clear()
                self.info_label.setText("Descargas canceladas.")
        else:
            QMessageBox.information(self, "Sin Descargas", "No hay descargas en curso.")

    def clear_table(self):
        self.table.setRowCount(0)
        self.download_queue = []
        self.total_downloads = 0
        self.completed_downloads = 0
        self.global_progress.setValue(0)
        self.info_label.setText("Listo para nuevas descargas")
        self.start_button.setEnabled(True)
        logging.info("Tabla reiniciada para nuevas descargas.")

    def show_completion_dialog(self):
        msg = QMessageBox()
        msg.setWindowIcon(QIcon('./source/icon_img.png'))
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle("Descargas Completadas")
        msg.setText(f"{self.completed_downloads} de {self.total_downloads} archivos descargados en:\n{self.download_path}")
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec_()
        self.reset_ui()

    def reset_ui(self):
        self.clear_table()

    def closeEvent(self, event):
        if self.active_threads:
            reply = QMessageBox.question(self, "Salir",
                                         "Descargas en curso. ¿Salir y cancelar descargas?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                for thread in self.active_threads.values():
                    thread.terminate()
                    thread.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    load_stylesheet(app, "style.qss") 
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
