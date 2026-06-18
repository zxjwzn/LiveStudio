"""LiveStudio GUI 包。

基于 Flet 的图形界面，叠加在现有 asyncio 后端之上。
分层：core（通用框架）/ bridge（后端↔状态，P2）/ views + components（视图层）。

入口：``python -m livestudio.gui.main``
"""
