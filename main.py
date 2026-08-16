import sys
import json
import os
import zipfile
import shutil
from datetime import datetime
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                             QListWidget, QListWidgetItem, QPushButton, QLineEdit, QLabel,
                             QFileDialog, QMenu, QMessageBox, QStackedWidget, QTabBar,
                             QProgressBar, QScrollArea, QFrame, QDialog, QDialogButtonBox,
                             QGroupBox, QTextEdit, QSizePolicy, QFormLayout, QTabWidget,
                             QRadioButton, QButtonGroup)
from PyQt5.QtGui import QIcon, QPixmap, QFont
from PyQt5.QtCore import Qt, QDir, QPoint, QSize, QThread, pyqtSignal

CONFIG_FILE = "aoi_hub_config.json"
DOWNLOAD_DIR = "./downloads"
INSTALL_ROOT = "./installed"
GITHUB_API_URL = "https://api.github.com/repos/yukaishou/AoiStudio/releases"
EXAMPLE_GITHUB_API_URL = "https://api.github.com/repos/yukaishou/AoiStudio_ExampleProjects/releases"
LOCAL_DOWNLOAD_JSON_PATH = "./config/download.json"
FILTER_PREFIXES = ("AoiStudio_Public", "AoiStudio_Release", "AoiStudio_Preview")
EXAMPLE_FILTER_PREFIX = "Aoi_"
EXAMPLE_PROJECT_ROOT = "./example_projects"

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(INSTALL_ROOT, exist_ok=True)
os.makedirs("./config", exist_ok=True)
os.makedirs(EXAMPLE_PROJECT_ROOT, exist_ok=True)


# ==========【新增】新建项目弹窗（参考UnityHub风格） ==========
class CreateProjectDialog(QDialog):
    def __init__(self, installed_versions: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建AoiStudio项目")
        self.setWindowIcon(QIcon("icon.png"))
        self.resize(640, 460)
        self.installed_versions = installed_versions
        self.selected_version: InstalledVersion = None
        self.project_folder = ""

        layout = QVBoxLayout(self)

        # 选择编辑器版本
        grp_ver = QGroupBox("选择编辑器版本")
        ver_layout = QVBoxLayout(grp_ver)
        self.list_ver = QListWidget()
        for ver in self.installed_versions:
            item_text = f"[{ver.tag}] {ver.name}\n{ver.download_time}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, ver)
            self.list_ver.addItem(item)
        ver_layout.addWidget(self.list_ver)
        layout.addWidget(grp_ver)

        # 项目名称、存储位置
        form_layout = QFormLayout()
        self.edit_proj_name = QLineEdit("MyNewProject")
        self.edit_proj_path = QLineEdit("./workspace")
        btn_browse_path = QPushButton("浏览...")
        btn_browse_path.clicked.connect(self.select_save_dir)

        path_row = QHBoxLayout()
        path_row.addWidget(self.edit_proj_path)
        path_row.addWidget(btn_browse_path)
        form_layout.addRow("项目名称：", self.edit_proj_name)
        form_layout.addRow("保存位置：", path_row)
        layout.addLayout(form_layout)

        # 项目模板选择
        grp_template = QGroupBox("项目模板")
        temp_layout = QVBoxLayout(grp_template)
        self.radio_empty = QRadioButton("空白文件夹")
        self.radio_example = QRadioButton("内置空白项目模板(复制 Editor/res/project_example)")
        self.template_group = QButtonGroup()
        self.template_group.addButton(self.radio_empty, 0)
        self.template_group.addButton(self.radio_example, 1)
        self.radio_empty.setChecked(True)
        temp_layout.addWidget(self.radio_empty)
        temp_layout.addWidget(self.radio_example)
        layout.addWidget(grp_template)

        # 按钮
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("创建")
        btns.accepted.connect(self.on_ok)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def select_save_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "选择项目保存根目录")
        if folder:
            self.edit_proj_path.setText(folder)

    def on_ok(self):
        ver_item = self.list_ver.currentItem()
        if not ver_item:
            QMessageBox.warning(self, "提示", "请选择一个编辑器版本！")
            return
        self.selected_version = ver_item.data(Qt.UserRole)

        proj_name = self.edit_proj_name.text().strip()
        save_root = self.edit_proj_path.text().strip()
        if not proj_name:
            QMessageBox.warning(self, "提示", "项目名称不能为空！")
            return
        if not os.path.exists(save_root):
            try:
                os.makedirs(save_root, exist_ok=True)
            except Exception as e:
                QMessageBox.warning(self, "路径错误", f"无法创建保存目录：{e}")
                return

        self.project_folder = os.path.join(save_root, proj_name)
        if os.path.exists(self.project_folder):
            QMessageBox.warning(self, "提示", f"项目文件夹已存在：{self.project_folder}")
            return

        self.accept()

    def get_template_mode(self):
        return 1 if self.radio_example.isChecked() else 0


# ==========【新增】选择编辑器版本弹窗（用于命令行传入项目路径时） ==========
class SelectEditorVersionDialog(QDialog):
    def __init__(self, installed_versions: list, target_project_path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择编辑器版本打开项目")
        self.setWindowIcon(QIcon("icon.png"))
        self.resize(620,420)
        self.installed_versions = installed_versions
        self.target_project_path = target_project_path
        self.selected_version: InstalledVersion = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"项目路径：{target_project_path}\n请选择一个本地已安装编辑器版本："))

        self.list_widget = QListWidget()
        for ver in self.installed_versions:
            item_text = f"[{ver.tag}] {ver.name}\n下载时间:{ver.download_time}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, ver)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.on_ok)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def on_ok(self):
        item = self.list_widget.currentItem()
        if not item:
            QMessageBox.warning(self, "提示", "请选择一个编辑器版本！")
            return
        self.selected_version = item.data(Qt.UserRole)
        self.accept()

# -------- 设置对话框：代理 + 自定义编辑器路径 --------
class SettingDialog(QDialog):
    def __init__(self, proxy_conf, editor_exe_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("全局设置")
        self.resize(480, 280)
        self.proxy_conf = proxy_conf.copy()
        self.editor_exe_path = editor_exe_path

        layout = QVBoxLayout(self)

        group_proxy = QGroupBox("HTTP/HTTPS代理")
        glay = QFormLayout(group_proxy)
        self.edit_http = QLineEdit(self.proxy_conf.get("http", ""))
        self.edit_https = QLineEdit(self.proxy_conf.get("https", ""))
        glay.addRow("HTTP:", self.edit_http)
        glay.addRow("HTTPS:", self.edit_https)
        layout.addWidget(group_proxy)

        group_editor = QGroupBox("自定义编辑器EXE")
        edlay = QHBoxLayout(group_editor)
        self.edit_editor_path = QLineEdit(self.editor_exe_path)
        btn_browse_exe = QPushButton("浏览...")
        btn_browse_exe.clicked.connect(self.select_exe)
        edlay.addWidget(self.edit_editor_path)
        edlay.addWidget(btn_browse_exe)
        layout.addWidget(group_editor)

        hint = QLabel("代理示例：http://127.0.0.1:7890；EXE留空则默认查找AoiStudio.exe")
        layout.addWidget(hint)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def select_exe(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择编辑器exe", "", "EXE文件(*.exe)")
        if path:
            self.edit_editor_path.setText(path)

    def get_values(self):
        proxy = {
            "http": self.edit_http.text().strip(),
            "https": self.edit_https.text().strip()
        }
        exe = self.edit_editor_path.text().strip()
        return proxy, exe


# -------- Github后台拉取线程（普通release） --------
class GithubFetchThread(QThread):
    finished_signal = pyqtSignal(list)
    error_signal = pyqtSignal(str)

    def __init__(self, api_url, proxies=None, filter_prefix=None):
        super().__init__()
        self.api_url = api_url
        self.proxies = proxies
        self.filter_prefix = filter_prefix

    def run(self):
        try:
            resp = requests.get(self.api_url, timeout=18, verify=False, proxies=self.proxies)
            resp.raise_for_status()
            releases = resp.json()
            result = []
            for rel in releases:
                tag_name = rel.get("tag_name", "")
                published_at = rel.get("published_at", "")
                body = rel.get("body", "")
                assets = rel.get("assets", [])
                filtered_assets = []
                for ast in assets:
                    name = ast.get("name", "")
                    dl_url = ast.get("browser_download_url", "")
                    size = ast.get("size", 0)
                    if self.filter_prefix is None:
                        filtered_assets.append({"name": name, "url": dl_url, "size": size})
                    elif isinstance(self.filter_prefix, tuple):
                        if name.startswith(self.filter_prefix):
                            filtered_assets.append({"name": name, "url": dl_url, "size": size})
                    elif isinstance(self.filter_prefix, str):
                        if name.startswith(self.filter_prefix):
                            filtered_assets.append({"name": name, "url": dl_url, "size": size})
                if filtered_assets:
                    result.append({
                        "tag": tag_name,
                        "publish": published_at,
                        "body": body,
                        "assets": filtered_assets
                    })
            self.finished_signal.emit(result)
        except Exception as e:
            self.error_signal.emit(str(e))


# -------- 下载+解压线程（支持取消） --------
class DownloadUnzipThread(QThread):
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, download_url, save_path, extract_dir, proxies=None):
        super().__init__()
        self.download_url = download_url
        self.save_path = save_path
        self.extract_dir = extract_dir
        self.proxies = proxies
        self._cancel_flag = False

    def cancel(self):
        self._cancel_flag = True

    def run(self):
        try:
            resp = requests.get(self.download_url, stream=True, timeout=35, verify=False, proxies=self.proxies)
            resp.raise_for_status()
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            with open(self.save_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if self._cancel_flag:
                        raise Exception("用户取消下载")
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = int((downloaded / total) * 100)
                            self.progress_signal.emit(pct)
            if self._cancel_flag:
                raise Exception("用户取消下载")

            if self.save_path.lower().endswith(".zip"):
                with zipfile.ZipFile(self.save_path, 'r') as zip_ref:
                    zip_ref.extractall(self.extract_dir)
            self.finished_signal.emit({
                "zip_path": self.save_path,
                "install_dir": self.extract_dir,
                "download_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        except Exception as e:
            self.error_signal.emit(str(e))


# -------- 项目模型 --------
class ProjectItem:
    def __init__(self, name="", path="", version="", last_open="", thumbnail=""):
        self.name = name
        self.path = path
        self.version = version
        self.last_open = last_open
        self.thumbnail = thumbnail

    def to_dict(self):
        return self.__dict__

    @staticmethod
    def from_dict(d):
        return ProjectItem(**d)


# -------- 本地已安装版本模型 --------
class InstalledVersion:
    def __init__(self, tag="", name="", install_path="", download_time=""):
        self.tag = tag
        self.name = name
        self.install_path = install_path
        self.download_time = download_time

    def to_dict(self):
        return self.__dict__

    @staticmethod
    def from_dict(d):
        return InstalledVersion(**d)


# -------- Release版本卡片 --------
class ReleaseCard(QFrame):
    def __init__(self, release_info, proxies, parent_hub, installed_tag_set, installed_map):
        super().__init__()
        self.release_info = release_info
        self.proxies = proxies
        self.parent_hub = parent_hub
        self.installed_tag_set = installed_tag_set
        self.installed_map = installed_map
        self.tag = release_info["tag"]
        self.source = release_info.get("source", "github")
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("QFrame{background:#383838;border-radius:6px;padding:12px;margin:4px;}")
        layout = QVBoxLayout(self)

        publish = release_info["publish"][:10]
        body_text = release_info.get("body", "")

        exist_mark = "【✅本地已安装】" if self.tag in self.installed_tag_set else ""
        src_mark = "【JSON本地源】" if self.source == "json" else ""
        lbl_title = QLabel(f"<b>{self.tag}</b> {exist_mark} {src_mark} | {publish}")
        lbl_title.setFont(QFont("", 11))
        layout.addWidget(lbl_title)

        if body_text:
            txt_body = QTextEdit()
            txt_body.setReadOnly(True)
            txt_body.setMaximumHeight(100)
            txt_body.setPlainText(body_text[:1200])
            txt_body.setStyleSheet("background:#2e2e2e;color:#ddd;border:none;")
            layout.addWidget(txt_body)

        self.asset_widgets = []
        for ast in release_info["assets"]:
            name = ast["name"]
            url = ast["url"]
            size_bytes = ast.get("size", 0)
            size_mb = round(size_bytes / 1024 / 1024, 2)

            row = QHBoxLayout()
            lbl_name = QLabel(f"{name}  ({size_mb} MB)")
            btn_dl = QPushButton("下载&安装")
            btn_dl.setFixedWidth(100)
            btn_open_dir = QPushButton("打开安装目录")
            btn_open_dir.setFixedWidth(110)
            btn_open_dir.setEnabled(self.tag in self.installed_tag_set)

            def open_dir_click(tg=self.tag):
                ver: InstalledVersion = self.installed_map.get(tg)
                if ver and os.path.exists(ver.install_path):
                    os.startfile(ver.install_path)
                else:
                    QMessageBox.warning(self, "提示", "安装目录不存在")

            btn_open_dir.clicked.connect(open_dir_click)
            btn_dl.clicked.connect(lambda checked, u=url, n=name, t=self.tag, b=btn_dl: self.on_download(u, n, t, b))
            row.addWidget(lbl_name)
            row.addStretch()
            row.addWidget(btn_open_dir)
            row.addSpacing(6)
            row.addWidget(btn_dl)
            layout.addLayout(row)
            self.asset_widgets.append((btn_dl, btn_open_dir))

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        self.dl_thread: DownloadUnzipThread = None

    def on_download(self, dl_url, filename, tag, btn: QPushButton):
        save_path = os.path.join(DOWNLOAD_DIR, filename)
        install_subdir = os.path.join(INSTALL_ROOT, f"{tag}_{os.path.splitext(filename)[0]}")
        if os.path.exists(save_path):
            ret = QMessageBox.question(self, "文件已存在", f"{filename}已存在，是否重新下载并解压？")
            if ret != QMessageBox.Yes:
                return

        btn.setText("取消")
        btn.clicked.disconnect()
        btn.clicked.connect(self.on_cancel_download)

        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.dl_thread = DownloadUnzipThread(dl_url, save_path, install_subdir, proxies=self.proxies)
        self.dl_thread.progress_signal.connect(self.progress_bar.setValue)
        self.dl_thread.finished_signal.connect(lambda res, b=btn, t=tag, fn=filename: self.on_download_finish(res, b, t, fn))
        self.dl_thread.error_signal.connect(lambda err, b=btn: self.on_download_error(err, b))
        self.dl_thread.start()

    def on_cancel_download(self):
        if self.dl_thread:
            self.dl_thread.cancel()

    def restore_download_button(self, btn: QPushButton):
        btn.setText("下载&安装")
        try:
            btn.clicked.disconnect()
        except Exception:
            pass

    def on_download_finish(self, res, btn: QPushButton, tag, filename):
        self.restore_download_button(btn)
        self.progress_bar.setVisible(False)
        ver = InstalledVersion(tag=tag, name=filename, install_path=res["install_dir"], download_time=res["download_time"])
        self.parent_hub.add_installed_version(ver)
        QMessageBox.information(self, "下载&解压完成",
                                f"压缩包:{res['zip_path']}\n解压目录:{res['install_dir']}\n下载时间:{res['download_time']}\n已添加到本地版本列表")

    def on_download_error(self, err, btn: QPushButton):
        self.restore_download_button(btn)
        self.progress_bar.setVisible(False)
        if "取消" in err:
            QMessageBox.information(self, "已取消", "下载已被用户取消")
        else:
            QMessageBox.warning(self, "下载失败", err)


# ==========【新增】示例项目卡片 ==========
class ExampleProjectCard(QFrame):
    def __init__(self, release_info, proxies, parent_hub):
        super().__init__()
        self.release_info = release_info
        self.proxies = proxies
        self.parent_hub = parent_hub
        self.tag = release_info["tag"]
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("QFrame{background:#304048;border-radius:6px;padding:12px;margin:4px;}")
        layout = QVBoxLayout(self)

        publish = release_info["publish"][:10]
        body_text = release_info.get("body", "")

        lbl_title = QLabel(f"<b>示例项目 {self.tag}</b> | {publish}")
        lbl_title.setFont(QFont("",11))
        layout.addWidget(lbl_title)

        if body_text:
            txt_body = QTextEdit()
            txt_body.setReadOnly(True)
            txt_body.setMaximumHeight(80)
            txt_body.setPlainText(body_text[:1000])
            txt_body.setStyleSheet("background:#243036;color:#ddd;border:none;")
            layout.addWidget(txt_body)

        self.asset_widgets = []
        for ast in release_info["assets"]:
            name = ast["name"]
            url = ast["url"]
            size_bytes = ast.get("size",0)
            size_mb = round(size_bytes/1024/1024,2)

            row = QHBoxLayout()
            lbl_name = QLabel(f"{name} ({size_mb} MB)")
            btn_dl = QPushButton("下载示例项目")
            btn_dl.setFixedWidth(120)

            btn_dl.clicked.connect(lambda checked,u=url,n=name,b=btn_dl:self.on_download(u,n,b))
            row.addWidget(lbl_name)
            row.addStretch()
            row.addWidget(btn_dl)
            layout.addLayout(row)
            self.asset_widgets.append(btn_dl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        self.dl_thread:DownloadUnzipThread = None

    def on_download(self,dl_url,filename,btn:QPushButton):
        save_path = os.path.join(DOWNLOAD_DIR,filename)
        proj_name_noext = os.path.splitext(filename)[0]
        extract_dir = os.path.join(EXAMPLE_PROJECT_ROOT, proj_name_noext)
        if os.path.exists(save_path):
            ret = QMessageBox.question(self,"文件已存在",f"{filename}已存在，是否重新下载？")
            if ret != QMessageBox.Yes:
                return

        btn.setText("取消")
        btn.clicked.disconnect()
        btn.clicked.connect(self.on_cancel_download)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.dl_thread = DownloadUnzipThread(dl_url,save_path,extract_dir,self.proxies)
        self.dl_thread.progress_signal.connect(self.progress_bar.setValue)
        self.dl_thread.finished_signal.connect(lambda res,b=btn,fn=filename:self.on_finish(res,b,fn))
        self.dl_thread.error_signal.connect(lambda err,b=btn:self.on_error(err,b))
        self.dl_thread.start()

    def on_cancel_download(self):
        if self.dl_thread:
            self.dl_thread.cancel()

    def restore_btn(self,btn:QPushButton):
        btn.setText("下载示例项目")
        try:
            btn.clicked.disconnect()
        except:pass

    def on_finish(self,res,btn,filename):
        self.restore_btn(btn)
        self.progress_bar.setVisible(False)
        proj_folder = res["install_dir"]
        # 添加到项目列表
        new_proj = ProjectItem(
            name=os.path.basename(proj_folder),
            path=proj_folder,
            version="Example",
            last_open=datetime.now().strftime("%Y-%m-%d %H:%M"),
            thumbnail=""
        )
        self.parent_hub.projects.append(new_proj)
        self.parent_hub.save_full_config()
        self.parent_hub.refresh_ui()
        QMessageBox.information(self,"示例项目下载完成",
                                f"压缩包:{res['zip_path']}\n解压目录:{proj_folder}\n已经自动添加到项目列表！")

    def on_error(self,err,btn):
        self.restore_btn(btn)
        self.progress_bar.setVisible(False)
        if "取消" in err:
            QMessageBox.information(self,"已取消","下载已取消")
        else:
            QMessageBox.warning(self,"下载失败",err)


# -------- 主窗口 --------
class AoiStudioHub(QMainWindow):
    def __init__(self, cli_project_path=None):
        super().__init__()
        self.setWindowTitle("AoiStudioHub")
        self.setWindowIcon(QIcon("icon.png"))
        self.resize(1300, 840)

        self.projects: list[ProjectItem] = []
        self.installed_versions: list[InstalledVersion] = []
        self.proxy_config = {"http": "", "https": ""}
        self.editor_custom_exe = ""
        self.release_list = []
        self.example_release_list = []

        self.load_full_config()

        # 如果命令行带项目路径，直接弹窗选择版本打开
        if cli_project_path and os.path.isdir(cli_project_path):
            if self.installed_versions:
                dlg = SelectEditorVersionDialog(self.installed_versions, cli_project_path)
                res = dlg.exec_()
                if res == QDialog.Accepted:
                    self.launch_editor_with_project(dlg.selected_version, cli_project_path)

        self.setStyleSheet("""
QMainWindow{background:#2c2c2c;color:#eeeeee;}
QWidget{background:#2c2c2c;color:#eeeeee;font-family:Microsoft YaHei;}
QPushButton{background:#444444;border:none;padding:6px 12px;border-radius:3px;color:#eee;}
QPushButton:hover{background:#555555;}
QPushButton:pressed{background:#3a3a3a;}
QLineEdit{background:#1e1e1e;border:1px solid #555;padding:6px;border-radius:3px;color:#fff;}
QTextEdit{background:#1e1e1e;border:1px solid #555;color:#eee;}
QListWidget{background:#262626;border:none;}
QListWidget::item{background:#333333;border-radius:4px;margin:4px;}
QListWidget::item:hover{background:#404040;}
QListWidget::item:selected{background:#485769;}
QTabBar::tab{background:#383838;padding:8px 16px;border:none;color:#bbbbbb;}
QTabBar::tab:selected{background:#2c2c2c;color:#ffffff;}
QProgressBar{background:#222;border-radius:3px;text-align:center;}
QProgressBar::chunk{background:#4185d7;}
QFrame{background:#2c2c2c;}
        """)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 左侧图标侧边栏
        left_side_bar = QWidget()
        left_side_bar.setFixedWidth(50)
        left_side_bar.setStyleSheet("background:#222222;")
        side_layout = QVBoxLayout(left_side_bar)
        side_layout.setContentsMargins(4, 10, 4, 10)
        side_layout.setSpacing(8)

        btn_project = QPushButton("📁")
        btn_project.setFixedSize(40, 40)
        btn_project.clicked.connect(lambda: self.switch_tab(0))

        btn_install = QPushButton("⬇️")
        btn_install.setFixedSize(40, 40)
        btn_install.clicked.connect(lambda: self.switch_tab(1))

        btn_example = QPushButton("📦")
        btn_example.setFixedSize(40,40)
        btn_example.clicked.connect(lambda:self.switch_tab(3))

        btn_editor = QPushButton("🖥")
        btn_editor.setFixedSize(40, 40)
        btn_editor.clicked.connect(lambda: self.switch_tab(2))

        btn_setting = QPushButton("⚙")
        btn_setting.setFixedSize(40, 40)
        btn_setting.clicked.connect(self.open_setting_dialog)

        side_layout.addWidget(btn_project)
        side_layout.addWidget(btn_install)
        side_layout.addWidget(btn_example)
        side_layout.addWidget(btn_editor)
        side_layout.addStretch()
        side_layout.addWidget(btn_setting)
        main_layout.addWidget(left_side_bar)

        # 右侧主体
        right_main = QWidget()
        right_layout = QVBoxLayout(right_main)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        top_bar = QWidget()
        top_bar.setFixedHeight(48)
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(12, 4, 12, 4)

        self.tab_bar = QTabBar()
        self.tab_bar.addTab("项目")
        self.tab_bar.addTab("版本下载")
        self.tab_bar.addTab("编辑器管理")
        self.tab_bar.addTab("示例项目")
        self.tab_bar.currentChanged.connect(self.switch_tab)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索项目")
        self.search_edit.setFixedWidth(220)
        self.search_edit.textChanged.connect(self.on_search)

        btn_add_project = QPushButton("+ 添加项目")
        btn_add_project.clicked.connect(self.add_project_dialog)

        # =========新增按钮：新建项目(UnityHub风格)=========
        btn_create_project = QPushButton("🆕新建项目")
        btn_create_project.clicked.connect(self.create_new_project_dialog)

        btn_refresh_releases = QPushButton("刷新版本")
        btn_refresh_releases.clicked.connect(self.fetch_releases)
        btn_refresh_example = QPushButton("刷新示例项目")
        btn_refresh_example.clicked.connect(self.fetch_example_releases)
        btn_clear_cache = QPushButton("清除下载缓存")
        btn_clear_cache.clicked.connect(self.clear_download_cache)
        btn_add_local_editor = QPushButton("添加本地编辑器")
        btn_add_local_editor.clicked.connect(self.add_local_editor)

        top_bar_layout.addWidget(self.tab_bar)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(self.search_edit)
        top_bar_layout.addSpacing(10)
        top_bar_layout.addWidget(btn_create_project)
        top_bar_layout.addWidget(btn_add_project)
        top_bar_layout.addWidget(btn_refresh_releases)
        top_bar_layout.addWidget(btn_refresh_example)
        top_bar_layout.addWidget(btn_clear_cache)
        top_bar_layout.addWidget(btn_add_local_editor)

        right_layout.addWidget(top_bar)

        self.stack = QStackedWidget()

        # -------- 0.项目页面 --------
        page_project = QWidget()
        page_proj_layout = QVBoxLayout(page_project)
        page_proj_layout.setContentsMargins(12,12,12,12)

        self.list_project = QListWidget()
        self.list_project.setIconSize(QSize(140,90))
        self.list_project.setViewMode(QListWidget.IconMode)
        self.list_project.setWrapping(True)
        self.list_project.setSpacing(10)
        self.list_project.setSelectionMode(QListWidget.SingleSelection)
        self.list_project.itemDoubleClicked.connect(self.on_item_double_click)
        self.list_project.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_project.customContextMenuRequested.connect(self.show_context_menu)
        page_proj_layout.addWidget(self.list_project)
        self.stack.addWidget(page_project)

        # -------- 1.版本下载页面：上方release列表 --------
        page_download = QWidget()
        download_layout = QVBoxLayout(page_download)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(10,10,10,10)
        self.scroll_layout.setSpacing(8)
        self.lbl_tip = QLabel("点击「刷新版本」拉取AoiStudio发布包\n⚙左侧齿轮按钮打开设置（代理/自定义EXE）\n读取config/download.json提供网盘备用下载")
        self.lbl_tip.setAlignment(Qt.AlignCenter)
        self.scroll_layout.addWidget(self.lbl_tip)
        self.scroll_area.setWidget(self.scroll_content)
        download_layout.addWidget(self.scroll_area)
        self.stack.addWidget(page_download)

        # -------- 2.编辑器管理标签页 --------
        page_editor_mgr = QWidget()
        editor_layout = QVBoxLayout(page_editor_mgr)
        group_editor_status = QGroupBox("本地已安装编辑器状态")
        grp_layout = QVBoxLayout(group_editor_status)
        self.editor_list = QListWidget()
        self.editor_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.editor_list.customContextMenuRequested.connect(self.on_installed_right_menu)
        self.editor_list.itemDoubleClicked.connect(self.on_local_version_double_click)
        grp_layout.addWidget(self.editor_list)
        editor_layout.addWidget(group_editor_status)

        tip_label = QLabel("提示：双击选中项目+双击版本启动编辑器；右键删除版本；右键菜单可【仅启动编辑器】")
        tip_label.setWordWrap(True)
        editor_layout.addWidget(tip_label)
        self.stack.addWidget(page_editor_mgr)

        # ==========【新增】3.示例项目页面 ==========
        page_example = QWidget()
        example_layout = QVBoxLayout(page_example)
        self.example_scroll = QScrollArea()
        self.example_scroll.setWidgetResizable(True)
        self.example_scroll_content = QWidget()
        self.example_scroll_layout = QVBoxLayout(self.example_scroll_content)
        self.example_scroll_layout.setContentsMargins(10,10,10,10)
        self.example_scroll_layout.setSpacing(8)
        self.example_tip = QLabel("点击「刷新示例项目」拉取AoiStudio_ExampleProjects仓库资源，只识别Aoi_开头的zip")
        self.example_tip.setAlignment(Qt.AlignCenter)
        self.example_scroll_layout.addWidget(self.example_tip)
        self.example_scroll.setWidget(self.example_scroll_content)
        example_layout.addWidget(self.example_scroll)
        self.stack.addWidget(page_example)

        right_layout.addWidget(self.stack)
        main_layout.addWidget(right_main)

        self.refresh_ui()
        self.refresh_installed_list()

    # ==========【新增】新建项目入口函数 ==========
    def create_new_project_dialog(self):
        if not self.installed_versions:
            QMessageBox.warning(self, "提示", "没有已安装的编辑器版本，请先下载/导入编辑器！")
            return
        dlg = CreateProjectDialog(self.installed_versions, self)
        res = dlg.exec_()
        if res != QDialog.Accepted:
            return
        sel_ver: InstalledVersion = dlg.selected_version
        target_proj_path = dlg.project_folder
        template_mode = dlg.get_template_mode()

        try:
            if template_mode == 1:
                # 复制模板：Editor_xxx/res/project_example
                entries = os.listdir(sel_ver.install_path)
                sub_dirs = [e for e in entries if os.path.isdir(os.path.join(sel_ver.install_path, e))]
                if not sub_dirs:
                    QMessageBox.critical(self, "模板缺失", f"编辑器目录没有子文件夹:{sel_ver.install_path}")
                    return
                sub_editor_root = os.path.join(sel_ver.install_path, sub_dirs[0])
                template_src = os.path.join(sub_editor_root, "res", "project_example")
                if not os.path.exists(template_src):
                    QMessageBox.critical(self, "模板缺失", f"编辑器内找不到模板目录：{template_src}")
                    return
                shutil.copytree(template_src, target_proj_path)
            else:
                # 空白项目，只创建文件夹
                os.makedirs(target_proj_path, exist_ok=False)

            new_proj = ProjectItem(
                name=os.path.basename(target_proj_path),
                path=target_proj_path,
                version=sel_ver.tag,
                last_open=datetime.now().strftime("%Y-%m-%d %H:%M"),
                thumbnail=""
            )
            self.projects.append(new_proj)
            self.save_full_config()
            self.refresh_ui()
            QMessageBox.information(self, "项目创建成功", f"项目路径：{target_proj_path}\n已加入项目列表")
        except Exception as e:
            QMessageBox.critical(self, "创建项目失败", str(e))

    def fetch_example_releases(self):
        self.example_tip.setText("正在请求示例项目Github API...")
        proxies = self.get_request_proxy()
        self.example_fetch_thread = GithubFetchThread(EXAMPLE_GITHUB_API_URL, proxies=proxies, filter_prefix=EXAMPLE_FILTER_PREFIX)
        self.example_fetch_thread.finished_signal.connect(self.on_example_fetch_done)
        self.example_fetch_thread.error_signal.connect(self.on_example_fetch_error)
        self.example_fetch_thread.start()

    def on_example_fetch_done(self,rel_list):
        self.example_release_list = rel_list
        #清空旧卡片
        while self.example_scroll_layout.count():
            item = self.example_scroll_layout.takeAt(0)
            w = item.widget()
            if w:w.deleteLater()
        if not rel_list:
            self.example_scroll_layout.addWidget(QLabel("没有找到Aoi_前缀的示例项目包"))
            return
        proxies = self.get_request_proxy()
        for r in rel_list:
            card = ExampleProjectCard(r,proxies,self)
            self.example_scroll_layout.addWidget(card)
        self.example_scroll_layout.addStretch()
        self.example_tip.setText(f"加载完成，共{len(rel_list)}个示例项目Release")

    def on_example_fetch_error(self,err):
        self.example_tip.setText(f"获取示例项目失败:{err}\n检查网络或者代理设置")

    def launch_editor_with_project(self, ver: InstalledVersion, project_path: str):
        """通用函数：使用指定版本打开指定项目路径（命令行/双击都调用这个）"""
        import subprocess
        exe_path = ""
        try:
            entries = os.listdir(ver.install_path)
            sub_dirs = [e for e in entries if os.path.isdir(os.path.join(ver.install_path, e))]
            if not sub_dirs:
                QMessageBox.warning(self, "找不到子目录", f"{ver.install_path} 下没有子文件夹")
                return False
            dir_name = sub_dirs[0]
            exe_path = os.path.join(ver.install_path, dir_name, "AoiStudioEditor.exe")
        except Exception as e:
            QMessageBox.warning(self, "读取目录失败", str(e))
            return False

        exe_path = os.path.abspath(exe_path)

        if not os.path.exists(exe_path):
            QMessageBox.warning(self, "未找到编辑器EXE", f"路径不存在：{exe_path}\n请在设置里指定自定义EXE路径")
            return False
        try:
            os.chdir(os.path.dirname(exe_path))
            subprocess.Popen([exe_path, project_path])
            QApplication.quit()
            return True
        except Exception as e:
            QMessageBox.critical(self, "启动编辑器失败", str(e))
            return False

    def load_local_json_releases(self):
        """读取config/download.json本地备用下载源"""
        if not os.path.exists(LOCAL_DOWNLOAD_JSON_PATH):
            return []
        try:
            with open(LOCAL_DOWNLOAD_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("releases", [])
            out = []
            for r in items:
                r["source"] = "json"
                out.append(r)
            return out
        except Exception:
            return []

    def get_request_proxy(self):
        proxies = {}
        if self.proxy_config["http"]:
            proxies["http"] = self.proxy_config["http"]
        if self.proxy_config["https"]:
            proxies["https"] = self.proxy_config["https"]
        return proxies if proxies else None

    def open_setting_dialog(self):
        dlg = SettingDialog(self.proxy_config, self.editor_custom_exe, self)
        if dlg.exec_():
            self.proxy_config, self.editor_custom_exe = dlg.get_values()
            self.save_full_config()

    def switch_tab(self, index):
        self.stack.setCurrentIndex(index)
        self.tab_bar.setCurrentIndex(index)
        if index == 2:
            self.refresh_installed_list()

    def fetch_releases(self):
        self.lbl_tip.setText("正在请求Github API...")
        proxies = self.get_request_proxy()
        self.fetch_thread = GithubFetchThread(GITHUB_API_URL, proxies=proxies, filter_prefix=FILTER_PREFIXES)
        self.fetch_thread.finished_signal.connect(lambda g_data:self.on_fetch_done(g_data, use_github=True))
        self.fetch_thread.error_signal.connect(self.on_fetch_error)
        self.fetch_thread.start()

    def get_installed_tag_set(self):
        return {v.tag for v in self.installed_versions}

    def get_installed_map(self):
        return {v.tag: v for v in self.installed_versions}

    def on_fetch_done(self, rel_list, use_github):
        json_list = self.load_local_json_releases()
        # github优先，json做降级补充
        final_list = []
        seen_tags = set()
        for g in rel_list:
            final_list.append(g)
            seen_tags.add(g["tag"])
        for j in json_list:
            if j["tag"] not in seen_tags:
                final_list.append(j)

        self.release_list = final_list
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        if not final_list:
            self.scroll_layout.addWidget(QLabel("没有可用版本，请检查网络或配置config/download.json"))
            return
        proxies = self.get_request_proxy()
        tag_set = self.get_installed_tag_set()
        tag_map = self.get_installed_map()
        for r in final_list:
            card = ReleaseCard(r, proxies, self, tag_set, tag_map)
            self.scroll_layout.addWidget(card)
        self.scroll_layout.addStretch()
        self.lbl_tip.setText(f"加载完成,GitHub:{len(rel_list)}个,JSON备用源:{len(json_list)}个")

    def on_fetch_error(self, err):
        json_list = self.load_local_json_releases()
        if len(json_list) > 0:
            self.lbl_tip.setText(f"Github访问失败，使用本地JSON备用源！错误:{err}")
            self.on_fetch_done([], use_github=False)
        else:
            self.lbl_tip.setText(f"获取版本失败：{err}\nconfig/download.json不存在或为空，无法降级")

    def add_installed_version(self, ver: InstalledVersion):
        self.installed_versions.append(ver)
        self.save_full_config()
        self.refresh_installed_list()

    def refresh_installed_list(self):
        self.editor_list.clear()
        for v in self.installed_versions:
            item_text = f"[{v.tag}] {v.name}\n下载时间:{v.download_time}\n{v.install_path}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, v)
            self.editor_list.addItem(item)

    # --------------------新增：仅启动编辑器AoiStudioEditor.exe--------------------
    def launch_raw_editor(self, ver: InstalledVersion):
        try:
            entries = os.listdir(ver.install_path)
            sub_dirs = [e for e in entries if os.path.isdir(os.path.join(ver.install_path,e))]
            if not sub_dirs:
                QMessageBox.warning(self, "找不到子目录", f"{ver.install_path} 下没有子文件夹")
                return
            dir_name = sub_dirs[0]
            exe_path = os.path.join(ver.install_path, dir_name, "AoiStudioEditor.exe")
        except Exception as e:
            QMessageBox.warning(self, "读取目录失败", str(e))
            return

        exe_path = os.path.abspath(exe_path)
        if not os.path.exists(exe_path):
            QMessageBox.warning(self, "找不到AoiStudioEditor.exe",
                                f"未找到：{exe_path}\n确认该版本包根目录存在AoiStudioEditor.exe")
            return
        import subprocess
        try:
            print(exe_path)
            os.chdir(os.path.abspath(os.path.join(ver.install_path,dir_name)))
            subprocess.Popen([exe_path])
            # 然后退出pyqt5
            QApplication.quit()
        except Exception as e:
            print(e)
            QMessageBox.critical(self, "启动AoiStudioEditor失败", str(e))

    # 本地版本右键菜单：删除、仅启动编辑器
    def on_installed_right_menu(self, pos: QPoint):
        item = self.editor_list.itemAt(pos)
        if not item:
            return
        ver: InstalledVersion = item.data(Qt.UserRole)
        menu = QMenu()
        act_launch_editor = menu.addAction("仅启动编辑器")
        act_remove_list = menu.addAction("仅从列表移除")
        act_remove_all = menu.addAction("从列表移除 + 删除磁盘文件夹")
        act = menu.exec_(self.editor_list.viewport().mapToGlobal(pos))

        if act == act_launch_editor:
            self.launch_raw_editor(ver)
        elif act == act_remove_list:
            self.installed_versions.remove(ver)
            self.save_full_config()
            self.refresh_installed_list()
        elif act == act_remove_all:
            ret = QMessageBox.question(self, "确认删除", f"确定删除 {ver.tag}？\n文件夹:{ver.install_path}")
            if ret != QMessageBox.Yes:
                return
            if os.path.exists(ver.install_path):
                try:
                    shutil.rmtree(ver.install_path)
                except Exception as e:
                    QMessageBox.warning(self,"删除文件夹失败",str(e))
            self.installed_versions.remove(ver)
            self.save_full_config()
            self.refresh_installed_list()

    def on_local_version_double_click(self, item):
        ver: InstalledVersion = item.data(Qt.UserRole)
        selected_project_items = self.list_project.selectedItems()
        if not selected_project_items:
            QMessageBox.warning(self, "提示", "请先切换到【项目】页面选中一个项目！")
            return
        proj_item = selected_project_items[0]
        proj: ProjectItem = proj_item.data(Qt.UserRole)
        self.launch_editor_with_project(ver, proj.path)

    def clear_download_cache(self):
        ret = QMessageBox.question(self, "清除下载缓存", f"将清空 {DOWNLOAD_DIR} 目录下所有文件，确定？")
        if ret != QMessageBox.Yes:
            return
        if os.path.exists(DOWNLOAD_DIR):
            for fname in os.listdir(DOWNLOAD_DIR):
                fpath = os.path.join(DOWNLOAD_DIR, fname)
                try:
                    if os.path.isfile(fpath):
                        os.remove(fpath)
                except Exception:
                    pass
        QMessageBox.information(self,"完成","下载缓存已清理")

    def load_full_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.projects = [ProjectItem.from_dict(d) for d in data.get("projects", [])]
                self.installed_versions = [InstalledVersion.from_dict(d) for d in data.get("installed", [])]
                self.proxy_config = data.get("proxy", {"http":"","https":""})
                self.editor_custom_exe = data.get("editor_exe", "")
            except Exception:
                pass

    def save_full_config(self):
        dump = {
            "projects": [p.to_dict() for p in self.projects],
            "installed": [v.to_dict() for v in self.installed_versions],
            "proxy": self.proxy_config,
            "editor_exe": self.editor_custom_exe
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(dump, f, ensure_ascii=False, indent=2)

    def refresh_ui(self, filter_keyword: str = ""):
        self.list_project.clear()
        for proj in self.projects:
            if filter_keyword:
                kw = filter_keyword.lower()
                if kw not in proj.name.lower() and kw not in proj.path.lower():
                    continue
            item = QListWidgetItem()
            item.setText(f"{proj.name}\n{proj.version}\n{proj.last_open}")
            item.setData(Qt.UserRole, proj)
            if proj.thumbnail and os.path.exists(proj.thumbnail):
                icon = QIcon(proj.thumbnail)
            else:
                pix = QPixmap(140, 90)
                pix.fill(Qt.darkCyan)
                icon = QIcon(pix)
            item.setIcon(icon)
            item.setSizeHint(QSize(180, 140))
            self.list_project.addItem(item)

    def on_search(self, txt):
        self.refresh_ui(txt)

    def add_project_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "选择AoiStudio项目文件夹", QDir.homePath())
        if not folder:
            return
        name = os.path.basename(folder)
        new_proj = ProjectItem(
            name=name,
            path=folder,
            version="AoiStudio",
            last_open=datetime.now().strftime("%Y-%m-%d %H:%M"),
            thumbnail=""
        )
        self.projects.append(new_proj)
        self.save_full_config()
        self.refresh_ui()

    def on_item_double_click(self, item: QListWidgetItem):
        proj: ProjectItem = item.data(Qt.UserRole)
        proj.last_open = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.save_full_config()
        path = os.path.abspath(proj.path)
        if os.path.exists(path):
            # 如果有安装编辑器，则用self.launch_editor_with_project
            if self.installed_versions:
                try:
                    dlg = SelectEditorVersionDialog(self.installed_versions, path)
                    res = dlg.exec_()
                    # res == QDialog.Accepted 用户点击确定；Cancel是取消
                    if res == QDialog.Accepted:
                        self.launch_editor_with_project(dlg.selected_version, path)
                except Exception as e:                    QMessageBox.critical(self, "打开项目异常", str(e))
            else:
                QMessageBox.warning(self, "没有可用编辑器", "请先下载或者导入AoiStudio编辑器版本")
        else:
            QMessageBox.warning(self, "项目路径不存在", f"{proj.path}\n文件夹已被移动或删除")

    def show_context_menu(self, pos: QPoint):
        item = self.list_project.itemAt(pos)
        if not item:
            return
        proj: ProjectItem = item.data(Qt.UserRole)
        menu = QMenu()
        act_open_folder = menu.addAction("打开项目所在文件夹")
        act_remove = menu.addAction("从Hub列表移除项目")
        act = menu.exec_(self.list_project.viewport().mapToGlobal(pos))

        if act == act_open_folder:
            if os.path.exists(proj.path):
                os.startfile(proj.path)
            else:
                QMessageBox.warning(self, "路径不存在", proj.path)
        elif act == act_remove:
            self.projects.remove(proj)
            self.save_full_config()
            self.refresh_ui()

    def add_local_editor(self):
        """手动添加本地已经解压好的编辑器版本"""
        folder = QFileDialog.getExistingDirectory(self, "选择已解压的AoiStudio编辑器根目录")
        if not folder:
            return
        tag_input, ok = QInputDialog.getText(self, "填写版本Tag", "请输入该版本的tag名称(例如v1.1.0)：")
        if not ok or not tag_input.strip():
            return
        tag_input = tag_input.strip()
        new_ver = InstalledVersion(
            tag=tag_input,
            name=os.path.basename(folder),
            install_path=folder,
            download_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        self.installed_versions.append(new_ver)
        self.save_full_config()
        self.refresh_installed_list()
        QMessageBox.information(self, "导入完成", f"版本 {tag_input} 已添加到本地编辑器列表")


def main():
    cli_proj = None
    if len(sys.argv) > 1:
        maybe_path = sys.argv[1]
        if os.path.isdir(maybe_path):
            cli_proj = maybe_path
    app = QApplication(sys.argv)
    win = AoiStudioHub(cli_project_path=cli_proj)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    from PyQt5.QtWidgets import QInputDialog
    main()