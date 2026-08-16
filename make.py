import os
import shutil
import subprocess
import sys

# ====================== 配置区，按需改这里 ======================
MAIN_SCRIPT = "main.py"             # ← 你的真实主程序文件名
EXE_ICON = "icon.png"               # 必须是ico！没有就填空字符串 ""
APP_NAME = "AoiStudioHub"

# True=单文件exe；False=目录模式（推荐，启动快）
ONE_FILE = True

# 是否隐藏黑窗口，调试改成False
NO_CONSOLE = True

ADD_DATA = [
    # ("icon.png", ".")   # 需要把png打进包就打开注释
]

EXCLUDE_MODULES = [
    "tkinter",
    "matplotlib",
    "numpy",
    "pandas",
    "test",
    "unittest"
]
# ==============================================================


def clean_build_output():
    for d in ["build", "dist"]:
        if os.path.exists(d):
            shutil.rmtree(d)
    spec_file = f"{APP_NAME}.spec"
    if os.path.exists(spec_file):
        os.remove(spec_file)


def build_pyinstaller_cmd():
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--noupx",
        "--clean"
    ]

    if NO_CONSOLE:
        cmd.append("--noconsole")
    else:
        cmd.append("--console")

    if ONE_FILE:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    # 只有ico存在才加-i参数
    if EXE_ICON and os.path.exists(EXE_ICON):
        cmd.extend(["-i", EXE_ICON])

    for src, dst in ADD_DATA:
        cmd.extend(["--add-data", f"{src}{os.pathsep}{dst}"])

    for mod in EXCLUDE_MODULES:
        cmd.extend(["--exclude-module", mod])

    # 主脚本放最后！！pyinstaller要求脚本参数必须在全部选项之后
    cmd.append(MAIN_SCRIPT)
    return cmd


def main():
    if not os.path.exists(MAIN_SCRIPT):
        print(f"错误：找不到主脚本 {MAIN_SCRIPT}")
        sys.exit(1)

    print(">>> 清理旧构建产物...")
    clean_build_output()

    cmd = build_pyinstaller_cmd()
    print("\n执行命令：")
    print(" ".join(cmd))
    print("\n=====开始打包=====\n")

    ret = subprocess.run(cmd, shell=False)
    shutil.copy(EXE_ICON, f"dist/{EXE_ICON}")
    if ret.returncode == 0:
        print("\n✅打包成功！输出目录：dist/")
    else:
        print(f"\n❌打包失败，返回码：{ret.returncode}")
        sys.exit(ret.returncode)

if __name__ == "__main__":
    main()