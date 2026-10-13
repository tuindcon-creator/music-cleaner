import sys
import threading
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QColor, QPainter, QPen, QDesktopServices
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QComboBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QPlainTextEdit, QMessageBox, QSlider, QScrollArea)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from engine import SUPPORTED, process_file, Cancelled
from hardware import detect, summary, validate_platform

def clock(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds//60:02d}:{seconds%60:02d}"

class Waveform(QWidget):
    def __init__(self):
        super().__init__()
        self.peaks, self.duration = [], 0
        self.setMinimumHeight(150)
    def set_data(self, peaks, duration):
        self.peaks, self.duration = peaks, duration
        self.update()
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#091722"))
        w, h = self.width(), self.height()
        painter.setPen(QPen(QColor("#203849"), 1))
        for x in range(0, w, 80):
            painter.drawLine(x, 0, x, h - 25)
        painter.setPen(QPen(QColor("#438cff"), 1))
        for i, peak in enumerate(self.peaks):
            x = int(i * w / max(1, len(self.peaks)))
            half = int(peak * (h - 35) / 2)
            painter.drawLine(x, (h - 25)//2-half, x, (h - 25)//2+half)
        painter.setPen(QColor("#aac5de"))
        painter.drawText(8, h - 8, "00:00")
        painter.drawText(max(8, w - 80), h - 8, clock(self.duration))
        if not self.peaks:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "Sóng âm xuất hiện khi xử lý file")

class BatchWorker(QThread):
    status = Signal(int, str)
    progress = Signal(int)
    wave = Signal(list, float)
    output = Signal(int, list)
    log = Signal(str)
    completed = Signal(int, int, bool)
    def __init__(self, files, root, mode, fmt, device):
        super().__init__()
        self.files, self.root, self.mode, self.fmt, self.device = files, root, mode, fmt, device
        self.cancel = threading.Event()
    def run(self):
        ok = failed = 0
        try:
            profile = detect(self.device, probe_gpu=self.mode != "extract")
            self.log.emit(summary(profile))
            device = profile.device
        except Exception as error:
            self.log.emit("Không đọc được cấu hình: " + str(error) + " — dùng CPU.")
            device = "cpu"
        for row, source in enumerate(self.files):
            if self.cancel.is_set():
                break
            try:
                self.log.emit(f"\n▶ {source}")
                def phase(text, value):
                    self.status.emit(row, text)
                    self.progress.emit(int((row + value/100) * 100 / len(self.files)))
                outputs = process_file(source, self.root, self.mode, self.fmt, device,
                    self.cancel, phase, self.wave.emit, self.log.emit)
                self.output.emit(row, outputs)
                ok += 1
            except Cancelled:
                self.status.emit(row, "Đã dừng")
                break
            except Exception as error:
                failed += 1
                self.status.emit(row, "Lỗi — xem nhật ký")
                self.log.emit(str(error))
        self.completed.emit(ok, failed, self.cancel.is_set())

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Music Cleaner • Tách giọng & âm thanh")
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            self.resize(min(1180, int(available.width() * 0.95)),
                        min(850, int(available.height() * 0.9)))
        else:
            self.resize(1000, 700)
        self.files, self.outputs, self.worker = [], {}, None
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.8)
        self.player.setAudioOutput(self.audio)
        self.player.errorOccurred.connect(lambda *args: self.logs.appendPlainText(self.player.errorString()))
        base = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(base)
        self.setCentralWidget(scroll)
        layout = QVBoxLayout(base)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        title = QLabel("♫  Music Cleaner")
        title.setObjectName("title")
        layout.addWidget(title)
        layout.addWidget(QLabel("Tách giọng / nhạc nền bằng AI • Trích âm thanh từ video • Xử lý hàng loạt"))
        row = QHBoxLayout()
        self.add = QPushButton("+ Chọn nhiều file")
        self.add_folder = QPushButton("+ Thêm thư mục")
        self.clear = QPushButton("Xóa hàng đợi")
        for button in (self.add, self.add_folder, self.clear):
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["File đầu vào", "Trạng thái", "Kết quả"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 2)
        settings = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItem("AI: Tách giọng + nhạc nền", "separate")
        self.mode.addItem("Trích âm thanh (giữ toàn bộ âm thanh)", "extract")
        self.fmt = QComboBox()
        self.fmt.addItems(["WAV", "MP3", "FLAC"])
        self.device = QComboBox()
        self.device.addItem("Tự động (khuyên dùng)", "auto")
        self.device.addItem("CPU (tương thích)", "cpu")
        self.device.addItem("GPU NVIDIA (cần PyTorch CUDA)", "cuda")
        self.device.addItem("Apple GPU (macOS)", "mps")
        for label, widget in [("Chức năng", self.mode), ("Định dạng", self.fmt), ("Thiết bị", self.device)]:
            settings.addWidget(QLabel(label))
            settings.addWidget(widget)
        layout.addLayout(settings)
        destination = QHBoxLayout()
        self.dest = QLineEdit(str(Path.home() / "MusicCleanerOutput"))
        self.choose_dest = QPushButton("Chọn thư mục xuất")
        self.open_dest = QPushButton("Mở thư mục")
        destination.addWidget(QLabel("Lưu tại"))
        destination.addWidget(self.dest, 1)
        destination.addWidget(self.choose_dest)
        destination.addWidget(self.open_dest)
        layout.addLayout(destination)
        self.waveform = Waveform()
        layout.addWidget(self.waveform)
        playback = QHBoxLayout()
        self.preview = QComboBox()
        self.preview.addItem("Chọn file để nghe thử", "")
        self.play = QPushButton("▶ Phát / Tạm dừng")
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.time = QLabel("00:00 / 00:00")
        playback.addWidget(self.preview, 1)
        playback.addWidget(self.play)
        playback.addWidget(self.seek, 2)
        playback.addWidget(self.time)
        layout.addLayout(playback)
        actions = QHBoxLayout()
        self.start = QPushButton("BẮT ĐẦU XỬ LÝ HÀNG LOẠT")
        self.start.setObjectName("primary")
        self.stop = QPushButton("Dừng")
        self.stop.setEnabled(False)
        actions.addWidget(self.start, 3)
        actions.addWidget(self.stop)
        layout.addLayout(actions)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMaximumBlockCount(1000)
        self.logs.setMaximumHeight(115)
        layout.addWidget(self.logs)
        try:
            self.logs.appendPlainText(summary(detect(probe_gpu=False)))
        except Exception as error:
            self.logs.appendPlainText("Chưa đọc được cấu hình: " + str(error))
        layout.addWidget(QLabel("AI xử lý toàn bộ file. Demucs tách nguồn giọng; chất lượng tùy bản thu. Lần đầu cần Internet tải mô hình."))
        self.add.clicked.connect(self.select_files)
        self.add_folder.clicked.connect(self.select_folder)
        self.clear.clicked.connect(self.clear_queue)
        self.choose_dest.clicked.connect(self.select_destination)
        self.open_dest.clicked.connect(self.open_folder)
        self.start.clicked.connect(self.run_batch)
        self.stop.clicked.connect(self.cancel_batch)
        self.table.itemSelectionChanged.connect(self.select_preview)
        self.preview.currentIndexChanged.connect(self.change_media)
        self.play.clicked.connect(self.toggle_play)
        self.seek.sliderReleased.connect(lambda: self.player.setPosition(self.seek.value()))
        self.player.durationChanged.connect(lambda value: self.seek.setRange(0, min(value, 2147483647)))
        self.player.positionChanged.connect(self.update_player)
    def select_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Chọn video hoặc âm thanh", "",
            "Media (" + " ".join("*"+ext for ext in sorted(SUPPORTED)) + ");;Tất cả (*)")
        self.append_files(paths)
    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Thêm các file trong thư mục (không gồm thư mục con)")
        if folder:
            self.append_files(sorted(str(p) for p in Path(folder).iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED))
    def append_files(self, paths):
        for path in paths:
            path = str(Path(path).resolve())
            if path in self.files:
                continue
            if Path(path).suffix.lower() not in SUPPORTED:
                self.logs.appendPlainText("Bỏ qua định dạng chưa hỗ trợ: " + path)
                continue
            row = len(self.files)
            self.files.append(path)
            self.table.insertRow(row)
            for col, text in enumerate([Path(path).name, "Chờ xử lý", ""]):
                item = QTableWidgetItem(text)
                if col == 0:
                    item.setToolTip(path)
                self.table.setItem(row, col, item)
        if self.files:
            self.table.selectRow(len(self.files)-1)
    def clear_queue(self):
        self.player.stop()
        self.files.clear()
        self.outputs.clear()
        self.table.setRowCount(0)
        self.preview.clear()
        self.preview.addItem("Chọn file để nghe thử", "")
        self.waveform.set_data([], 0)
    def select_destination(self):
        folder = QFileDialog.getExistingDirectory(self, "Thư mục xuất", self.dest.text())
        if folder:
            self.dest.setText(folder)
    def open_folder(self):
        path = Path(self.dest.text().strip()).expanduser()
        if path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
    def select_preview(self):
        row = self.table.currentRow()
        self.preview.clear()
        if 0 <= row < len(self.files):
            self.preview.addItem("Gốc: " + Path(self.files[row]).name, self.files[row])
            for path in self.outputs.get(row, []):
                self.preview.addItem(Path(path).name, path)
    def change_media(self, *_):
        self.player.stop()
        path = self.preview.currentData()
        self.player.setSource(QUrl.fromLocalFile(path) if path else QUrl())
    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()
    def update_player(self, position):
        if not self.seek.isSliderDown():
            self.seek.setValue(min(position, 2147483647))
        self.time.setText(f"{clock(position/1000)} / {clock(self.player.duration()/1000)}")
    def lock(self, busy):
        for widget in [self.add, self.add_folder, self.clear, self.mode, self.fmt,
                       self.device, self.dest, self.choose_dest, self.start]:
            widget.setEnabled(not busy)
        self.stop.setEnabled(busy)
    def run_batch(self):
        if not self.files:
            QMessageBox.information(self, "Chưa có file", "Hãy chọn một hoặc nhiều file trước.")
            return
        if not self.dest.text().strip():
            QMessageBox.warning(self, "Thiếu thư mục", "Hãy chọn thư mục xuất.")
            return
        self.player.stop()
        self.progress.setValue(0)
        self.outputs.clear()
        for row in range(len(self.files)):
            self.table.item(row, 1).setText("Chờ xử lý")
            self.table.item(row, 2).setText("")
        self.lock(True)
        self.worker = BatchWorker(self.files.copy(), str(Path(self.dest.text().strip()).expanduser()),
            self.mode.currentData(), self.fmt.currentText().lower(), self.device.currentData())
        self.worker.status.connect(lambda row, text: self.table.item(row, 1).setText(text))
        self.worker.progress.connect(self.progress.setValue)
        self.worker.wave.connect(self.waveform.set_data)
        self.worker.log.connect(self.logs.appendPlainText)
        self.worker.output.connect(self.add_output)
        self.worker.completed.connect(self.batch_summary)
        self.worker.finished.connect(lambda: self.lock(False))
        self.worker.start()
    def add_output(self, row, paths):
        self.outputs[row] = paths
        self.table.item(row, 2).setText(" • ".join(Path(p).name for p in paths))
        self.table.item(row, 2).setToolTip("\n".join(paths))
        if self.table.currentRow() == row:
            self.select_preview()
    def batch_summary(self, ok, failed, cancelled):
        if not cancelled:
            self.progress.setValue(100)
        else:
            for row in range(len(self.files)):
                if self.table.item(row, 1).text() == "Chờ xử lý":
                    self.table.item(row, 1).setText("Chưa xử lý — đã dừng")
        self.logs.appendPlainText(f"\n{'Đã dừng' if cancelled else 'Hoàn tất'}: {ok} thành công, {failed} lỗi.")
    def cancel_batch(self):
        if self.worker:
            self.worker.cancel.set()
            self.stop.setEnabled(False)
            self.logs.appendPlainText("Đang dừng và dọn kết quả chưa hoàn tất…")
    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.cancel_batch()
            event.ignore()
            self.logs.appendPlainText("Chờ tác vụ dừng rồi đóng cửa sổ.")
        else:
            self.player.stop()
            event.accept()

def main():
    validate_platform()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QWidget { background:#0b1520; color:#e8f1ff; font-family:'Segoe UI'; font-size:13px; }
        QLabel#title { font-size:32px; font-weight:700; color:white; }
        QPushButton { background:#172b3e; border:1px solid #35516c; border-radius:8px; padding:11px; }
        QPushButton:hover { background:#23415b; }
        QPushButton:disabled { color:#65758a; background:#142030; }
        QPushButton#primary { background:#2065ff; font-weight:700; font-size:16px; }
        QLineEdit,QComboBox,QPlainTextEdit,QTableWidget { background:#102131; border:1px solid #294359; border-radius:6px; padding:5px; }
        QHeaderView::section { background:#183047; padding:8px; border:0; }
        QProgressBar { border:1px solid #294359; border-radius:5px; text-align:center; }
        QProgressBar::chunk { background:#246bff; }
        QSlider::groove:horizontal { height:6px; background:#294359; }
        QSlider::handle:horizontal { width:14px; background:#438cff; margin:-4px 0; border-radius:7px; }
    """)
    window = Window()
    window.show()
    sys.exit(app.exec())
if __name__ == "__main__":
    main()

