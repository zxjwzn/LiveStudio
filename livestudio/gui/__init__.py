"""GUI 包根

LiveStudio 的 PySide6 + QFluentWidgets 桌面界面。后端(config / audio / 平台 /
动画 / 日志)保持不变,GUI 通过 bridge 层单向消费后端事件与命令。
"""
