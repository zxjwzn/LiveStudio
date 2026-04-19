def main() -> None:
     """输出当前项目中 VTube Studio 请求库的设计说明。"""

     design = """
LiveStudio VTube Studio API 设计：

1. `livestudio/clients/vtube_studio/config.py`
    - 保存连接配置与插件身份信息。

2. `livestudio/clients/vtube_studio/errors.py`
    - 统一定义连接、认证、响应与 API 错误。

3. `livestudio/clients/vtube_studio/models/`
    - 采用按领域拆分的 Pydantic 模型文件。
    - 每个请求、响应和错误数据都对应独立模型。
    - 所有字段均带详细注释，便于 IDE 与自动文档使用。

4. `livestudio/clients/vtube_studio/client.py`
    - 基于异步 WebSocket 的底层客户端。
    - 负责发送请求、匹配响应、统一错误处理与模型反序列化。

5. `livestudio/clients/vtube_studio/service.py`
    - 面向业务的服务封装层。
    - 提供 `connect_and_authenticate` 等高层函数，隔离网络细节。

6. `livestudio/clients/vtube_studio/examples.py`
    - 提供常见调用示例，展示库的实际使用方式。
""".strip()

     print(design)


if __name__ == "__main__":
    main()
