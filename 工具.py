import sys
import os
import threading
import subprocess
import json
import time
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                             QPushButton, QComboBox, QTextEdit, QListWidget,
                             QLabel, QWidget, QFileDialog, QSplitter, QCheckBox)
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from PyQt5.QtGui import QPixmap, QIcon

class LoggerSignals(QObject):
    log = pyqtSignal(str)
    apps_loaded = pyqtSignal(list)
    set_btn_state = pyqtSignal(bool)

class FridaWorkbench(QMainWindow):
    def __init__(self):
        super().__init__()
        # 信号初始化
        self.signals = LoggerSignals()
        self.signals.log.connect(self.append_log)
        self.signals.apps_loaded.connect(self.update_app_list)
        self.signals.set_btn_state.connect(self.set_refresh_btn_state)

        self.current_script_dir = ""
        self.current_script_path = ""
        self.log_dir = ""
        self.frida_process = None
        self.is_running = False

        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Frida 工作站 (洛哥专属保佑版)")
        self.resize(1580, 950)

        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)

        # --- 左侧：脚本库 ---
        left_panel = QVBoxLayout()
        left_panel.addWidget(QLabel("📂 脚本库 (.js)"))
        self.btn_choose_dir = QPushButton("选择脚本文件夹")
        self.btn_choose_dir.clicked.connect(self.select_script_directory)
        left_panel.addWidget(self.btn_choose_dir)
        self.script_list = QListWidget()
        self.script_list.itemClicked.connect(self.on_script_selected)
        left_panel.addWidget(self.script_list)

        # --- 中间：控制区 (增加佛祖保佑图) ---
        mid_panel = QVBoxLayout()

        # [1. Conda & 进程]
        mid_panel.addWidget(QLabel("🛠️ Conda 环境:"))
        self.combo_env = QComboBox()
        self.combo_env.addItems(["base", "ios16", "f38"])
        mid_panel.addWidget(self.combo_env)

        mid_panel.addSpacing(10)
        self.btn_refresh_apps = QPushButton("🔄 刷新 App 列表")
        self.btn_refresh_apps.clicked.connect(self.fetch_apps)
        mid_panel.addWidget(self.btn_refresh_apps)

        self.input_target = QComboBox()
        self.input_target.setEditable(True)
        self.input_target.setPlaceholderText("请选择或输入包名...")
        mid_panel.addWidget(self.input_target)

        mid_panel.addSpacing(10)
        self.check_spawn = QCheckBox("启用 Spawn 模式 (-f)")
        mid_panel.addWidget(self.check_spawn)

        # [2. 关键改动：增加佛祖保佑图区域]
        mid_panel.addStretch(1)  # 弹簧挤压，让图在中间

        # 容器
        buddha_container = QWidget()
        buddha_layout = QVBoxLayout(buddha_container)
        buddha_layout.setAlignment(Qt.AlignCenter)  # 整体居中
        buddha_layout.setContentsMargins(0, 10, 0, 10)

        # 加载图片
        self.label_buddha = QLabel()
        pixmap = QPixmap("buddha.jpg")  # 确保 buddha.jpg 在同目录下

        if not pixmap.isNull():
            # 缩放图片，保持比例，高度限制在 280px 左右
            scaled_pixmap = pixmap.scaledToHeight(280, Qt.SmoothTransformation)
            self.label_buddha.setPixmap(scaled_pixmap)
            self.label_buddha.setToolTip("佛祖保佑，Sign 无忧，DEX 尽出。")
        else:
            self.label_buddha.setText(">>> 佛祖正在来的路上...")
            self.label_buddha.setStyleSheet("color: #ffa500; font-size: 14px; font-weight: bold;")

        # 加个保佑文字
        label_text = QLabel(">>> 极客禅 · 逆向平安 <<<")
        label_text.setStyleSheet("color: #ffa500; font-family: 'Consolas'; font-size: 11px;")
        label_text.setAlignment(Qt.AlignCenter)

        buddha_layout.addWidget(self.label_buddha)
        buddha_layout.addWidget(label_text)
        mid_panel.addWidget(buddha_container)

        mid_panel.addStretch(1)  # 弹簧挤压

        # [3. 日志设置 & 操作按钮]
        mid_panel.addWidget(QLabel("💾 日志保存:"))
        self.btn_log_dir = QPushButton("选择存储文件夹")
        self.btn_log_dir.clicked.connect(self.select_log_directory)
        mid_panel.addWidget(self.btn_log_dir)
        self.label_log_path = QLabel("日志不保存")
        self.label_log_path.setStyleSheet("color: gray; font-size: 10px;")
        self.label_log_path.setAlignment(Qt.AlignCenter)
        mid_panel.addWidget(self.label_log_path)

        mid_panel.addSpacing(20)
        self.btn_run = QPushButton("⚡ 开始注入")
        self.btn_run.setMinimumHeight(55)
        self.btn_run.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; font-size: 15px;")
        self.btn_run.clicked.connect(self.start_frida)
        mid_panel.addWidget(self.btn_run)

        self.btn_stop = QPushButton("🛑 停止 Hook")
        self.btn_stop.setMinimumHeight(55)
        self.btn_stop.setStyleSheet("background-color: #dc3545; color: white; font-weight: bold;")
        self.btn_stop.clicked.connect(self.stop_frida)
        mid_panel.addWidget(self.btn_stop)

        # --- 右侧：日志输出 (增加提示) ---
        self.log_output = QTextEdit()
        self.log_output.setStyleSheet(
            "background-color: #121212; color: #00FF00; font-family: 'Consolas'; font-size: 11pt;")
        self.log_output.setReadOnly(True)
        # 增加初始化提示
        import datetime
        now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.log_output.setText(f"[{now}] >>> Frida 工作站已就绪，请放心食用。\n" + "-" * 60 + "\n")

        # --- 布局拆分与比例 (优化比例让中间不卡) ---
        splitter = QSplitter(Qt.Horizontal)
        w_left = QWidget();
        w_left.setLayout(left_panel)
        w_mid = QWidget();
        w_mid.setLayout(mid_panel)
        splitter.addWidget(w_left);
        splitter.addWidget(w_mid);
        splitter.addWidget(self.log_output)

        # 优化比例：左侧窄点，日志区最宽
        splitter.setSizes([300, 480, 800]) # 1580
        splitter.setStretchFactor(2, 1)  # 让日志区自动拉伸

        main_layout.addWidget(splitter)
        self.setCentralWidget(main_widget)

    # --- 核心逻辑 (保持不变，确保卡顿已解决) ---
    def fetch_apps(self):
        env_name = self.combo_env.currentText()
        self.signals.set_btn_state.emit(False)
        self.append_log(f"[*] 正在获取进程 (环境: {env_name})...")

        def run():
            try:
                cmd = f'conda run --no-capture-output -n {env_name} frida-ps -Ua --json'
                # 增加超时
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8', timeout=15)
                stdout = result.stdout.strip()
                start = stdout.find('[');
                end = stdout.rfind(']')
                if start != -1 and end != -1:
                    apps_data = json.loads(stdout[start:end + 1])
                    app_list = [f"{app.get('name')} ({app.get('identifier')})" for app in apps_data]
                    app_list.sort()
                    self.signals.apps_loaded.emit(app_list)
                else:
                    self.signals.log.emit("[X] 查询失败：请确认 frida-server 状态")
            except Exception as e:
                self.signals.log.emit(f"[X] 查询异常: {str(e)}")
            finally:
                self.signals.set_btn_state.emit(True)

        threading.Thread(target=run, daemon=True).start()

    def start_frida(self):
        if self.is_running: return
        env_name = self.combo_env.currentText()
        raw_target = self.input_target.currentText()
        target = raw_target.split("(")[-1].split(")")[0] if "(" in raw_target else raw_target

        if not self.current_script_path:
            self.append_log("[!] 请先选择脚本")
            return

        mode_flag = "-f" if self.check_spawn.isChecked() else "-F"
        mode_desc = "Spawn" if self.check_spawn.isChecked() else "Attach"

        log_file_path = None
        if self.log_dir:
            log_file_path = os.path.join(self.log_dir, f"{target}_{int(time.time())}.txt")

        cmd = f'conda run --no-capture-output -n {env_name} frida -U {mode_flag} {target} -l "{self.current_script_path}"'
        self.append_log(f"[*] 启动任务 | 模式: {mode_desc} | 目标: {target}")

        self.is_running = True
        threading.Thread(target=self.run_process, args=(cmd, log_file_path), daemon=True).start()

    def run_process(self, cmd, log_path):
        try:
            self.frida_process = subprocess.Popen(
                cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', bufsize=1
            )
            f = open(log_path, "w", encoding="utf-8") if log_path else None

            while self.is_running:
                line = self.frida_process.stdout.readline()
                if not line and self.frida_process.poll() is not None: break
                if line:
                    self.signals.log.emit(line.strip())
                    if f: f.write(line); f.flush()
            if f: f.close()
        finally:
            self.is_running = False
            self.signals.log.emit("[*] Hook 会话结束。")

    def stop_frida(self):
        self.is_running = False
        if self.frida_process:
            if os.name == 'nt':
                subprocess.run(f"taskkill /F /T /PID {self.frida_process.pid}", shell=True)
            else:
                self.frida_process.terminate()
            self.frida_process = None
            self.append_log("[🛑] 已强制停止。")

    # --- 界面交互逻辑 ---
    def select_script_directory(self):
        path = QFileDialog.getExistingDirectory(self, "选择脚本目录")
        if path:
            self.current_script_dir = path
            self.script_list.clear()
            self.script_list.addItems([f for f in os.listdir(path) if f.endswith('.js')])

    def on_script_selected(self, item):
        self.current_script_path = os.path.join(self.current_script_dir, item.text())
        self.append_log(f"[I] 已选中脚本: {item.text()}")

    def select_log_directory(self):
        path = QFileDialog.getExistingDirectory(self, "选择日志目录")
        if path:
            self.log_dir = path
            self.label_log_path.setText(f"保存至: {os.path.basename(path)}")
            self.label_log_path.setStyleSheet("color: #00ff00; font-size: 10px;")

    def update_app_list(self, app_list):
        self.input_target.clear()
        self.input_target.addItems(app_list)
        self.append_log(f"[√] 已同步设备 {len(app_list)} 个进程")

    def set_refresh_btn_state(self, state):
        self.btn_refresh_apps.setEnabled(state)

    def append_log(self, text):
        self.log_output.append(text)
        self.log_output.moveCursor(self.log_output.textCursor().End)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = FridaWorkbench()
    window.show()
    sys.exit(app.exec_())