import sys
import threading
import traceback
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QDesktopServices, QLinearGradient, QPainterPath
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFileDialog, QComboBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar, QPlainTextEdit, QMessageBox, QSlider, QScrollArea, QFrame, QStyle)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from engine import SUPPORTED, process_file, Cancelled, read_waveform
from hardware import detect, summary, validate_platform
from processing_modes import MODES

def clock(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds//60:02d}:{seconds%60:02d}"

class Waveform(QWidget):
    def __init__(self):
        super().__init__()
        self.peaks, self.duration = [], 0
        self.hint = "Chọn file để xem sóng âm"
        self.setMinimumHeight(150)
    def set_data(self, peaks, duration):
        self.peaks, self.duration = peaks, duration
        self.update()
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#091722"))
        w, h = self.width(), self.height()
        painter.setPen(QPen(QColor("#203849"), 1))
        for tick in range(7):
            x = int(tick * (w - 1) / 6)
            painter.drawLine(x, 0, x, h - 30)
            painter.setPen(QColor("#9fb8ce"))
            text = clock(self.duration * tick / 6)
            painter.drawText(max(0, min(x - 18, w - 48)), h - 8, text)
            painter.setPen(QPen(QColor("#203849"), 1))
        painter.setPen(QPen(QColor("#438cff"), 1))
        for i, peak in enumerate(self.peaks):
            x = int(i * w / max(1, len(self.peaks)))
            half = int(peak * (h - 35) / 2)
            painter.drawLine(x, (h - 25)//2-half, x, (h - 25)//2+half)
        painter.setPen(QColor("#aac5de"))
        if not self.peaks:
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             self.hint)

class BatchWorker(QThread):
    status = Signal(int, str)
    progress = Signal(int)
    wave = Signal(int, list, float)
    output = Signal(int, list)
    log = Signal(str)
    error = Signal(int, str)
    completed = Signal(int, int, bool)
    def __init__(self, files, root, mode, fmt, device, quality="auto", rows=None, preview_start=None, cleanup=0):
        super().__init__()
        self.files, self.root, self.mode, self.fmt, self.device = files, root, mode, fmt, device
        self.cancel = threading.Event()
        self.quality = quality
        self.rows = list(range(len(files))) if rows is None else rows
        self.preview_start = preview_start
        self.cleanup = cleanup
    def run(self):
        ok = failed = 0
        try:
            profile = detect(self.device, probe_gpu=self.mode == "separate")
            self.log.emit(summary(profile))
            device = profile.device
        except Exception as error:
            self.log.emit("Không đọc được cấu hình: " + str(error) + " — dùng CPU.")
            device = "cpu"
        for job, (row, source) in enumerate(zip(self.rows, self.files)):
            if self.cancel.is_set():
                break
            try:
                self.log.emit(f"\n▶ {source}")
                def phase(text, value):
                    self.status.emit(row, text)
                    self.progress.emit(int((job + value/100) * 100 / len(self.files)))
                def waveform(peaks, duration):
                    if self.preview_start is None:
                        self.wave.emit(row, peaks, duration)
                outputs = process_file(source, self.root, self.mode, self.fmt, device,
                    self.cancel, phase, waveform, self.log.emit, quality=self.quality,
                    preview_seconds=30 if self.preview_start is not None else None,
                    preview_start=self.preview_start or 0, cleanup=self.cleanup)
                self.output.emit(row, outputs)
                ok += 1
            except Cancelled:
                self.status.emit(row, "Đã dừng")
                break
            except Exception as error:
                failed += 1
                self.status.emit(row, "Lỗi — xem nhật ký")
                self.log.emit(traceback.format_exc())
                self.error.emit(row, str(error))
        self.completed.emit(ok, failed, self.cancel.is_set())


def card():
    frame = QFrame()
    frame.setObjectName("card")
    box = QVBoxLayout(frame)
    box.setContentsMargins(18, 13, 18, 13)
    box.setSpacing(10)
    return frame, box

def section_title(text):
    label = QLabel(text)
    label.setObjectName("section")
    return label

class PulseMark(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for i, height in enumerate((20, 44, 66, 42, 20)):
            gradient = QLinearGradient(0, 8, 0, 80)
            gradient.setColorAt(0, QColor("#c0b2ff"))
            gradient.setColorAt(.55, QColor("#637cff"))
            gradient.setColorAt(1, QColor("#2693ff"))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            painter.drawRoundedRect(QRectF(10+i*15, (90-height)/2, 9, height), 4.5, 4.5)

class PlayButton(QPushButton):
    def __init__(self):
        super().__init__("")
        self.playing = False
        self.setAccessibleName("Phát hoặc tạm dừng")
    def set_playing(self, playing):
        self.playing = playing
        self.update()
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        if self.playing:
            painter.drawRoundedRect(QRectF(23, 21, 6, 23), 1, 1)
            painter.drawRoundedRect(QRectF(35, 21, 6, 23), 1, 1)
        else:
            shape = QPainterPath()
            shape.moveTo(25, 20)
            shape.lineTo(44, 32)
            shape.lineTo(25, 44)
            shape.closeSubpath()
            painter.drawPath(shape)

class PreviewWorker(QThread):
    ready = Signal(str, list, float)
    failed = Signal(str, str)
    def __init__(self, path):
        super().__init__()
        self.path = path
        self.cancel = threading.Event()
    def run(self):
        try:
            peaks, duration = read_waveform(self.path, self.cancel, lambda *_: None)
            if not self.cancel.is_set():
                self.ready.emit(self.path, peaks, duration)
        except Cancelled:
            pass
        except Exception as error:
            if not self.cancel.is_set():
                self.failed.emit(self.path, str(error))

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Music Cleaner 1.1 • Tách nhạc nền & âm thanh")
        screen = QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.resize(min(1440, int(area.width() * .95)), min(1000, int(area.height() * .94)))
        else:
            self.resize(1180, 850)
        self.files, self.outputs, self.worker = [], {}, None
        self.sample_run = False
        self.active_rows = []
        self.wave_cache = {}
        self.preview_workers = set()
        self.active_preview = None
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.8)
        self.player.setAudioOutput(self.audio)
        base = QWidget()
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(base)
        self.setCentralWidget(scroll)
        layout = QVBoxLayout(base)
        layout.setContentsMargins(20, 22, 20, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        logo = PulseMark()
        logo.setFixedSize(90, 90)
        header.addWidget(logo)
        heading = QVBoxLayout()
        title = QLabel("Music Cleaner")
        title.setObjectName("title")
        heading.addWidget(title)
        subtitle = QLabel("Tách nhạc nền khỏi giọng nói • Âm thanh & video")
        subtitle.setObjectName("subtitle")
        heading.addWidget(subtitle)
        header.addLayout(heading, 1)
        badge = QLabel("AI")
        badge.setObjectName("badge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(58, 54)
        header.addWidget(badge)
        self.options_toggle = QPushButton("⚙  Tùy chọn")
        self.options_toggle.setCheckable(True)
        header.addWidget(self.options_toggle)
        layout.addLayout(header)

        self.settings_card, settings = card()
        self.mode = QComboBox()
        self.mode.addItem("Tách giọng + nhạc nền bằng AI", "separate")
        self.mode.addItem("Trích âm thanh từ video / audio", "extract")
        self.mode.addItem("Lọc lời thoại đã tách (giong.wav)", "speech")
        self.device = QComboBox()
        self.device.addItem("Tự động (khuyên dùng)", "auto")
        self.device.addItem("CPU", "cpu")
        self.device.addItem("GPU NVIDIA", "cuda")
        self.device.addItem("Apple GPU (macOS)", "mps")
        setting_row = QHBoxLayout()
        setting_row.addWidget(QLabel("Chức năng"))
        setting_row.addWidget(self.mode, 1)
        setting_row.addWidget(QLabel("Thiết bị"))
        setting_row.addWidget(self.device, 1)
        settings.addLayout(setting_row)
        self.settings_card.hide()
        layout.addWidget(self.settings_card)
        self.options_toggle.toggled.connect(self.settings_card.setVisible)

        file_card, file_layout = card()
        file_row = QHBoxLayout()
        file_icon = QLabel("♫")
        file_icon.setObjectName("fileIcon")
        file_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        file_icon.setFixedSize(76, 76)
        file_row.addWidget(file_icon)
        file_text = QVBoxLayout()
        self.file_name = QLabel("Chọn video hoặc âm thanh để bắt đầu")
        self.file_name.setTextFormat(Qt.TextFormat.PlainText)
        self.file_name.setObjectName("fileName")
        self.file_name.setWordWrap(True)
        self.file_meta = QLabel("MP3, WAV, FLAC, MP4, MKV và nhiều định dạng khác")
        self.file_meta.setObjectName("muted")
        self.file_meta.setWordWrap(True)
        file_text.addWidget(self.file_name)
        file_text.addWidget(self.file_meta)
        file_row.addLayout(file_text, 1)
        self.add = QPushButton("Chọn file / nhiều file")
        self.add.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        self.add.setMinimumHeight(52)
        file_row.addWidget(self.add)
        file_layout.addLayout(file_row)
        layout.addWidget(file_card)

        wave_card, wave_layout = card()
        wave_header = QHBoxLayout()
        wave_header.addWidget(section_title("Sóng âm của file đang chọn"), 1)
        legend = QLabel("●  Âm thanh gốc")
        legend.setStyleSheet("color: #72a7ff;")
        wave_header.addWidget(legend)
        wave_layout.addLayout(wave_header)
        self.waveform = Waveform()
        self.waveform.setMinimumHeight(155)
        wave_layout.addWidget(self.waveform)
        layout.addWidget(wave_card)

        middle = QHBoxLayout()
        queue_card, queue_layout = card()
        queue_heading = QHBoxLayout()
        self.queue_title = section_title("Danh sách file • 0 file")
        queue_heading.addWidget(self.queue_title, 1)
        self.add_folder = QPushButton("+ Thư mục")
        self.clear = QPushButton("Xóa danh sách")
        queue_heading.addWidget(self.add_folder)
        queue_heading.addWidget(self.clear)
        queue_layout.addLayout(queue_heading)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["File đầu vào", "Trạng thái", "Kết quả"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(100)
        self.table.setMaximumHeight(135)
        self.table.setShowGrid(False)
        queue_layout.addWidget(self.table)
        middle.addWidget(queue_card, 3)

        listen_card, listen_layout = card()
        listen_layout.addWidget(section_title("Nghe thử bản gốc / kết quả"))
        self.preview = QComboBox()
        self.preview.addItem("Chọn file để nghe thử", "")
        self.preview.setMinimumWidth(220)
        listen_layout.addWidget(self.preview)
        player_row = QHBoxLayout()
        self.play = PlayButton()
        self.play.setObjectName("play")
        self.play.setFixedSize(64, 64)
        player_row.addWidget(self.play)
        seek_column = QVBoxLayout()
        self.time = QLabel("00:00 / 00:00")
        self.seek = QSlider(Qt.Orientation.Horizontal)
        seek_column.addWidget(self.time)
        seek_column.addWidget(self.seek)
        player_row.addLayout(seek_column, 1)
        listen_layout.addLayout(player_row)
        volume_row = QHBoxLayout()
        volume_row.addStretch()
        volume_row.addWidget(QLabel("Âm lượng"))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(80)
        self.volume.setMaximumWidth(160)
        self.volume.valueChanged.connect(lambda value: self.audio.setVolume(value / 100))
        volume_row.addWidget(self.volume)
        listen_layout.addLayout(volume_row)
        listen_layout.addStretch()
        middle.addWidget(listen_card, 2)
        layout.addLayout(middle)

        export_card, export_layout = card()
        export_top = QHBoxLayout()
        self.export_title = section_title("Xuất giọng nói & nhạc nền")
        export_top.addWidget(self.export_title, 1)
        self.fmt = QComboBox()
        self.fmt.addItems(["WAV", "MP3", "FLAC"])
        self.quality = QComboBox()
        for key, (label, description) in MODES.items():
            self.quality.addItem(label, key)
        export_top.addWidget(QLabel("Chế độ"))
        export_top.addWidget(self.quality)
        export_top.addWidget(QLabel("Định dạng"))
        export_top.addWidget(self.fmt)
        export_layout.addLayout(export_top)
        self.quality_note = QLabel(MODES["auto"][1])
        self.quality_note.setObjectName("muted")
        self.quality_note.setWordWrap(True)
        export_layout.addWidget(self.quality_note)
        cleanup_row = QHBoxLayout()
        cleanup_row.addWidget(QLabel("Giảm nhạc sót trong lời thoại"))
        self.cleanup = QComboBox()
        self.cleanup.addItem("Tắt — giữ giọng trước lọc", 0)
        self.cleanup.addItem("Nhẹ — ưu tiên giọng", 12)
        self.cleanup.addItem("Mạnh hơn — cần nghe thử", 18)
        cleanup_row.addWidget(self.cleanup, 1)
        cleanup_row.addWidget(QLabel("Luôn giữ bản trước lọc để đối chiếu"))
        export_layout.addLayout(cleanup_row)
        export_row = QHBoxLayout()
        destination_column = QVBoxLayout()
        names_row = QHBoxLayout()
        names_row.addWidget(QLabel("File kết quả:"))
        self.output_names = QLineEdit("giong.wav  +  nhac_nen.wav")
        self.output_names.setReadOnly(True)
        names_row.addWidget(self.output_names, 1)
        destination_column.addLayout(names_row)
        destination = QHBoxLayout()
        self.dest = QLineEdit(str(Path.home() / "MusicCleanerOutput"))
        self.choose_dest = QPushButton("Chọn thư mục")
        self.choose_dest.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
        destination.addWidget(QLabel("Thư mục lưu:"))
        destination.addWidget(self.dest, 1)
        destination.addWidget(self.choose_dest)
        self.open_dest = QPushButton("Mở")
        self.open_dest.setToolTip("Mở thư mục kết quả")
        destination.addWidget(self.open_dest)
        destination_column.addLayout(destination)
        export_row.addLayout(destination_column, 3)
        self.start = QPushButton("TÁCH NHẠC NỀN TỰ ĐỘNG\nXuất giọng + nhạc nền riêng biệt")
        self.start.setObjectName("primary")
        self.start.setMinimumHeight(108)
        export_row.addWidget(self.start, 2)
        export_layout.addLayout(export_row)
        layout.addWidget(export_card)

        status_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setMinimumHeight(24)
        status_row.addWidget(self.progress, 1)
        self.stop = QPushButton("Dừng xử lý")
        self.stop.setEnabled(False)
        self.try_button = QPushButton("Thử 30 giây")
        self.try_button.setToolTip("Tách thử file đang chọn, bắt đầu từ vị trí thanh nghe thử.")
        self.try_button.clicked.connect(lambda: self.run_batch(True))
        status_row.addWidget(self.try_button)
        status_row.addWidget(self.stop)
        layout.addLayout(status_row)
        self.error_message = QLabel("")
        self.error_message.setWordWrap(True)
        self.error_message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.error_message.setStyleSheet("color: #ff9393;")
        self.error_message.hide()
        layout.addWidget(self.error_message)
        log_header = QHBoxLayout()
        self.log_toggle = QPushButton("Nhật ký xử lý ▾")
        self.log_toggle.setCheckable(True)
        self.save_log = QPushButton("Lưu nhật ký lỗi")
        log_header.addWidget(self.log_toggle)
        log_header.addStretch()
        log_header.addWidget(self.save_log)
        layout.addLayout(log_header)
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMaximumBlockCount(2000)
        self.logs.setMaximumHeight(150)
        self.logs.hide()
        layout.addWidget(self.logs)
        self.log_toggle.toggled.connect(self.logs.setVisible)
        try:
            self.logs.appendPlainText(summary(detect(probe_gpu=False)))
        except Exception as error:
            self.logs.appendPlainText("Chưa đọc được cấu hình: " + str(error))
        footer = QLabel("AI tách toàn bộ file; chất lượng tùy bản thu. File gốc được giữ nguyên. Lần đầu tải mô hình cần Internet.")
        footer.setObjectName("muted")
        footer.setWordWrap(True)
        layout.addWidget(footer)
        layout.addStretch()

        self.add.clicked.connect(self.select_files)
        self.add_folder.clicked.connect(self.select_folder)
        self.clear.clicked.connect(self.clear_queue)
        self.choose_dest.clicked.connect(self.select_destination)
        self.open_dest.clicked.connect(self.open_folder)
        self.start.clicked.connect(self.run_batch)
        self.stop.clicked.connect(self.cancel_batch)
        self.save_log.clicked.connect(self.export_log)
        self.table.itemSelectionChanged.connect(self.select_preview)
        self.preview.currentIndexChanged.connect(self.change_media)
        self.play.clicked.connect(self.toggle_play)
        self.player.errorOccurred.connect(lambda *args: self.logs.appendPlainText(self.player.errorString()))
        self.seek.sliderReleased.connect(lambda: self.player.setPosition(self.seek.value()))
        self.player.durationChanged.connect(self.media_duration)
        self.player.positionChanged.connect(self.update_player)
        self.player.playbackStateChanged.connect(lambda state: self.play.set_playing(
            state == QMediaPlayer.PlaybackState.PlayingState))
        self.mode.currentIndexChanged.connect(self.update_export_labels)
        self.fmt.currentIndexChanged.connect(self.update_export_labels)
        self.quality.currentIndexChanged.connect(self.update_export_labels)
        self.cleanup.currentIndexChanged.connect(self.update_export_labels)
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
        self.queue_title.setText(f"Danh sách file • {len(self.files)} file")
        self.update_export_labels()
    def clear_queue(self):
        self.cancel_previews()
        self.player.stop()
        self.files.clear()
        self.outputs.clear()
        self.wave_cache.clear()
        self.table.setRowCount(0)
        self.preview.clear()
        self.preview.addItem("Chọn file để nghe thử", "")
        self.waveform.set_data([], 0)
        self.waveform.hint = "Chọn file để xem sóng âm"
        self.file_name.setText("Chọn video hoặc âm thanh để bắt đầu")
        self.file_meta.setText("MP3, WAV, FLAC, MP4, MKV và nhiều định dạng khác")
        self.queue_title.setText("Danh sách file • 0 file")
        self.update_export_labels()
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
            path = self.files[row]
            self.file_name.setText(Path(path).name)
            self.refresh_metadata(path)
            self.cancel_previews()
            if path in self.wave_cache:
                peaks, duration = self.wave_cache[path]
                self.waveform.set_data(peaks, duration)
            else:
                self.waveform.hint = "Đang đọc sóng âm…"
                self.waveform.set_data([], 0)
                preview = PreviewWorker(path)
                self.preview_workers.add(preview)
                self.active_preview = preview
                preview.ready.connect(self.preview_ready)
                preview.failed.connect(self.preview_failed)
                preview.finished.connect(lambda task=preview: self.release_preview(task))
                preview.start()
            self.preview.addItem("Gốc: " + Path(self.files[row]).name, self.files[row])
            for path in self.outputs.get(row, []):
                trial = " (thử 30s)" if Path(path).parent.name.startswith("Thu_30s_") else ""
                self.preview.addItem(Path(path).name + trial, path)
    def cancel_previews(self):
        for task in self.preview_workers:
            task.cancel.set()
    def release_preview(self, task):
        self.preview_workers.discard(task)
        if self.active_preview is task:
            self.active_preview = None
        task.deleteLater()
    def preview_ready(self, path, peaks, duration):
        self.wave_cache[path] = (peaks, duration)
        row = self.table.currentRow()
        if 0 <= row < len(self.files) and self.files[row] == path:
            self.waveform.set_data(peaks, duration)
            self.refresh_metadata(path)
    def preview_failed(self, path, message):
        row = self.table.currentRow()
        if 0 <= row < len(self.files) and self.files[row] == path:
            self.waveform.hint = "Chưa đọc được sóng âm. Xem nhật ký để biết chi tiết."
            self.waveform.update()
            self.logs.appendPlainText(message)
    def handle_wave(self, row, peaks, duration):
        if 0 <= row < len(self.files):
            self.preview_ready(self.files[row], peaks, duration)
    def refresh_metadata(self, path):
        source = Path(path)
        try:
            size = f"{source.stat().st_size / 2**20:.1f} MB"
        except OSError:
            size = "Không tìm thấy file"
        duration = self.wave_cache.get(path, ([], None))[1]
        length = clock(duration) if duration is not None else "Đang đọc…"
        self.file_meta.setText(f"Thời lượng: {length}   |   Kích thước: {size}   |   Định dạng: {source.suffix[1:].upper()}")
    def media_duration(self, value):
        self.seek.setRange(0, min(value, 2147483647))
        self.update_player(self.player.position())
    def update_export_labels(self):
        extract = self.mode.currentData() == "extract"
        speech = self.mode.currentData() == "speech"
        if speech and not self.cleanup.currentData():
            self.cleanup.setCurrentIndex(1)
        extension = self.fmt.currentText().lower()
        self.quality_note.setText("Giữ toàn bộ âm thanh, không chạy AI." if extract else
            "Mô hình lời thoại chạy CPU 2 luồng; có thể làm giọng đổi màu. Hãy thử 30 giây trước." if speech else
            MODES[self.quality.currentData()][1])
        busy = self.worker is not None and self.worker.isRunning()
        self.quality.setEnabled(not busy and not extract and not speech)
        self.cleanup.setEnabled(not busy and not extract)
        self.device.setEnabled(not busy and not extract and not speech)
        self.try_button.setEnabled(not busy)
        self.export_title.setText("Xuất âm thanh từ video / audio" if extract else "Lọc lời thoại đã tách" if speech else "Xuất giọng nói & nhạc nền")
        names = f"am_thanh.{extension}" if extract else f"giong_goc.{extension}  +  giong_loc.{extension}" if speech else (
            f"giong.{extension}  +  nhac_nen.{extension}" + (f"  +  giong_loc.{extension}" if self.cleanup.currentData() else ""))
        self.output_names.setText(names)
        count = len(self.files)
        action = "TRÍCH ÂM THANH" if extract else "LỌC LỜI THOẠI" if speech else "TÁCH NHẠC NỀN TỰ ĐỘNG"
        detail = f"Xử lý {count} file trong danh sách" if count > 1 else (
            "Giữ toàn bộ âm thanh của file" if extract else "Giữ cả bản trước và sau lọc" if speech else "Xuất giọng + nhạc nền riêng biệt")
        self.start.setText(action + "\n" + detail)
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
                       self.device, self.dest, self.choose_dest, self.start, self.quality, self.try_button, self.cleanup]:
            widget.setEnabled(not busy)
        self.stop.setEnabled(busy)
        if not busy:
            self.update_export_labels()
    def run_batch(self, sample=False):
        if not self.files:
            QMessageBox.information(self, "Chưa có file", "Hãy chọn một hoặc nhiều file trước.")
            return
        if not self.dest.text().strip():
            QMessageBox.warning(self, "Thiếu thư mục", "Hãy chọn thư mục xuất.")
            return
        selected = self.table.currentRow()
        self.sample_run = bool(sample)
        self.active_rows = [selected if selected >= 0 else 0] if sample else list(range(len(self.files)))
        preview_start = (self.player.position() / 1000 if self.preview.currentData() == self.files[self.active_rows[0]] else 0) if sample else None
        self.player.stop()
        self.cancel_previews()
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        self.error_message.hide()
        if not sample:
            self.outputs.clear()
        for row in self.active_rows:
            self.table.item(row, 1).setText("Chờ xử lý")
            self.table.item(row, 2).setText("")
        self.lock(True)
        self.worker = BatchWorker([self.files[row] for row in self.active_rows], str(Path(self.dest.text().strip()).expanduser()),
            self.mode.currentData(), self.fmt.currentText().lower(),
            self.device.currentData() if self.mode.currentData() == "separate" else "cpu",
            self.quality.currentData(), self.active_rows, preview_start, self.cleanup.currentData())
        self.worker.status.connect(self.handle_status)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.wave.connect(self.handle_wave)
        self.worker.log.connect(self.append_log)
        self.worker.error.connect(self.show_error)
        self.worker.output.connect(self.add_output)
        self.worker.completed.connect(self.batch_summary)
        self.worker.finished.connect(lambda: self.lock(False))
        self.worker.start()
    def add_output(self, row, paths):
        self.outputs[row] = self.outputs.get(row, []) + paths if self.sample_run else paths
        self.table.item(row, 2).setText(" • ".join(Path(p).name for p in paths))
        self.table.item(row, 2).setToolTip("\n".join(paths))
        if self.table.currentRow() == row:
            self.select_preview()
    def append_log(self, message):
        self.logs.appendPlainText(message)
        if message.startswith("Lọc bổ sung chưa hoàn tất"):
            self.error_message.setText(message)
            self.error_message.show()
            self.log_toggle.setChecked(True)
    def handle_status(self, row, text):
        item = self.table.item(row, 1)
        item.setText("Thử 30s xong" if self.sample_run and text == "Hoàn tất" else text)
        color = "#ff9393" if text.startswith("Lỗi") else "#ffc783" if "lỗi" in text.lower() else "#6adca5" if text == "Hoàn tất" else "#9fbfff"
        item.setForeground(QColor(color))
    def batch_summary(self, ok, failed, cancelled):
        if not cancelled:
            self.progress.setValue(100)
        else:
            for row in self.active_rows:
                if self.table.item(row, 1).text() == "Chờ xử lý":
                    self.table.item(row, 1).setText("Chưa xử lý — đã dừng")
        self.logs.appendPlainText(f"\n{'Đã dừng' if cancelled else 'Hoàn tất'}: {ok} thành công, {failed} lỗi.")
        self.progress.setFormat(f"{'Đã dừng' if cancelled else 'Kết thúc'}: {ok} thành công, {failed} lỗi")
        if self.sample_run:
            self.progress.setFormat(f"Thử 30s: {ok} thành công, {failed} lỗi")
    def show_error(self, row, message):
        lines = [line.strip() for line in message.splitlines() if line.strip()]
        details = [line for line in lines if "Error:" in line or "Exception:" in line]
        reason = (details[-1] if details else lines[-1] if lines else "Lỗi không có thông tin")
        self.error_message.setText(f"{Path(self.files[row]).name}: {reason[:350]}")
        self.error_message.show()
        self.log_toggle.setChecked(True)
    def export_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Lưu nhật ký", "music-cleaner-log.txt", "Text (*.txt)")
        if path:
            try:
                Path(path).write_text(self.logs.toPlainText(), encoding="utf-8")
            except OSError as error:
                QMessageBox.warning(self, "Không lưu được nhật ký", str(error))
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
        elif self.preview_workers:
            self.cancel_previews()
            event.ignore()
            self.logs.appendPlainText("Đang dừng đọc sóng âm; đóng cửa sổ lại sau giây lát.")
        else:
            self.player.stop()
            self.player.setSource(QUrl())
            event.accept()


STYLE = """
QWidget { background: #07121c; color: #e8f0fb; font-family: 'Segoe UI'; font-size: 14px; }
QScrollArea, QScrollArea > QWidget > QWidget { border: none; }
QFrame#card { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #11212e,stop:1 #0d1b27); border: 1px solid #294153; border-radius: 15px; }
QLabel { background: transparent; }
QLabel#title { font-size: 38px; font-weight: 700; color: #f6f8fc; }
QLabel#subtitle { font-size: 17px; color: #9fb8ce; }
QLabel#section { font-size: 19px; font-weight: 700; }
QLabel#fileName { font-size: 20px; font-weight: 600; }
QLabel#muted { color: #9cb3c8; }
QLabel#badge { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #147fff,stop:1 #4b36f1); border: 1px solid #7b83ff; border-radius: 12px; font-size: 22px; font-weight: 700; }
QLabel#fileIcon { background: #217fc2; border: 1px solid #49b1ff; border-radius: 14px; font-size: 38px; }
QPushButton { background: #122432; border: 1px solid #3b566c; border-radius: 9px; padding: 9px 14px; }
QPushButton:hover { background: #203c52; border-color: #6498c3; }
QPushButton:checked { background: #234462; }
QPushButton:disabled { color: #657d91; background: #10202c; border-color: #263b4b; }
QPushButton#primary { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #227fff,stop:1 #174bff); border: 1px solid #4babff; border-radius: 14px; font-size: 17px; font-weight: 700; padding: 20px; }
QPushButton#primary:hover { background: #387cff; }
QPushButton#primary:disabled { background: #1e3d75; color: #8dabc8; }
QPushButton#play { background: #206cff; border: 1px solid #5aa5ff; border-radius: 32px; font-size: 27px; }
QLineEdit, QComboBox, QPlainTextEdit { background: #0a1925; border: 1px solid #385269; border-radius: 8px; padding: 9px; selection-background-color: #235b9e; }
QLineEdit:read-only { color: #bed1e5; }
QComboBox QAbstractItemView { background: #102635; selection-background-color: #235b9e; }
QComboBox::drop-down { border: none; width: 25px; }
QTableWidget { background: #0c1b27; border: 1px solid #2a4153; border-radius: 9px; selection-background-color: #193b58; selection-color: #f4f8ff; }
QHeaderView::section { background: #142b3d; color: #c6d8e9; padding: 9px; border: none; }
QTableWidget::item { padding: 7px; border-bottom: 1px solid #1e3445; }
QProgressBar { background: #0b1b29; border: 1px solid #2c455c; border-radius: 7px; text-align: center; }
QProgressBar::chunk { background: #297bff; border-radius: 6px; }
QSlider::groove:horizontal { height: 7px; background: #2a3f51; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #277cff; border-radius: 3px; }
QSlider::handle:horizontal { width: 15px; background: #8fbaff; margin: -4px 0; border-radius: 7px; }
QScrollBar:vertical { background: #0b1c29; width: 10px; }
QScrollBar::handle:vertical { background: #35536c; min-height: 25px; border-radius: 4px; }
"""

def main():
    validate_platform()
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    window = Window()
    window.show()
    sys.exit(app.exec())
if __name__ == "__main__":
    main()

