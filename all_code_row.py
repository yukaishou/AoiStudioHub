import os

def count_py_lines(folder_path: str):
    total_lines = 0
    # 遍历文件夹
    for root, dirs, files in os.walk(folder_path):
        for filename in files:
            if filename.endswith(".py"):
                file_path = os.path.join(root, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                        # 过滤纯空行
                        valid = [line for line in lines if line.strip() != ""]
                        cnt = len(valid)
                        total_lines += cnt
                        print(f"{file_path} : {cnt} 行")
                except Exception as e:
                    print(f"读取失败 {file_path}, 错误: {e}")
    print(f"\n===== 总计有效行数（去除空行）：{total_lines}")
    return total_lines
if __name__ == "__main__":
    # 修改这里为你的目标文件夹路径
    target_folder = r"."
    count_py_lines(target_folder)